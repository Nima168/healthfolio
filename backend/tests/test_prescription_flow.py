"""Prescriptions end to end: upload → worker → summary → "Add to Checkups and Follow-ups" → follow-ups list.

Real test database, fake Groq client (no network, no cost).
"""

from datetime import date

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models.extraction import ProcessingJob
from app.models.prescription import FollowUp, Medication, Suggestion
from tests.ai_fakes import (
    SYNTHETIC_PRESCRIPTION_LINES,
    SYNTHETIC_REPORT_LINES,
    classification,
    follow_up,
    medication,
    payload,
    prescription,
    response,
)
from tests.test_extraction_flow import extraction, make_user, run_worker, upload_report

pytestmark = pytest.mark.integration


@pytest.fixture
def asha(client, db, storage_dir):
    return make_user(client, "asha@example.com")


@pytest.fixture
def settings():
    return get_settings()


UNCLEAR_X_RAY = follow_up(description="X-ray", confidence="low")


def upload_prescription(client, headers, category="prescription", label="1"):
    return upload_report(client, headers, label, category=category, lines=SYNTHETIC_PRESCRIPTION_LINES)


def follow_ups(client, headers):
    return client.get("/api/v1/follow-ups", headers=headers).json()["items"]


def test_prescription_summary(client, asha, db, settings):
    document_id = upload_prescription(client, asha)

    processed, fake = run_worker(settings, response(prescription()))

    assert processed == 1
    assert fake.requests[0]["response_format"]["json_schema"]["name"] == "prescription"  # no classification call
    body = extraction(client, asha, document_id)
    assert body["job"]["status"] == "completed"
    assert body["document_kind"] == "prescription"
    assert body["summary"] is None and body["items"] == []

    summary = body["prescription"]
    assert (summary["prescribed_on"], summary["date_text"], summary["prescriber_name"]) == (
        "2026-10-07",
        "07-Oct-2026",
        "Dr. Sample Physician",
    )
    assert summary["medications"][0] == {
        "name": "Atorvastatin",
        "strength": "10 mg",
        "instructions": "once daily at night",
        "duration_text": "90 days",
        "unclear": False,
        "reason": None,
    }
    assert [(f["due_date"], f["description"]) for f in summary["follow_ups"]] == [
        ("2026-11-04", "Kidney function test + doctor visit"),
        ("2026-12-07", "CBC"),
        ("2027-01-07", "HbA1c + lipid profile"),
    ]
    assert "needs_review" not in summary
    assert not any(line["unclear"] for line in [*summary["medications"], *summary["follow_ups"]])
    assert summary["reminders"] == "available"

    [job] = db.scalars(select(ProcessingJob)).all()
    assert (job.document_kind, job.prompt_version) == ("prescription", "prescription-v5-readability")
    # Never inferred as currently taken from a document.
    assert {m.status for m in db.scalars(select(Medication))} == {"unknown"}


def test_unclear_items_are_flagged_where_they_are(client, asha, settings):
    document_id = upload_prescription(client, asha)
    run_worker(settings, response(prescription(follow_ups=[follow_up(), UNCLEAR_X_RAY])))

    body = extraction(client, asha, document_id)

    assert body["job"]["status"] == "completed_with_warnings"
    assert body["prescription"]["follow_ups"] == [
        {
            "due_date": "2026-11-04",
            "description": "Kidney function test",
            "unclear": False,
            "reason": None,
            "when_text": "after 4 weeks",  # shown as written, with the calculated date labelled as such
            "calculated": True,
        },
        {
            "due_date": "2026-11-04",
            "description": "X-ray",
            "unclear": True,
            "reason": "The follow-up was not clearly legible.",
            "when_text": "after 4 weeks",
            "calculated": True,
        },
    ]


def test_untyped_documents_are_classified_first(client, asha, db, settings):
    prescription_id = upload_prescription(client, asha, category=None, label="p")
    report_id = upload_report(client, asha, "r", category=None)
    other_id = upload_report(client, asha, "o", category=None, lines=["Synthetic invoice", "Total: 500"])

    # One worker run drains the queue, oldest first.
    _, fake = run_worker(
        settings,
        response(classification("prescription")),
        response(prescription()),
        response(classification("lab_report")),
        response(payload()),
        response(classification("other")),
    )

    assert extraction(client, asha, prescription_id)["document_kind"] == "prescription"
    assert extraction(client, asha, report_id)["summary"]["normal"][0]["name"] == "Haemoglobin"
    other = extraction(client, asha, other_id)
    assert (other["document_kind"], other["summary"], other["prescription"]) == ("other", None, None)
    assert len(fake.requests) == 5  # nothing extracted after "other"

    versions = {job.document_kind: job.prompt_version for job in db.scalars(select(ProcessingJob))}
    assert versions["prescription"] == "classify-v4-ocr+prescription-v5-readability"
    assert versions["other"] == "classify-v4-ocr"


def test_lab_reports_still_use_the_lab_summary(client, asha, settings):
    document_id = upload_report(client, asha)
    run_worker(settings, response(payload()))

    body = extraction(client, asha, document_id)

    assert body["document_kind"] == "lab_report" and body["prescription"] is None
    assert body["summary"]["report_date"] == "14/03/2026"
    assert SYNTHETIC_REPORT_LINES  # the lab path is unchanged


# ---------- Add as reminders → follow-ups ----------


def test_add_as_reminders(client, asha, db, settings):
    document_id = upload_prescription(client, asha)
    run_worker(settings, response(prescription()))

    added = client.post(f"/api/v1/documents/{document_id}/follow-ups", headers=asha)

    assert added.status_code == 201
    assert added.json()["prescription"]["reminders"] == "added"
    items = follow_ups(client, asha)
    assert [(f["due_date"], f["title"], f["kind"], f["status"]) for f in items] == [
        ("2026-11-04", "Kidney function test", "investigation", "scheduled"),
        ("2026-11-04", "doctor visit", "appointment", "scheduled"),
        ("2026-12-07", "CBC", "investigation", "scheduled"),
        ("2027-01-07", "HbA1c", "investigation", "scheduled"),
        ("2027-01-07", "lipid profile", "investigation", "scheduled"),
    ]
    assert items[0]["source_document_title"] == "Synthetic report 1"
    assert {s.status for s in db.scalars(select(Suggestion))} == {"accepted"}

    again = client.post(f"/api/v1/documents/{document_id}/follow-ups", headers=asha)
    assert (again.status_code, again.json()["error"]["code"]) == (409, "NOTHING_TO_ADD")
    assert len(follow_ups(client, asha)) == 5  # never added twice


def test_items_needing_review_are_not_added(client, asha, settings):
    document_id = upload_prescription(client, asha)
    run_worker(settings, response(prescription(follow_ups=[follow_up(), UNCLEAR_X_RAY])))

    client.post(f"/api/v1/documents/{document_id}/follow-ups", headers=asha)

    assert [f["title"] for f in follow_ups(client, asha)] == ["Kidney function test"]


def test_follow_up_status_and_overdue(client, asha, db, settings):
    document_id = upload_prescription(client, asha)
    run_worker(
        settings,
        response(prescription(follow_ups=[follow_up(date="2026-10-08", relative_amount=None, relative_unit=None)])),
    )
    client.post(f"/api/v1/documents/{document_id}/follow-ups", headers=asha)
    [item] = follow_ups(client, asha)
    assert item["overdue"] is (date.fromisoformat(item["due_date"]) < date.today())

    done = client.patch(f"/api/v1/follow-ups/{item['id']}", headers=asha, json={"status": "completed"}).json()
    assert (done["status"], done["overdue"]) == ("completed", False) and done["completed_at"] is not None

    undone = client.patch(f"/api/v1/follow-ups/{item['id']}", headers=asha, json={"status": "scheduled"}).json()
    assert undone["completed_at"] is None

    bad = client.patch(f"/api/v1/follow-ups/{item['id']}", headers=asha, json={"status": "done"})
    assert bad.status_code == 422


def test_other_users_cannot_see_or_change_follow_ups(client, asha, settings):
    document_id = upload_prescription(client, asha)
    run_worker(settings, response(prescription()))
    client.post(f"/api/v1/documents/{document_id}/follow-ups", headers=asha)
    item_id = follow_ups(client, asha)[0]["id"]
    ravi = make_user(client, "ravi@example.com")

    assert follow_ups(client, ravi) == []
    assert client.patch(f"/api/v1/follow-ups/{item_id}", headers=ravi, json={"status": "cancelled"}).status_code == 404
    assert client.post(f"/api/v1/documents/{document_id}/follow-ups", headers=ravi).status_code == 404


def test_deleting_the_prescription(client, asha, db, settings):
    added_id = upload_prescription(client, asha, label="a")
    pending_id = upload_prescription(client, asha, label="b")
    run_worker(settings, response(prescription()))
    run_worker(settings, response(prescription()))
    client.post(f"/api/v1/documents/{added_id}/follow-ups", headers=asha)

    client.delete(f"/api/v1/documents/{added_id}", headers=asha)
    client.delete(f"/api/v1/documents/{pending_id}", headers=asha)
    db.expire_all()

    # Follow-ups the user added stay; the deleted document's name is no longer shown.
    items = follow_ups(client, asha)
    assert len(items) == 5 and {f["source_document_title"] for f in items} == {None}
    assert db.scalar(select(FollowUp).limit(1)) is not None
    assert all(m.deleted_at is not None for m in db.scalars(select(Medication)))
    pending = db.scalars(select(Suggestion).where(Suggestion.status != "accepted")).all()
    assert pending and {s.status for s in pending} == {"superseded"}


def test_a_reading_that_found_nothing_can_be_tried_again(client, asha, db, settings):
    document_id = upload_prescription(client, asha)
    empty = response(prescription(medications=[], follow_ups=[], warnings=["not a valid prescription"]))
    _, fake = run_worker(settings, empty)
    # The document clearly has text, so an empty answer is read twice more, then reported, never shown as "none".
    assert len(fake.requests) == 3
    job = extraction(client, asha, document_id)["job"]
    assert (job["status"], job["error_category"]) == ("failed", "ai_empty_output")

    retried = client.post(f"/api/v1/documents/{document_id}/extract", headers=asha)
    assert retried.status_code == 202
    run_worker(settings, response(prescription()))

    assert len(extraction(client, asha, document_id)["prescription"]["medications"]) == 4


def test_read_again_replaces_the_reading_and_keeps_added_follow_ups(client, asha, db, settings):
    document_id = upload_prescription(client, asha)
    run_worker(settings, response(prescription()))
    client.post(f"/api/v1/documents/{document_id}/follow-ups", headers=asha)
    assert len(follow_ups(client, asha)) == 5

    assert client.post(f"/api/v1/documents/{document_id}/extract", headers=asha).status_code == 202
    run_worker(settings, response(prescription(medications=[medication()])))

    summary = extraction(client, asha, document_id)["prescription"]
    assert [m["name"] for m in summary["medications"]] == ["Atorvastatin"]  # only the new reading, no duplicates
    assert len(summary["follow_ups"]) == 3
    # The same follow-ups were already added: adding again links them instead of duplicating.
    assert summary["reminders"] == "available"
    client.post(f"/api/v1/documents/{document_id}/follow-ups", headers=asha)
    assert len(follow_ups(client, asha)) == 5
    assert extraction(client, asha, document_id)["prescription"]["reminders"] == "added"
