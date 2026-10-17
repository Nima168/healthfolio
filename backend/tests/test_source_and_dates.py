"""Dates shown as printed, the empty-answer re-read, and checking values against their own line.

Fake Groq client and synthetic text only (no network, no database).
"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.ai.dates import ambiguous, document_date
from app.ai.discharge_validation import validate_discharge
from app.ai.extractor import ExtractionError, GroqExtractor
from app.ai.prescription_validation import AMBIGUOUS_BASE, AMBIGUOUS_DATE, validate_prescription
from app.ai.readability import NOT_IDENTIFIED
from app.ai.reading import PageImage, PageText, PreparedDocument
from app.ai.report_validation import validate_consultation, validate_imaging
from app.ai.schema import ConsultationPayload, DischargePayload, ExtractionPayload, ImagingPayload, PrescriptionPayload
from app.ai.source_check import SourceText, check_all, contains, names
from app.ai.validation import validate_payload
from app.core.config import get_settings
from app.services.lab_summary import classify
from tests.ai_fakes import FakeGroq, follow_up, medication, payload, prescription, response, result
from tests.test_discharge import discharge
from tests.test_reports import consultation, imaging

TODAY = date(2026, 10, 14)


def text_document(*lines: str, page: int = 1) -> PreparedDocument:
    return PreparedDocument(page_count=page, texts=[PageText(page, "\n".join(lines), "ocr", 92)])


# ---------- dates exactly as printed ----------


@pytest.mark.parametrize(
    ("printed", "expected"),
    [
        ("02/09/26", True),  # 2 September or 9 February
        ("2.9.2026", True),
        ("Date: 12-08-2026 10:30", True),
        ("25/09/26", False),  # 25 cannot be a month
        ("05/05/2026", False),  # the same either way
        ("02-Sep-2026", False),
        ("2026-09-02", False),  # year first: always year-month-day
        ("12-Mar-2026 13:10", False),
        ("after 4 weeks", False),
        (None, False),
    ],
)
def test_ambiguous_dates(printed, expected):
    assert ambiguous(printed) is expected


def test_an_ambiguous_date_keeps_no_calendar_date():
    assert document_date("2026-09-02", "02/09/26") is None
    assert document_date("2026-09-25", "25/09/26") == date(2026, 9, 25)
    assert document_date(None, "02-Sep-2026") is None


def test_prescription_with_an_ambiguous_date_does_not_guess_follow_up_dates():
    body = prescription(
        prescription_date_text="02/09/26",
        prescription_date="2026-09-02",
        follow_ups=[
            follow_up(),  # "after 4 weeks", counted from the prescription date
            follow_up(description="CBC", date="2026-10-11", date_text="on 10/11/26", relative_amount=None),
            follow_up(description="ECG", date="2026-11-25", date_text="on 25/11/26", relative_amount=None),
        ],
    )
    header, _, follow_ups = validate_prescription(PrescriptionPayload.model_validate(body), 1)

    assert (header.prescribed_on, header.date_text, header.date_ambiguous) == (None, "02/09/26", True)
    after, cbc, ecg = follow_ups
    assert (after.due_date, after.review_reason) == (None, AMBIGUOUS_BASE)
    assert (cbc.due_date, cbc.date_text, cbc.review_reason) == (None, "on 10/11/26", AMBIGUOUS_DATE)
    assert (ecg.due_date, ecg.due_date_basis, ecg.review_reason) == (date(2026, 11, 25), "written", None)


def test_lab_report_with_an_ambiguous_date_is_not_dated():
    body = payload(report_date_text="03/04/2026", report_date="2026-04-03")
    [item] = validate_payload(ExtractionPayload.model_validate(body), 1, TODAY)

    assert item.observed_at is None
    assert "ambiguous_date" in item.findings and "date_from_report" not in item.findings


def test_a_lab_result_date_is_kept_only_when_unambiguous():
    rows = [
        result(test_name="Haemoglobin", result_date="2026-04-03", result_date_text="03/04/2026"),
        result(test_name="Ferritin", result_date="2026-04-23", result_date_text="23/04/2026"),
    ]
    first, second = validate_payload(ExtractionPayload.model_validate(payload(rows)), 1, TODAY)

    assert first.observed_at is None and "ambiguous_date" in first.findings  # never the report date instead
    assert second.observed_at == date(2026, 4, 23)


def test_a_value_far_outside_its_range_is_still_grouped_but_marked():
    from app.services.lab_summary import FAR_OUTSIDE_NOTE, summarise

    def row(name, value, range_text):
        return SimpleNamespace(
            name=name,
            value_text=value,
            value_numeric=Decimal(value),
            unit="g/dL",
            reference_range_text=range_text,
            validation_findings=[],
            confidence="high",
        )

    summary = summarise([row("Total Protein", "162", "6.4 - 8.3"), row("Albumin", "6.0", "3.5 - 5.2")], None)
    protein, albumin = summary.above
    assert protein.note == FAR_OUTSIDE_NOTE and albumin.note is None


def test_other_documents_keep_dates_only_when_unambiguous():
    details, _ = validate_consultation(
        ConsultationPayload.model_validate(consultation(visit_date="2026-10-08", visit_date_text="08/10/2026")), 1
    )
    assert (details["visit_date"], details["visit_text"]) == (None, "08/10/2026")

    imaging_details = validate_imaging(
        ImagingPayload.model_validate(imaging(exam_date="2026-09-18", exam_date_text="18/09/2026"))
    )
    assert (imaging_details["exam_date"], imaging_details["exam_text"]) == ("2026-09-18", "18/09/2026")


def test_discharge_with_an_ambiguous_date_counts_no_follow_up_from_it():
    body = discharge(discharge_date_text="03/08/2026", discharge_date="2026-08-03")
    validated = validate_discharge(DischargePayload.model_validate(body), 1)

    assert (validated.header.discharged_on, validated.header.discharged_text) == (None, "03/08/2026")
    assert validated.header.stay_days is None
    calculated = [f for f in validated.follow_ups if f.date_text and "after" in f.date_text]
    assert calculated and all(f.due_date is None and f.review_reason == AMBIGUOUS_BASE for f in calculated)


# ---------- an empty answer is read again ----------

EMPTY = response(payload([]))
FOUND = response(payload([result()]))
PAGE = text_document(*[f"Haemoglobin 13.8 g/dL 12.0 - 15.5 row {n}" for n in range(10)])


def extractor(*replies):
    fake = FakeGroq(*replies)
    return GroqExtractor(fake, get_settings()), fake


def test_an_empty_answer_for_a_page_with_text_is_read_again():
    reader, fake = extractor(EMPTY, FOUND)
    outcome = reader.extract(PAGE)

    assert len(fake.requests) == 2
    assert [r.test_name for r in outcome.payload.lab_results] == ["Haemoglobin"]
    assert outcome.input_tokens == 2 * 1200  # both calls are counted


def test_a_second_re_read_is_tried_before_giving_up():
    reader, fake = extractor(EMPTY, EMPTY, FOUND)
    outcome = reader.extract(PAGE)

    assert len(fake.requests) == 3 and len(outcome.payload.lab_results) == 1


def test_three_empty_answers_fail_clearly_instead_of_showing_no_results():
    reader, fake = extractor(EMPTY)  # the fake repeats its last reply
    with pytest.raises(ExtractionError) as failure:
        reader.extract(PAGE)

    assert (failure.value.category, failure.value.transient) == ("ai_empty_output", False)
    assert len(fake.requests) == 3


def test_a_page_with_almost_no_text_may_truly_be_empty():
    reader, fake = extractor(EMPTY)
    outcome = reader.extract(text_document("Synthetic Lab Report", "No results"))

    assert outcome.payload.lab_results == [] and len(fake.requests) == 1


def test_a_page_image_answered_with_nothing_is_read_again():
    image = PreparedDocument(page_count=1, images=[PageImage(1, b"\xff\xd8 fake jpeg")])
    reader, fake = extractor(EMPTY, FOUND)
    reader.extract(image)

    assert len(fake.requests) == 2


# ---------- each value checked against its own line ----------

REPORT = text_document(
    "City Diagnostics - Synthetic Report",
    "Test            Result   Unit    Reference",
    "AST (SGOT)      29       U/L     0 - 40",
    "Ferritin        311      ng/mL   30 - 400",
    "Haemoglobin     13.8     g/dL    12.0 -",
    "                                 15.5",
)


def lab(name, value, unit, range_text, **overrides):
    return (
        result(test_name=name, value_text=value, value_numeric=float(value), unit=unit, reference_range_text=range_text)
        | overrides
    )


def judged(item):
    """The lab summary's verdict for a validated result, as it will be once stored."""
    return classify(SimpleNamespace(**vars(item), validation_findings=item.findings))


def read(document, *results):
    validated = validate_payload(
        ExtractionPayload.model_validate(payload(list(results))), 1, TODAY, SourceText.of(document)
    )
    return {item.name: item for item in validated}


def test_matching_helpers():
    assert names("Ferritin", "Ferritim 311 ng/mL") and names("AST (SGOT)", "AST 29 U/L")
    assert not names("ALT (SGPT)", "AST (SGOT) 29 U/L")
    assert contains("AST 29 U/L 0-40", "0 - 40") and contains("Hb 13.8 g/dL", "13.8")
    assert not contains("Ferritin 311", "31") and not contains("Hb 15.4", "5.4") and not contains("Hb 5.4", "5")


def test_a_value_from_another_row_is_not_identified_and_never_judged():
    items = read(
        REPORT,
        lab("AST (SGOT)", "311", "U/L", "0 - 40"),  # Ferritin's value: swapped rows
        lab("Ferritin", "29", "ng/mL", "30 - 400"),
    )

    for name in ("AST (SGOT)", "Ferritin"):
        item = items[name]
        assert item.value_text == NOT_IDENTIFIED and item.value_numeric is None
        assert {"value_not_identified", "value_in_other_row"} <= set(item.findings) and item.needs_review
        status, reason = judged(item)
        assert status == "invalid" and "another row" in reason


def test_values_on_their_own_line_pass_and_a_wrapped_range_is_accepted():
    items = read(
        REPORT,
        lab("AST (SGOT)", "29", "U/L", "0 - 40"),
        lab("Ferritin", "311", "ng/mL", "30 - 400"),
        lab("Haemoglobin", "13.8", "g/dL", "12.0 - 15.5"),  # the range wraps onto the next line
    )

    assert all(item.findings == ["date_from_report"] for item in items.values()), {
        n: i.findings for n, i in items.items()
    }
    assert judged(items["Haemoglobin"]) == ("within", None)


def test_a_value_nowhere_on_its_line_is_flagged_and_not_compared():
    items = read(
        REPORT,
        lab("AST (SGOT)", "92", "U/L", "0 - 40"),
        lab("Ferritin", "311", "ng/mL", "30 - 400"),
        lab("Haemoglobin", "13.8", "g/dL", "12.0 - 15.5"),
    )

    assert "value_not_matched" in items["AST (SGOT)"].findings and items["AST (SGOT)"].value_text == "92"
    assert judged(items["AST (SGOT)"])[0] == "invalid"


@pytest.mark.parametrize("stray", ["�", "£", "£ "])
def test_a_part_printed_beside_a_stray_symbol_is_not_identified(stray):
    # OCR misread "≤" in "≤ 3.5" and lost the decimal point; the model dropped the symbol and returned "35".
    scan = text_document(
        f"LDL / HDL Ratio    3.8 H*    ratio    {stray}35",
        "Total Cholesterol / HDL Ratio    5.7    ratio    < 5.0",
    )
    items = read(
        scan,
        lab("LDL / HDL Ratio", "3.8", "ratio", "35", value_text="3.8 H"),
        lab("Total Cholesterol / HDL Ratio", "5.7", "ratio", "< 5.0"),
    )

    ratio = items["LDL / HDL Ratio"]
    assert ratio.reference_range_text == NOT_IDENTIFIED and ratio.value_text == "3.8 H"
    assert "range_not_identified" in ratio.findings and judged(ratio)[0] == "invalid"
    assert judged(items["Total Cholesterol / HDL Ratio"]) == ("above", None)  # nothing unreadable on its line


def test_a_unit_or_range_off_the_line_is_flagged_for_review_only():
    items = read(REPORT, lab("Ferritin", "311", "ng/mL", "12.0 - 15.5"))

    assert "range_not_matched" in items["Ferritin"].findings and items["Ferritin"].needs_review


def test_an_invented_test_is_flagged():
    items = read(REPORT, lab("Vitamin D", "31", "ng/mL", "30 - 100"))

    assert "name_not_matched" in items["Vitamin D"].findings
    assert judged(items["Vitamin D"])[0] == "invalid"


def test_results_read_from_a_page_image_are_never_judged():
    image = PreparedDocument(page_count=1, images=[PageImage(1, b"jpeg")])
    items = read(image, lab("Ferritin", "29", "ng/mL", "30 - 400"))

    assert "read_from_image" in items["Ferritin"].findings
    status, reason = judged(items["Ferritin"])
    assert status == "invalid" and "page image" in reason


def test_text_not_laid_out_in_rows_is_not_held_against_the_values():
    # Some PDFs give the names column first, then the values column.
    columns = text_document("AST (SGOT)", "Ferritin", "Haemoglobin", "29", "311", "13.8")
    source = SourceText.of(columns)

    outcomes = check_all(source, [("AST (SGOT)", "29", 1), ("Ferritin", "311", 1), ("Haemoglobin", "13.8", 1)])
    assert outcomes == [None, None, None]


def test_a_medicine_strength_from_another_line_is_not_identified():
    document = text_document(
        "1. Atorvastatin 10 mg - once daily at night", "2. Metformin 500 mg - once daily after dinner"
    )
    body = prescription(
        medications=[
            medication(strength="500 mg"),  # Metformin's strength
            medication(name="Metformin", strength="500 mg", instructions="once daily after dinner"),
        ]
    )
    _, medicines, _ = validate_prescription(PrescriptionPayload.model_validate(body), 1, SourceText.of(document))

    atorvastatin, metformin = medicines
    assert atorvastatin.strength == NOT_IDENTIFIED and "strength" in (atorvastatin.review_reason or "")
    assert (metformin.strength, metformin.review_reason) == ("500 mg", None)


def discharge_result(name, value, unit, range_text):
    return {
        "test_name": name,
        "value_text": value,
        "unit": unit,
        "reference_range_text": range_text,
        "result_date_text": "13-Aug",
        "page": 1,
        "confidence": "high",
    }


def test_a_discharge_value_from_another_row_is_not_identified():
    document = text_document("Serum Creatinine 1.31 mg/dL 0.70 - 1.30 13-Aug", "Sodium 137 mmol/L 135 - 145 13-Aug")
    body = discharge(
        results=[
            discharge_result("Serum Creatinine", "137", "mg/dL", "0.70 - 1.30"),  # rows swapped
            discharge_result("Sodium", "1.31", "mmol/L", "135 - 145"),
        ]
    )
    results = validate_discharge(DischargePayload.model_validate(body), 1, SourceText.of(document)).results

    for item in results:
        assert item.value_text == NOT_IDENTIFIED and item.value_numeric is None
        assert item.needs_review and "value_in_other_row" in item.findings


def test_a_discharge_value_off_its_line_is_flagged():
    document = text_document("Serum Creatinine 1.31 mg/dL 0.70 - 1.30 13-Aug")
    body = discharge(results=[discharge_result("Serum Creatinine", "1.81", "mg/dL", "0.70 - 1.30")])
    [creatinine] = validate_discharge(DischargePayload.model_validate(body), 1, SourceText.of(document)).results

    assert (creatinine.value_text, creatinine.unchecked, creatinine.needs_review) == ("1.81", "value_not_matched", True)
