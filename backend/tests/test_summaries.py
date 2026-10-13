"""AI summaries: checking, request shape, and end to end with a fake Groq client (synthetic data, no network)."""

import json

import pytest
from sqlalchemy import select

from app.ai.summary import SummaryPayload, _months, _numbers, build_request, check
from app.api.v1.summaries import provide_ai_client
from app.core.config import get_settings
from app.models.summary import AiSummary
from app.services.summary_facts import Fact, Facts
from tests.ai_fakes import FakeGroq, connection_error, payload, response, result
from tests.test_extraction_flow import make_user, run_worker, upload_report

# ---------- checking (no database) ----------

FACTS = Facts(
    records=[
        Fact(
            id="F1",
            kind="lab_results",
            title="Lab results: 2 tests",
            date="2026-03-14",
            details=["HbA1c 6.1 % (high; range 4.0 - 5.6)", "1 within range"],
        ),
        Fact(id="F2", kind="medications", title="Metformin 500 mg", details=["once daily after dinner"]),
    ],
    checks=[Fact(id="C1", kind="check", title="1 medicine read from documents not yet confirmed.")],
)


def summary(*sections, explanations=()):
    return SummaryPayload.model_validate({"sections": list(sections), "explanations": list(explanations)})


def section(key, *sentences):
    return {"key": key, "sentences": list(sentences)}


def sentence(text, *ids, kind="record"):
    return {"text": text, "kind": kind, "fact_ids": list(ids)}


def test_supported_sentences_are_kept_with_their_sources():
    checked = check(
        summary(
            section("results", sentence("Your HbA1c of 6.1 % is above the range 4.0 - 5.6 on the report.", "F1")),
            section("overview", sentence("Your report from 14 March 2026 has 2 tests.", "F1")),
            section("gaps", sentence("One medicine still needs confirming.", "C1", kind="interpretation")),
        ),
        FACTS,
    )

    assert checked.dropped == 0
    assert [s["key"] for s in checked.sections] == ["overview", "results", "gaps"]  # fixed order
    assert checked.sections[0]["title"] == "Overview"
    assert checked.sections[2]["sentences"] == [
        {"text": "One medicine still needs confirming.", "kind": "interpretation", "fact_ids": ["C1"]}
    ]


@pytest.mark.parametrize(
    "bad",
    [
        sentence("Your HbA1c is 7.2 %.", "F1"),  # a number not in the cited facts
        sentence("Your HbA1c is 6.1 %.", "F2"),  # true, but not in the fact it cites
        sentence("You have diabetes."),  # no source at all
        sentence("Your HbA1c is 6.1 %.", "F1", "F9"),  # an invented fact id
        sentence("   ", "F1"),
        sentence("Your lab report is from June 2026.", "F1"),  # the wrong month (the fact is 2026-03-14)
        sentence("You have four lab results.", "F1"),  # a number written as a word, not in the fact
    ],
)
def test_unsupported_sentences_are_dropped_and_counted(bad):
    checked = check(summary(section("results", bad, sentence("Metformin is listed.", "F2"))), FACTS)

    assert checked.dropped == 1
    assert checked.sections[0]["sentences"] == [{"text": "Metformin is listed.", "kind": "record", "fact_ids": ["F2"]}]


def test_numbers_are_read_as_written_but_not_from_names_or_units():
    assert _numbers("HbA1c 6.1 %, eGFR 61 mL/min/1.73 m2, 1,200 cells, 03 days, four tests, once daily") == {
        "6.1",
        "61",
        "1.73",
        "1200",
        "3",
        "4",
    }
    assert _months("June 2026, 10-Aug-2026, 2026-11-04, you may ask, 5 May") == {6, 8, 11, 5}
    assert _months("you may ask") == set()


def test_general_information_explains_only_recorded_terms_and_gives_no_values():
    explanations = [
        {
            "term": "HbA1c",
            "text": "A blood test that reflects average blood sugar over recent months.",
            "fact_ids": ["F1"],
        },
        {"term": "HbA1c", "text": "Below 5.7 is normal.", "fact_ids": ["F1"]},  # a value: ranges differ by lab
        {"term": "Cholesterol", "text": "A fat in the blood.", "fact_ids": ["F1"]},  # not in the records
    ]
    checked = check(
        summary(section("results", sentence("Metformin is listed.", "F2")), explanations=explanations), FACTS
    )

    assert [e["term"] for e in checked.explanations] == ["HbA1c"]
    assert checked.dropped == 2


def test_a_summary_with_nothing_supported_is_empty():
    assert check(summary(section("overview", sentence("All is well.", "F7"))), FACTS).empty


def test_request_sends_only_facts_as_data_with_a_strict_schema():
    settings = get_settings()
    facts = Facts(
        records=[Fact(id="F1", kind="lab_results", title="Lab results: 1 test", source_document_title="Mine")],
        checks=[],
    )

    request = build_request(facts, settings, scope="history")

    assert request["model"] == settings.ai_model
    assert request["reasoning_format"] == "hidden"
    assert request["response_format"]["json_schema"]["strict"] is True
    system, user = request["messages"]
    assert system["role"] == "system" and "Use ONLY these facts" in system["content"]
    assert user["content"].startswith("<facts>")
    sent = json.loads(user["content"].split("<facts>")[1].split("</facts>")[0])
    assert sent == [{"id": "F1", "kind": "lab_results", "title": "Lab results: 1 test", "date": "not mentioned"}]
    assert "Mine" not in user["content"]  # document titles stay on the server


# ---------- end to end ----------

HBA1C = result(
    test_name="HbA1c",
    value_text="6.1",
    value_numeric=6.1,
    unit="%",
    reference_range_text="4.0 - 5.6",
    reference_low=4.0,
    reference_high=5.6,
    source_text="HbA1c 6.1 % 4.0 - 5.6",
)
AI_SUMMARY = {
    "sections": [
        section("overview", sentence("Your lab report has 2 tests.", "F1")),
        section("results", sentence("Your HbA1c of 6.1 % is above the range 4.0 - 5.6 printed on the report.", "F1")),
        section("results", sentence("Your cholesterol of 240 is high.", "F1")),  # not in the records: dropped
    ],
    "explanations": [{"term": "HbA1c", "text": "A blood test that reflects average blood sugar.", "fact_ids": ["F1"]}],
}


@pytest.fixture
def ai(app, monkeypatch):
    """Summaries switched on, answered by a fake Groq client."""
    monkeypatch.setattr(get_settings(), "extraction_enabled", True)
    fake = FakeGroq(response(AI_SUMMARY))
    app.dependency_overrides[provide_ai_client] = lambda: fake
    return fake


@pytest.fixture
def asha(client, db, storage_dir):
    return make_user(client, "asha@example.com")


def read_report(client, headers, label="1"):
    document_id = upload_report(client, headers, label)
    run_worker(get_settings(), response(payload([result(), HBA1C])))
    return document_id


@pytest.mark.integration
def test_history_summary_is_written_checked_and_cited(client, asha, db, ai):
    document_id = read_report(client, asha)

    before = client.get("/api/v1/summaries/history", headers=asha).json()
    assert (before["enabled"], before["can_create"], before["summary"]) == (True, True, None)

    created = client.post("/api/v1/summaries/history", headers=asha)
    assert created.status_code == 201
    body = created.json()
    summary = body["summary"]
    assert body["stale"] is False
    assert [s["key"] for s in summary["sections"]] == ["overview", "results"]
    assert summary["sections"][1]["sentences"] == [
        {
            "text": "Your HbA1c of 6.1 % is above the range 4.0 - 5.6 printed on the report.",
            "kind": "record",
            "fact_ids": ["F1"],
        }
    ]
    assert summary["dropped_count"] == 1  # the invented cholesterol sentence
    assert summary["explanations"][0]["term"] == "HbA1c"
    source = summary["sources"]["F1"]
    assert (source["kind"], source["source_document_id"], source["date"]) == ("lab_results", document_id, "2026-03-14")
    assert source["source_document_title"] == "Synthetic report 1"
    # Rule-based checks travel with the summary, separate from the AI's sentences.
    assert any("not given" in insight["text"] for insight in summary["insights"])

    # What was sent: facts only, no email or document title.
    [request] = ai.requests
    sent = request["messages"][1]["content"]
    assert "HbA1c 6.1 %" in sent
    assert "asha@example.com" not in sent and "Synthetic report 1" not in sent

    # Stored with its versions, and shown again on the next visit.
    stored = db.scalars(select(AiSummary)).one()
    assert (stored.scope, stored.prompt_version, stored.model_version) == ("history", "summary-v3", "qwen/qwen3.8-27b")
    assert client.get("/api/v1/summaries/history", headers=asha).json()["summary"]["id"] == summary["id"]


@pytest.mark.integration
def test_new_records_mark_the_summary_out_of_date(client, asha, ai):
    read_report(client, asha, "1")
    client.post("/api/v1/summaries/history", headers=asha)

    read_report(client, asha, "2")

    assert client.get("/api/v1/summaries/history", headers=asha).json()["stale"] is True


@pytest.mark.integration
def test_document_summary(client, asha, ai):
    document_id = read_report(client, asha)
    unread = upload_report(client, asha, "2")  # queued, not read

    created = client.post(f"/api/v1/documents/{document_id}/summary", headers=asha)
    assert created.status_code == 201
    assert created.json()["summary"]["scope"] == "document"
    assert client.get(f"/api/v1/documents/{document_id}/summary", headers=asha).json()["summary"] is not None

    state = client.get(f"/api/v1/documents/{unread}/summary", headers=asha).json()
    assert (state["can_create"], state["summary"]) == (False, None)
    assert client.post(f"/api/v1/documents/{unread}/summary", headers=asha).status_code == 409

    ravi = make_user(client, "ravi@example.com")
    assert client.get(f"/api/v1/documents/{document_id}/summary", headers=ravi).status_code == 404
    assert client.post(f"/api/v1/documents/{document_id}/summary", headers=ravi).status_code == 404


@pytest.mark.integration
def test_deleting_a_document_removes_summaries_that_used_it(client, asha, db, ai):
    document_id = read_report(client, asha)
    client.post("/api/v1/summaries/history", headers=asha)
    client.post(f"/api/v1/documents/{document_id}/summary", headers=asha)

    assert client.delete(f"/api/v1/documents/{document_id}", headers=asha).status_code == 204

    assert db.scalars(select(AiSummary)).all() == []
    assert client.get("/api/v1/summaries/history", headers=asha).json()["summary"] is None


@pytest.mark.integration
def test_nothing_is_sent_when_off_empty_or_failing(client, asha, db, app, monkeypatch):
    fake = FakeGroq(connection_error())
    app.dependency_overrides[provide_ai_client] = lambda: fake

    off = client.post("/api/v1/summaries/history", headers=asha)
    assert (off.status_code, off.json()["error"]["message"]) == (503, "AI summaries are turned off on this server.")

    monkeypatch.setattr(get_settings(), "extraction_enabled", True)
    assert client.get("/api/v1/summaries/history", headers=asha).json()["can_create"] is False
    assert client.post("/api/v1/summaries/history", headers=asha).status_code == 409  # no records yet
    assert fake.requests == []

    read_report(client, asha)
    failed = client.post("/api/v1/summaries/history", headers=asha)
    assert failed.status_code == 503
    assert "try again" in failed.json()["error"]["message"]
    assert db.scalars(select(AiSummary)).all() == []
