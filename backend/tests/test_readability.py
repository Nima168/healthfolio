"""Printed but unreadable parts are shown as "Not identified", never as a guess (app/ai/readability.py)."""

from datetime import date
from types import SimpleNamespace

import pytest

from app.ai.discharge_validation import validate_discharge
from app.ai.prescription_validation import validate_prescription
from app.ai.readability import NOT_IDENTIFIED, check_result, garbled_range, garbled_unit, garbled_value, not_a_result
from app.ai.schema import DischargePayload, ExtractionPayload, PrescriptionPayload
from app.ai.validation import validate_payload
from app.services.lab_summary import classify
from tests.ai_fakes import medication, payload, prescription, result

TODAY = date(2026, 10, 14)


def _labs(*rows):
    return validate_payload(ExtractionPayload.model_validate(payload(list(rows))), 1, TODAY)


# ---------- the rules ----------


@pytest.mark.parametrize("value", ["TENS", "5.7.H", "l3.B", "13.8H", "O.8", "O38", "�35"])
def test_misread_values_are_caught(value):
    assert garbled_value(value, numeric_expected=True)


@pytest.mark.parametrize(
    "value", ["13.8", "<150", "< 7", "7,800", "6.1%", "2-3", "1.020", "Negative", "Not detected", "Pale yellow"]
)
def test_real_values_are_kept(value):
    assert not garbled_value(value, numeric_expected=True)


def test_text_results_without_a_numeric_range_are_kept():
    assert not garbled_value("No enteric pathogens isolated", numeric_expected=False)


@pytest.mark.parametrize("text", ["55:2", "O38   122", "0.3 1.2", "�35"])
def test_misread_ranges_are_caught(text):
    assert garbled_range(text)


@pytest.mark.parametrize(
    "text",
    [
        "3.5 - 5.2",
        "< 5.0",
        "> 40",
        "4,000 - 10,000",
        "0.70 to 1.30",
        "Desirable < 200; Borderline 200-239; High >= 240",
        "Optimal < 100; Near optimal 100-129: Borderline 130-159",
    ],
)
def test_real_ranges_are_kept(text):
    assert not garbled_range(text)


def test_units():
    assert not any(garbled_unit(u) for u in ["10^3/uL", "10*3/uL", "mg/dL", "mL/min/1.73 m2", "%", "x10^9/L"])
    assert garbled_unit('mg"dL') and garbled_unit("mg/d�")


def test_header_lines_are_not_results():
    assert not_a_result("Report Date", "15/09/2026", None, None)
    assert not_a_result("Collected", "05-Oct-2026 08:15", None, None)
    assert not not_a_result("Haemoglobin", "13.8", "g/dL", "13.0 - 17.0")


def test_declared_parts_are_replaced_even_if_text_looks_fine():
    assert check_result("13.8", "g/dL", "12.0 - 15.5", ["unit"]) == ("13.8", NOT_IDENTIFIED, "12.0 - 15.5", ["unit"])


# ---------- lab results ----------


def test_a_misread_value_is_not_identified_flagged_and_not_compared():
    [item] = _labs(
        result(test_name="MCV", value_text="TENS", value_numeric=None, unit="fL", reference_range_text="83.0 - 101.0")
    )

    assert item.value_text == NOT_IDENTIFIED and item.value_numeric is None
    assert "value_not_identified" in item.findings and item.needs_review
    row = SimpleNamespace(
        reference_range_text=item.reference_range_text,
        value_numeric=item.value_numeric,
        value_text=item.value_text,
        validation_findings=item.findings,
        confidence=item.confidence,
    )
    assert classify(row)[0] == "invalid"


def test_a_misread_range_is_not_identified_and_never_compared():
    [item] = _labs(result(value_text="3.8", value_numeric=3.8, reference_range_text="�35", reference_high=35.0))

    assert item.reference_range_text == NOT_IDENTIFIED
    assert item.reference_high is None and "range_not_identified" in item.findings and item.needs_review


def test_a_part_the_model_cannot_read_is_not_identified_not_missing():
    [item] = _labs(result(unit=None, reference_range_text=None, unreadable=["unit", "range"]))

    # Printed but unreadable: "Not identified", not "Not mentioned" (which would wrongly say it is not printed).
    assert (item.unit, item.reference_range_text) == (NOT_IDENTIFIED, NOT_IDENTIFIED)


def test_an_unreadable_value_keeps_the_row():
    [item] = _labs(result(value_text="", value_numeric=None, unreadable=["value"]))

    assert item.value_text == NOT_IDENTIFIED and item.needs_review


def test_a_report_date_read_as_a_result_is_removed():
    items = _labs(
        result(),
        result(
            test_name="Report Date", value_text="15/09/2026", value_numeric=None, unit=None, reference_range_text=None
        ),
    )

    assert [i.name for i in items] == ["Haemoglobin"]


def test_a_clear_result_is_unchanged():
    [item] = _labs(result())

    assert (item.value_text, item.unit, item.reference_range_text) == ("13.8", "g/dL", "12.0 - 15.5")
    assert not item.needs_review


# ---------- discharge results and medicines ----------


def test_discharge_results_use_the_same_rules():
    body = {
        "facility_name": "Lakeside General Hospital",
        "admission_date_text": None,
        "admission_date": None,
        "discharge_date_text": None,
        "discharge_date": None,
        "diagnoses": [],
        "results": [
            {
                "test_name": "Serum Creatinine",
                "value_text": "1.31",
                "unit": "mg/dL",
                "reference_range_text": "55:2",
                "result_date_text": None,
                "page": 1,
                "confidence": "high",
            },
            {
                "test_name": "Date",
                "value_text": "13-Aug-2026",
                "unit": None,
                "reference_range_text": None,
                "result_date_text": None,
                "page": 1,
                "confidence": "high",
            },
        ],
        "medications": [],
        "follow_ups": [],
        "warning_signs": [],
        "warnings": [],
    }
    [creatinine] = validate_discharge(DischargePayload.model_validate(body), 1).results

    assert creatinine.reference_range_text == NOT_IDENTIFIED
    assert creatinine.not_identified == ["range"] and creatinine.needs_review


def test_medicine_details_the_model_cannot_read_are_not_identified():
    body = prescription([medication(strength=None, unreadable=["strength"])], [])
    _, [medicine], _ = validate_prescription(PrescriptionPayload.model_validate(body), 1)

    assert medicine.strength == NOT_IDENTIFIED
    assert "Not identified" in medicine.review_reason
