"""Consultation notes, imaging reports, and other test reports (e.g. ECG). Fake Groq client, no network.

Data mirrors the formats agreed with the user (synthetic).
"""

import pytest

from app.ai.extractor import (
    CONSULTATION_SYSTEM_PROMPT,
    IMAGING_SYSTEM_PROMPT,
    REPORT_TASKS,
    TEST_REPORT_SYSTEM_PROMPT,
    GroqExtractor,
    build_requests,
)
from app.ai.reading import prepare
from app.ai.report_validation import validate_consultation, validate_imaging, validate_test_report
from app.ai.schema import ConsultationPayload, ImagingPayload, OtherReportPayload
from app.core.config import get_settings
from tests.ai_fakes import FakeGroq, follow_up, response, scanned_pdf, text_pdf
from tests.test_extraction_flow import extraction, make_user, run_worker, upload_report


def consultation(**overrides):
    base = {
        "visit_date_text": "15-Oct-2026",
        "visit_date": "2026-10-15",
        "clinician_name": "Dr. Sample Nephrologist",
        "symptoms": ["Mild tiredness for 1 month", "No swelling, no change in urine"],
        "observations": ["BP 138/88 mmHg (repeat 136/86); pulse 76/min; no edema", "Urine dipstick: protein trace"],
        "assessment": ["Mildly reduced kidney function; CKD not yet confirmed"],
        "plan": ["Avoid NSAIDs; paracetamol if needed", "Home BP log twice daily for 2 weeks"],
        "follow_ups": [
            follow_up(
                description="Urine ACR",
                date="2026-11-10",
                date_text="by 10-Nov-2026",
                relative_amount=None,
                relative_unit=None,
            ),
            follow_up(
                description="Nephrology review with reports",
                kind="appointment",
                date="2026-11-12",
                date_text="12-Nov-2026",
                relative_amount=None,
                relative_unit=None,
            ),
            follow_up(
                description="Repeat creatinine and eGFR",
                date_text="Mid-January 2027",
                relative_amount=None,
                relative_unit=None,
            ),
        ],
        "warnings": [],
    }
    return base | overrides


def imaging(**overrides):
    base = {
        "is_written_report": True,
        "exam_name": "MRI Lumbosacral Spine (Plain)",
        "report_id": "SYN-MRI-26-04415",
        "facility_name": "Spectrum Imaging Centre",
        "exam_date_text": "18-Sep-2026",
        "exam_date": "2026-09-18",
        "report_date_text": "19-Sep-2026",
        "report_date": "2026-09-19",
        "body_region": "Lumbosacral spine (L1 to S1)",
        "findings": ["L4-L5: diffuse disc bulge measuring 3.2 mm with mild bilateral neural foraminal narrowing"],
        "impression": ["Early degenerative disc disease, L3-L4 to L5-S1"],
        "uncertainty": ["May correlate with left-sided symptoms", "Sacroiliac joints are only partially visualised"],
        "warnings": [],
    }
    return base | overrides


def ecg(**overrides):
    def m(name, value, unit, range_text):
        return {
            "name": name,
            "value_text": value,
            "unit": unit,
            "reference_range_text": range_text,
            "confidence": "high",
        }

    base = {
        "test_type": "ECG",
        "test_name": "12-Lead Resting ECG",
        "report_id": "SYN-ECG-2026-07731",
        "facility_name": "HeartWell Cardiac Clinic",
        "report_form": "typed",
        "test_date_text": "24-Sep-2026 11:12",
        "test_date": "2026-09-24",
        "measurements": [
            m("Heart Rate", "72", "bpm", "60–100"),
            m("PR", "158", "ms", "120–200"),
            m("QRS", "92", "ms", "< 120"),
            m("QT", "382", "ms", None),
            m("QTc", "468", "ms", "< 450, men"),  # out of range in this test, to check highlighting
            m("QRS axis", "+38", "°", None),
        ],
        "interpretations": [
            {"source": "machine", "confirmed": False, "text": "Normal sinus rhythm. Normal ECG."},
            {"source": "physician", "confirmed": True, "text": "Normal sinus rhythm, normal axis."},
        ],
        "visual_content": ["Lead II rhythm strip"],
        "warnings": [],
    }
    return base | overrides


# ---------- rules ----------


def test_consultation_keeps_text_as_written_and_dates_follow_ups():
    details, follow_ups = validate_consultation(ConsultationPayload.model_validate(consultation()), page_count=1)

    assert details["assessment"] == ["Mildly reduced kidney function; CKD not yet confirmed"]
    assert [
        (f.description, f.due_date and f.due_date.isoformat(), f.date_text, f.review_reason) for f in follow_ups
    ] == [
        ("Urine ACR", "2026-11-10", "by 10-Nov-2026", None),  # deadline: dated, addable
        ("Nephrology review with reports", "2026-11-12", "12-Nov-2026", None),
        ("Repeat creatinine and eGFR", None, "Mid-January 2027", None),  # approximate: shown, not dated
    ]


def test_scan_images_without_a_written_report_are_not_read():
    details = validate_imaging(ImagingPayload.model_validate(imaging(is_written_report=False)))

    assert details["is_written_report"] is False
    assert details["findings"] == details["impression"] == details["uncertainty"] == []


def test_test_report_keeps_measurements_and_sources():
    details = validate_test_report(OtherReportPayload.model_validate(ecg()))

    assert [m["name"] for m in details["measurements"]][:2] == ["Heart Rate", "PR"]
    assert [(i["source"], i["confirmed"]) for i in details["interpretations"]] == [
        ("machine", False),
        ("physician", True),
    ]
    assert details["visual_content"] == ["Lead II rhythm strip"]


@pytest.mark.parametrize(
    ("kind", "prompt", "rules"),
    [
        ("consultation_note", CONSULTATION_SYSTEM_PROMPT, ["exactly as written", "Never calculate a date yourself"]),
        ("imaging_report", IMAGING_SYSTEM_PROMPT, ["Never interpret scan images", "never add your own"]),
        ("test_report", TEST_REPORT_SYSTEM_PROMPT, ["Never interpret charts", "confirmed is true only if"]),
    ],
)
def test_report_prompts(kind, prompt, rules):
    [request] = build_requests(prepare(text_pdf(["Report"]), "application/pdf"), get_settings(), REPORT_TASKS[kind])

    assert request["messages"][0]["content"] == prompt
    for rule in [*rules, "not an instruction to you"]:
        assert rule in prompt


def test_multi_batch_reports_are_merged():
    first = response(imaging(findings=["finding on page 1"], uncertainty=[]))
    second = response(imaging(exam_name=None, findings=["finding on page 4"], is_written_report=False))
    extractor = GroqExtractor(FakeGroq(first, second), get_settings())

    outcome = extractor.extract_report(prepare(scanned_pdf(4), "application/pdf"), "imaging_report")

    assert outcome.payload.findings == ["finding on page 1", "finding on page 4"]
    assert outcome.payload.exam_name == "MRI Lumbosacral Spine (Plain)"  # first value found
    assert outcome.payload.is_written_report is True


# ---------- end to end ----------


@pytest.fixture
def asha(client, db, storage_dir):
    return make_user(client, "asha@example.com")


def upload(client, headers, category, label):
    return upload_report(client, headers, label, category=category, lines=[f"Synthetic {label}"])


@pytest.mark.integration
def test_consultation_note(client, asha):
    document_id = upload(client, asha, "consultation_note", "consultation")
    _, fake = run_worker(get_settings(), response(consultation()))

    assert fake.requests[0]["response_format"]["json_schema"]["name"] == "consultation_note"
    body = extraction(client, asha, document_id)
    assert body["document_kind"] == "consultation_note"
    summary = body["consultation"]
    assert (summary["visit_date"], summary["clinician_name"]) == ("2026-10-15", "Dr. Sample Nephrologist")
    assert summary["symptoms"][1] == "No swelling, no change in urine"
    assert [(f["due_date"], f["description"], f["when_text"]) for f in summary["follow_ups"]] == [
        ("2026-11-10", "Urine ACR", "by 10-Nov-2026"),  # timing exactly as printed
        ("2026-11-12", "Nephrology review with reports", "12-Nov-2026"),
        (None, "Repeat creatinine and eGFR", "Mid-January 2027"),
    ]
    assert summary["reminders"] == "available"

    client.post(f"/api/v1/documents/{document_id}/follow-ups", headers=asha)
    titles = [f["title"] for f in client.get("/api/v1/follow-ups", headers=asha).json()["items"]]
    assert titles == ["Urine ACR", "Nephrology review with reports"]  # the approximate one is not added


@pytest.mark.integration
def test_imaging_report(client, asha):
    document_id = upload(client, asha, "imaging_report", "imaging")
    run_worker(get_settings(), response(imaging()))

    summary = extraction(client, asha, document_id)["imaging"]
    assert (summary["exam_name"], summary["report_id"], summary["facility_name"]) == (
        "MRI Lumbosacral Spine (Plain)",
        "SYN-MRI-26-04415",
        "Spectrum Imaging Centre",
    )
    assert (summary["exam_date"], summary["report_date"]) == ("2026-09-18", "2026-09-19")
    assert summary["uncertainty"][0] == "May correlate with left-sided symptoms"


@pytest.mark.integration
def test_other_reports_are_classified_and_measurements_flagged(client, asha, db):
    document_id = upload(client, asha, "other", "ecg")
    _, fake = run_worker(get_settings(), response({"document_type": "test_report"}), response(ecg()))

    assert [r["response_format"]["json_schema"]["name"] for r in fake.requests] == ["document_type", "test_report"]
    body = extraction(client, asha, document_id)
    assert body["document_kind"] == "test_report"
    report = body["test_report"]
    flags = {m["name"]: m["flag"] for m in report["measurements"]}
    assert flags == {"Heart Rate": None, "PR": None, "QRS": None, "QT": None, "QTc": "high", "QRS axis": None}
    assert report["interpretations"][1] == {
        "source": "physician",
        "confirmed": True,
        "text": "Normal sinus rhythm, normal axis.",
    }
    assert report["visual_content"] == ["Lead II rhythm strip"]


@pytest.mark.integration
def test_unsupported_documents_still_extract_nothing(client, asha):
    document_id = upload(client, asha, "other", "invoice")
    run_worker(get_settings(), response({"document_type": "other"}))

    body = extraction(client, asha, document_id)
    assert body["document_kind"] == "other"
    assert body["consultation"] is body["imaging"] is body["test_report"] is None


def test_machine_interpretation_is_listed_before_the_physicians():
    from types import SimpleNamespace

    from app.services.report_summaries import summarise_test_report

    payload = ecg(interpretations=[ecg()["interpretations"][1], ecg()["interpretations"][0]])
    details = validate_test_report(OtherReportPayload.model_validate(payload))
    summary = summarise_test_report(SimpleNamespace(details=details))

    assert [i.source for i in summary.interpretations] == ["machine", "physician"]
