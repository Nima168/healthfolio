"""Extraction end to end against the real test database, with a fake Groq client (no network, no cost)."""

from datetime import UTC, datetime, timedelta

import groq
import pytest
from sqlalchemy import select, update

from app.ai.extractor import GroqExtractor
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models.auth import AuditEvent
from app.models.extraction import Observation, ProcessingJob
from app.services import jobs
from app.worker import Worker
from tests.ai_fakes import SYNTHETIC_REPORT_LINES, FakeGroq, api_error, payload, response, result, text_pdf

pytestmark = pytest.mark.integration


def make_user(client, email):
    token = client.post("/api/v1/auth/register", json={"email": email, "password": "a long enough passphrase"})
    return {"Authorization": f"Bearer {token.json()['access_token']}"}


@pytest.fixture
def asha(client, db, storage_dir):
    return make_user(client, "asha@example.com")


@pytest.fixture
def settings():
    return get_settings()


def upload_report(client, headers, label="1", category="lab_report", lines=None):
    content = text_pdf([*(lines or SYNTHETIC_REPORT_LINES), f"Report reference {label}"])
    data = {"title": f"Synthetic report {label}"} | ({"category": category} if category else {})
    response_ = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("report.pdf", content, "application/pdf")},
        data=data,
    )
    assert response_.status_code == 201
    return response_.json()["id"]


def run_worker(settings, *replies):
    fake = FakeGroq(*replies)
    worker = Worker(settings, GroqExtractor(fake, settings))
    processed = worker.run(once=True)
    return processed, fake


def extraction(client, headers, document_id):
    return client.get(f"/api/v1/documents/{document_id}/observations", headers=headers).json()


def all_jobs(db):
    db.expire_all()
    return db.scalars(select(ProcessingJob).order_by(ProcessingJob.created_at)).all()


# ---------- queue and worker ----------


def test_upload_queues_one_extraction_job(client, asha, db):
    document_id = upload_report(client, asha)

    [job] = all_jobs(db)
    assert (str(job.document_id), job.status, job.attempts) == (document_id, "pending", 0)
    assert extraction(client, asha, document_id)["job"]["status"] == "pending"


def test_worker_extracts_results(client, asha, db, settings):
    document_id = upload_report(client, asha)
    results = [
        result(),
        result(test_name="HbA1c", value_text="6.1", value_numeric=6.1, unit="%", confidence="medium"),
        result(
            test_name="Vitamin B12",
            value_text="<150",
            value_numeric=None,
            unit="pg/mL",
            reference_range_text="200 - 900",
        ),
    ]

    processed, fake = run_worker(settings, response(payload(results)))

    assert processed == 1
    body = extraction(client, asha, document_id)
    assert body["job"]["status"] == "completed_with_warnings"  # HbA1c was only medium confidence
    assert [item["name"] for item in body["items"]] == ["Haemoglobin", "HbA1c", "Vitamin B12"]
    assert [item["needs_review"] for item in body["items"]] == [False, True, False]
    # Summary against the report's own printed range (12.0 - 15.5 in the fake).
    summary = body["summary"]
    assert summary["report_date"] == "14/03/2026"
    assert [line["name"] for line in summary["normal"]] == ["Haemoglobin"]
    assert summary["above"] == []
    assert [line["name"] for line in summary["below"]] == []  # HbA1c is unclear, so it is not judged
    assert [line["name"] for line in summary["invalid"]] == ["HbA1c", "Vitamin B12"]
    assert summary["invalid"][1]["value_text"] == "<150"
    assert body["items"][2]["value_text"] == "<150" and body["items"][2]["value_numeric"] is None
    assert body["items"][0]["page"] == 1 and body["items"][0]["observed_at"] == "2026-03-14"

    document = client.get(f"/api/v1/documents/{document_id}", headers=asha).json()
    assert document["processing_status"] == "completed_with_warnings"

    [job] = all_jobs(db)
    assert (job.model_version, job.prompt_version, job.input_tokens, job.output_tokens) == (
        "qwen/qwen3.8-27b",
        "lab-results-v6-dates",
        1200,
        340,
    )
    # The typed PDF's own text was sent, not the file.
    assert "HbA1c" in fake.requests[0]["messages"][1]["content"]


def test_clean_extraction_completes_without_warnings(client, asha, settings):
    document_id = upload_report(client, asha)
    run_worker(settings, response(payload([result()])))

    assert extraction(client, asha, document_id)["job"]["status"] == "completed"


def test_transient_errors_are_retried_with_backoff_then_fail(client, asha, db, settings):
    document_id = upload_report(client, asha)
    rate_limited = api_error(groq.RateLimitError, 429)

    run_worker(settings, rate_limited)
    [job] = all_jobs(db)
    assert (job.status, job.attempts, job.error_category) == ("pending", 1, "ai_unavailable")
    assert job.run_after > datetime.now(UTC)  # waiting to retry
    assert run_worker(settings, rate_limited)[0] == 0  # not runnable yet

    for _ in range(settings.extraction_max_attempts - 1):
        db.execute(update(ProcessingJob).values(run_after=datetime.now(UTC) - timedelta(seconds=1)))
        db.commit()
        run_worker(settings, rate_limited)

    [job] = all_jobs(db)
    assert (job.status, job.attempts) == ("failed", settings.extraction_max_attempts)
    assert extraction(client, asha, document_id)["job"]["error_category"] == "ai_unavailable"


def test_permanent_errors_fail_immediately(client, asha, db, settings):
    upload_report(client, asha)

    run_worker(settings, response(payload(), finish_reason="content_filter"))

    [job] = all_jobs(db)
    assert (job.status, job.attempts, job.error_category) == ("failed", 1, "ai_refused")
    assert db.scalar(select(AuditEvent).where(AuditEvent.event_type == "ai.extraction_failed")) is not None


def test_stale_running_jobs_are_recovered(client, asha, db, settings):
    upload_report(client, asha)
    db.execute(update(ProcessingJob).values(status="running", heartbeat_at=datetime.now(UTC) - timedelta(minutes=30)))
    db.commit()

    processed, _ = run_worker(settings, response(payload()))

    assert processed == 1
    assert all_jobs(db)[0].status == "completed"


def test_two_workers_never_take_the_same_job(client, asha, db):
    upload_report(client, asha, "a")
    upload_report(client, asha, "b")
    first_session, second_session = get_session_factory()(), get_session_factory()()
    try:
        # Worker A is mid-claim, holding a row lock on the oldest job...
        locked = first_session.scalar(
            select(ProcessingJob).order_by(ProcessingJob.created_at).limit(1).with_for_update()
        )
        # ...so worker B skips it and takes the other one.
        claimed = jobs.claim_next(second_session)
        assert claimed is not None and claimed.id != locked.id
    finally:
        first_session.rollback()
        first_session.close()
        second_session.close()


def test_deleting_a_document_cancels_its_job_and_hides_results(client, asha, db, settings):
    document_id = upload_report(client, asha)
    client.delete(f"/api/v1/documents/{document_id}", headers=asha)

    assert run_worker(settings, response(payload()))[0] == 0
    assert all_jobs(db)[0].status == "cancelled"

    second = upload_report(client, asha, "2")
    run_worker(settings, response(payload()))
    client.delete(f"/api/v1/documents/{second}", headers=asha)
    db.expire_all()
    assert all(o.deleted_at is not None for o in db.scalars(select(Observation)))


def test_worker_logs_contain_no_document_content(client, asha, settings, capsys):
    upload_report(client, asha)
    capsys.readouterr()

    run_worker(settings, response(payload([result(source_text="Haemoglobin 13.8 g/dL")])))

    output = capsys.readouterr().out
    assert "extraction job finished" in output
    for secret in ("Haemoglobin", "13.8", "City Diagnostics", "SYSTEM_PROMPT"):
        assert secret not in output


# ---------- access ----------


def test_other_users_cannot_see_results(client, asha, settings):
    document_id = upload_report(client, asha)
    run_worker(settings, response(payload()))
    ravi = make_user(client, "ravi@example.com")

    assert client.get(f"/api/v1/documents/{document_id}/observations", headers=ravi).status_code == 404
    assert client.post(f"/api/v1/documents/{document_id}/extract", headers=ravi).status_code == 404


def test_results_are_shown_as_extracted_without_a_review_step(client, asha, settings):
    document_id = upload_report(client, asha)
    run_worker(settings, response(payload()))
    [item] = extraction(client, asha, document_id)["items"]

    assert not {"review_status", "reviewed_at", "corrections"} & item.keys()
    review = client.post(f"/api/v1/observations/{item['id']}/review", headers=asha, json={"action": "confirm"})
    assert review.status_code == 404


# ---------- requesting extraction again ----------


def test_extract_endpoint_rules(client, asha, db, settings):
    document_id = upload_report(client, asha)
    url = f"/api/v1/documents/{document_id}/extract"

    in_progress = client.post(url, headers=asha)
    assert (in_progress.status_code, in_progress.json()["error"]["code"]) == (409, "EXTRACTION_IN_PROGRESS")

    run_worker(settings, response(payload(), finish_reason="content_filter"))  # fails permanently
    retried = client.post(url, headers=asha)
    assert retried.status_code == 202 and retried.json()["job"]["status"] == "pending"

    run_worker(settings, response(payload()))
    read_again = client.post(url, headers=asha)  # a completed reading may be replaced
    assert read_again.status_code == 202
    assert len(all_jobs(db)) == 3


def test_documents_from_before_extraction_can_be_queued(client, asha, db):
    document_id = upload_report(client, asha)
    db.execute(update(ProcessingJob).values(status="cancelled"))  # stand-in for "no usable job"
    db.query(ProcessingJob).delete()
    db.commit()

    assert extraction(client, asha, document_id)["job"] is None
    assert client.post(f"/api/v1/documents/{document_id}/extract", headers=asha).status_code == 202


def test_response_reports_whether_extraction_is_enabled(client, asha, settings, monkeypatch):
    document_id = upload_report(client, asha)
    assert extraction(client, asha, document_id)["extraction_enabled"] is False

    monkeypatch.setattr(settings, "extraction_enabled", True)
    assert extraction(client, asha, document_id)["extraction_enabled"] is True
