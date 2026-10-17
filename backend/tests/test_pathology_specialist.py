"""Pathology and specialist reports: read by the report type chosen at upload. Fake Groq, no network.

Data is fictional, in the agreed templates (2026-10-17).
"""

from datetime import date

import pytest

from app.ai.extractor import PATHOLOGY_TASK, SPECIALIST_TASK, build_requests
from app.ai.readability import NOT_IDENTIFIED
from app.ai.reading import prepare
from app.ai.report_validation import validate_pathology, validate_specialist
from app.ai.schema import PathologyPayload, SpecialistPayload
from app.core.config import get_settings
from tests.ai_fakes import follow_up, response, text_pdf
from tests.test_extraction_flow import extraction, make_user, run_worker
from tests.test_reports import upload


def pathology(**overrides):
    base = {
        "test_name": "Histopathology",
        "specimen_label": "Skin biopsy (left forearm)",
        "report_id": "HP-26-1182",
        "facility_name": "Sampleville Pathology Lab",
        "pathologist_name": "Dr. Sample Pathologist",
        "collected_date_text": "02-Oct-2026",
        "collected_date": "2026-10-02",
        "received_date_text": "02-Oct-2026",
        "received_date": "2026-10-02",
        "reported_date_text": "06-Oct-2026",
        "reported_date": "2026-10-06",
        "specimen": ["Skin punch biopsy, left forearm, 4 mm, in formalin"],
        "clinical_history": ["Pigmented lesion, increasing in size for 3 months"],
        "gross_description": ["Single grey-brown skin core measuring 4 x 3 x 3 mm"],
        "microscopic_description": ["Nests of melanocytes at the dermo-epidermal junction", "No dermal invasion seen"],
        "diagnosis": ["Compound melanocytic naevus, completely excised"],
        "tumour_details": ["Margins: clear (nearest 1.2 mm)"],
        "special_tests": ["SOX10: positive", "Ki-67: < 1%"],
        "comments": ["Clinical correlation advised"],
        "warnings": [],
    }
    return base | overrides


def measurement(name, value, unit, range_text, confidence="high"):
    return {
        "name": name,
        "value_text": value,
        "unit": unit,
        "reference_range_text": range_text,
        "confidence": confidence,
    }


def specialist(**overrides):
    base = {
        "test_name": "Echocardiogram",
        "specialty": "Cardiology",
        "report_id": "ECHO-26-0457",
        "facility_name": "Sampleville Heart Centre",
        "reported_by": "Dr. Sample Cardiologist",
        "test_date_text": "09-Oct-2026",
        "test_date": "2026-10-09",
        "reason": ["Breathlessness on exertion"],
        "measurements": [
            measurement("LVEF", "58", "%", "55–70"),
            measurement("LA diameter", "4.3", "cm", "2.7–3.8"),
            measurement("E/A ratio", "0.8", None, None),
        ],
        "findings": ["Mild concentric left ventricular hypertrophy", "Normal valve structure and function"],
        "conclusions": [
            {"source": "physician", "confirmed": True, "text": "Mild LVH with preserved systolic function"}
        ],
        "recommendations": ["Control blood pressure"],
        "follow_ups": [
            follow_up(
                description="Repeat echo",
                date_text="after 12 months",
                relative_amount=12,
                relative_unit="months",
                source_text="Repeat echo after 12 months",
            )
        ],
        "visual_content": ["Echo still images"],
        "warnings": [],
    }
    return base | overrides


# ---------- reading rules ----------


def test_pathology_is_kept_exactly_as_written_and_unreadable_lines_are_marked():
    details = validate_pathology(
        PathologyPayload.model_validate(pathology(diagnosis=["Compound  naevus", "Margin � mm"], comments=[]))
    )

    assert details["diagnosis"] == ["Compound naevus", NOT_IDENTIFIED]  # never a guess
    assert (details["reported_date"], details["reported_text"]) == ("2026-10-06", "06-Oct-2026")
    assert details["comments"] == []  # not in the report: left empty, so not shown


def test_specialist_follow_ups_count_from_the_test_date():
    details, follow_ups = validate_specialist(SpecialistPayload.model_validate(specialist()), page_count=1)

    assert [m["name"] for m in details["measurements"]] == ["LVEF", "LA diameter", "E/A ratio"]
    assert details["conclusions"][0]["source"] == "physician"
    assert [(f.description, f.due_date) for f in follow_ups] == [("Repeat echo", date(2027, 10, 9))]


def test_unreadable_measurement_parts_are_not_identified():
    details, _ = validate_specialist(
        SpecialistPayload.model_validate(specialist(measurements=[measurement("LVEF", "5�", "%", "55–70")])),
        page_count=1,
    )

    assert details["measurements"][0]["value_text"] == NOT_IDENTIFIED
    assert details["measurements"][0]["unclear"] is True


@pytest.mark.parametrize("task", [PATHOLOGY_TASK, SPECIALIST_TASK])
def test_each_reading_uses_its_own_prompt_and_schema(task):
    get_settings.cache_clear()
    document = prepare(text_pdf(["Synthetic report"]), "application/pdf")
    [request] = build_requests(document, get_settings(), task)

    assert request["response_format"]["json_schema"]["name"] == task.schema_name
    assert request["messages"][0]["content"] == task.system_prompt


# ---------- end to end ----------


@pytest.fixture
def asha(client, db, storage_dir):
    return make_user(client, "asha@example.com")


@pytest.mark.integration
def test_pathology_report(client, asha):
    document_id = upload(client, asha, "pathology_report", "pathology")
    _, fake = run_worker(get_settings(), response(pathology()))

    # The chosen report type decides: no classification request.
    assert [r["response_format"]["json_schema"]["name"] for r in fake.requests] == ["pathology_report"]
    body = extraction(client, asha, document_id)
    assert body["document_kind"] == "pathology_report"
    summary = body["pathology"]
    assert (summary["test_name"], summary["specimen_label"], summary["reported_text"]) == (
        "Histopathology",
        "Skin biopsy (left forearm)",
        "06-Oct-2026",
    )
    assert summary["special_tests"] == ["SOX10: positive", "Ki-67: < 1%"]

    # The written diagnosis is suggested in Health Profile and tracked in Diagnoses and Conditions.
    profile = client.get("/api/v1/profile", headers=asha).json()
    assert [s["name"] for s in profile["suggestions"]] == ["Compound melanocytic naevus, completely excised"]
    [issue] = client.get("/api/v1/diagnoses", headers=asha).json()["items"]
    assert (issue["kinds"], issue["last_seen"], issue["profile"]) == (["diagnosis"], "2026-10-06", "to_review")

    timeline = client.get("/api/v1/timeline", headers=asha).json()["items"]
    assert timeline[0]["title"] == "Pathology: Histopathology, Skin biopsy (left forearm)"


@pytest.mark.integration
def test_specialist_report(client, asha):
    document_id = upload(client, asha, "specialist_report", "echo")
    _, fake = run_worker(get_settings(), response(specialist()))

    assert [r["response_format"]["json_schema"]["name"] for r in fake.requests] == ["specialist_report"]
    body = extraction(client, asha, document_id)
    summary = body["specialist"]
    assert (summary["test_name"], summary["specialty"], summary["test_text"]) == (
        "Echocardiogram",
        "Cardiology",
        "09-Oct-2026",
    )
    assert [m["flag"] for m in summary["measurements"]] == [None, "high", None]  # only against a printed range
    assert summary["follow_ups"][0]["due_date"] == "2027-10-09"
    assert summary["reminders"] == "available"

    # A measurement outside its printed range raises an alert, as for other test reports.
    alerts = client.get("/api/v1/alerts", headers=asha).json()["items"]
    assert [a["title"].split(" ")[:3] for a in alerts] == [["LA", "diameter", "4.3"]]
    # The conclusion is tracked in Diagnoses and Conditions.
    [issue] = client.get("/api/v1/diagnoses", headers=asha).json()["items"]
    assert (issue["name"], issue["kinds"]) == ("Mild LVH with preserved systolic function", ["assessment"])

    added = client.post(f"/api/v1/documents/{document_id}/follow-ups", headers=asha)
    assert added.status_code == 201
    assert added.json()["specialist"]["reminders"] == "added"
