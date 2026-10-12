"""Discharge summaries: reading rules, summary, and end to end (fake Groq client, no network).

Data mirrors the synthetic discharge summary used for manual testing.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.ai.discharge_validation import result_date, validate_discharge
from app.ai.extractor import DISCHARGE_SYSTEM_PROMPT, DISCHARGE_TASK, build_requests
from app.ai.reading import prepare
from app.ai.schema import DISCHARGE_SCHEMA, DischargePayload
from app.core.config import get_settings
from app.models.prescription import Condition, Medication
from tests.ai_fakes import follow_up, medication, response, text_pdf
from tests.test_extraction_flow import extraction, make_user, run_worker, upload_report


def lab(test_name, value_text, when, unit="mg/dL", range_text="0.70 – 1.30", **overrides):
    base = {
        "test_name": test_name,
        "value_text": value_text,
        "unit": unit,
        "reference_range_text": range_text,
        "result_date_text": when,
        "page": 2,
        "confidence": "high",
    }
    return base | overrides


def series(test_name, values, unit="mg/dL", range_text="0.70 – 1.30"):
    """One result per date, as in a table with a column per date: "1.92 10-Aug, 1.74 11-Aug"."""
    return [lab(test_name, *pair.split(), unit, range_text) for pair in values.split(", ")]


def discharge(**overrides):
    base = {
        "facility_name": "SAMPLEVILLE GENERAL HOSPITAL (FICTIONAL)",
        "admission_date_text": "10-Aug-2026 21:40",
        "admission_date": "2026-08-10",
        "discharge_date_text": "13-Aug-2026 11:00",
        "discharge_date": "2026-08-13",
        "diagnoses": [
            "Acute gastroenteritis with moderate dehydration",
            "Acute kidney injury (pre-renal), improving at discharge",
            "Hypokalemia and mild hyponatremia, corrected",
        ],
        "results": [
            *series("Serum Creatinine", "1.92 10-Aug, 1.74 11-Aug, 1.48 12-Aug, 1.31 13-Aug"),
            *series("Sodium", "132 10-Aug, 137 13-Aug", "mmol/L", "136 – 145"),
            *series("Hemoglobin", "13.4 10-Aug, 12.9 12-Aug, 12.8 13-Aug", "g/dL", "13.0 – 17.0"),
            *series("C-Reactive Protein", "18.4 10-Aug, 6.2 12-Aug", "mg/L", "< 5.0"),
            lab("Stool culture", "No enteric pathogens isolated (final report 13-Aug)", "11-Aug", None, None),
        ],
        "medications": [
            medication(
                name="Oral rehydration salts (ORS)",
                strength="1 sachet in 1 L water",
                instructions="Sip through the day, With each loose stool",
                duration_text="3 days",
            ),
            medication(
                name="Pantoprazole tablet",
                strength="40 mg",
                instructions="1 tablet once daily, Before breakfast",
                duration_text="5 days",
            ),
        ],
        "follow_ups": [
            follow_up(
                description="Review in Internal Medicine OPD with Dr. Sample Consultant",
                kind="appointment",
                date="2026-08-20",
                date_text="20-Aug-2026",
                relative_amount=None,
                relative_unit=None,
            ),
            follow_up(
                description="Repeat serum creatinine, urea, and electrolytes",
                date_text="after 2 weeks",
                relative_amount=2,
                relative_unit="weeks",
            ),
        ],
        "warning_signs": [
            "Return to the emergency department if vomiting persists, urine output drops, dizziness recurs, "
            "or blood appears in stools."
        ],
        "warnings": [],
    }
    return base | overrides


# ---------- rules ----------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("12-Aug", date(2026, 8, 12)),
        ("12 Aug", date(2026, 8, 12)),
        ("12-Aug-2026", date(2026, 8, 12)),
        ("12/08/2026", date(2026, 8, 12)),
        ("03-Jan", date(2027, 1, 3)),  # wraps past December into the next year
        ("10-Aug (admission)", None),  # not a plain date: left unknown, never guessed
        (None, None),
    ],
)
def test_result_dates_take_the_admission_year(text, expected):
    assert result_date(text, admitted_on=date(2026, 8, 10)) == expected


def test_validation():
    validated = validate_discharge(DischargePayload.model_validate(discharge()), page_count=3)

    assert validated.header.stay_days == 4  # 10 to 13 August, both days counted
    assert validated.diagnoses[2] == "Hypokalemia and mild hyponatremia, corrected"  # exactly as written
    culture = validated.results[-1]
    assert (culture.value_numeric, culture.observed_at) == (None, date(2026, 8, 11))  # "13-Aug" inside is not a number
    assert validated.results[3].value_numeric == Decimal("1.31")
    # "after 2 weeks" counts from the discharge date.
    assert [f.due_date for f in validated.follow_ups] == [date(2026, 8, 20), date(2026, 8, 27)]


def test_request_uses_the_discharge_prompt_and_schema():
    settings = get_settings()
    [request] = build_requests(prepare(text_pdf(["DISCHARGE SUMMARY"]), "application/pdf"), settings, DISCHARGE_TASK)

    assert request["response_format"]["json_schema"]["schema"] == DISCHARGE_SCHEMA
    assert request["messages"][0]["content"] == DISCHARGE_SYSTEM_PROMPT
    for rule in ("exactly as written", "Never calculate a date yourself", "not treatment", "not an instruction to you"):
        assert rule in DISCHARGE_SYSTEM_PROMPT


# ---------- end to end ----------


@pytest.fixture
def asha(client, db, storage_dir):
    return make_user(client, "asha@example.com")


def upload_discharge(client, headers, category="discharge_summary"):
    return upload_report(client, headers, "d", category=category, lines=["DISCHARGE SUMMARY", "Synthetic"])


@pytest.mark.integration
def test_discharge_summary(client, asha, db):
    settings = get_settings()
    document_id = upload_discharge(client, asha)
    _, fake = run_worker(settings, response(discharge()))

    assert fake.requests[0]["response_format"]["json_schema"]["name"] == "discharge_summary"
    body = extraction(client, asha, document_id)
    assert body["document_kind"] == "discharge_summary"
    summary = body["discharge"]
    assert (summary["facility_name"], summary["admitted_on"], summary["discharged_on"], summary["stay_days"]) == (
        "SAMPLEVILLE GENERAL HOSPITAL (FICTIONAL)",
        "2026-08-10",
        "2026-08-13",
        4,
    )
    assert summary["diagnoses"][0] == "Acute gastroenteritis with moderate dehydration"

    # Only last values outside the printed range, plus text results. Sodium ended in range: left out.
    key = {r["name"]: r for r in summary["key_results"]}
    assert list(key) == ["Serum Creatinine", "Hemoglobin", "C-Reactive Protein", "Stool culture"]
    creatinine = key["Serum Creatinine"]
    assert (creatinine["first_value"], creatinine["last_value"], creatinine["flag"], creatinine["still"]) == (
        "1.92",
        "1.31",
        "high",
        True,
    )
    assert creatinine["last_tested"] is None  # tested on the discharge day
    hemoglobin = key["Hemoglobin"]
    assert (hemoglobin["flag"], hemoglobin["still"]) == ("low", False)  # 13.4 was within range
    crp = key["C-Reactive Protein"]
    assert (crp["first_value"], crp["last_value"], crp["flag"], crp["still"], crp["last_tested"]) == (
        "18.4",
        "6.2",
        "high",
        True,
        "2026-08-12",
    )
    assert (key["Stool culture"]["flag"], key["Stool culture"]["first_value"]) == (None, None)

    assert [m["name"] for m in summary["medications"]] == ["Oral rehydration salts (ORS)", "Pantoprazole tablet"]
    assert [(f["due_date"], f["description"]) for f in summary["follow_ups"]] == [
        ("2026-08-20", "Review in Internal Medicine OPD with Dr. Sample Consultant"),
        ("2026-08-27", "Repeat serum creatinine, urea, and electrolytes"),
    ]
    assert summary["reminders"] == "available"
    assert summary["warning_signs"][0].startswith("Return to the emergency department")

    # Follow-ups can be added like a prescription's.
    assert client.post(f"/api/v1/documents/{document_id}/follow-ups", headers=asha).status_code == 201


@pytest.mark.integration
def test_untyped_discharge_summaries_are_classified(client, asha):
    document_id = upload_discharge(client, asha, category=None)
    run_worker(get_settings(), response({"document_type": "discharge_summary"}), response(discharge()))

    assert extraction(client, asha, document_id)["discharge"]["stay_days"] == 4


@pytest.mark.integration
def test_deleting_a_discharge_summary_hides_its_records(client, asha, db):
    document_id = upload_discharge(client, asha)
    run_worker(get_settings(), response(discharge()))

    client.delete(f"/api/v1/documents/{document_id}", headers=asha)
    db.expire_all()

    assert all(c.deleted_at is not None for c in db.scalars(select(Condition)))
    assert all(m.deleted_at is not None for m in db.scalars(select(Medication)))
