"""Prescription reading rules, summary, and request shape (no database, no network)."""

from datetime import date

import pytest

from app.ai.extractor import (
    CLASSIFY_TASK,
    CLASSIFY_TEXT_CHARS,
    PRESCRIPTION_SYSTEM_PROMPT,
    PRESCRIPTION_TASK,
    GroqExtractor,
    build_requests,
)
from app.ai.prescription_validation import (
    BEFORE_PRESCRIPTION,
    DUPLICATE_MEDICATION,
    NO_BASE_DATE,
    NO_INSTRUCTIONS,
    NO_TIMING,
    UNCLEAR_FOLLOW_UP,
    UNCLEAR_MEDICATION,
    UNREADABLE_DATE,
    add_months,
    needs_second_look,
    validate_prescription,
)
from app.ai.readability import NOT_IDENTIFIED
from app.ai.reading import prepare
from app.ai.schema import PRESCRIPTION_SCHEMA, PrescriptionPayload
from app.core.config import get_settings
from app.models.extraction import ProcessingJob
from app.models.prescription import Medication, Suggestion
from app.services.prescription_summary import addable, summarise_prescription
from tests.ai_fakes import (
    SYNTHETIC_PRESCRIPTION_LINES,
    FakeGroq,
    classification,
    follow_up,
    medication,
    prescription,
    response,
    scanned_pdf,
    text_pdf,
)


@pytest.fixture
def settings():
    get_settings.cache_clear()
    return get_settings()


def _validate(**overrides):
    return validate_prescription(PrescriptionPayload.model_validate(prescription(**overrides)), page_count=1)


# ---------- dates ----------


@pytest.mark.parametrize(
    ("start", "months", "expected"),
    [
        (date(2026, 10, 7), 3, date(2027, 1, 7)),
        (date(2026, 1, 31), 1, date(2026, 2, 28)),  # moved back to the last day of a shorter month
        (date(2028, 1, 31), 1, date(2028, 2, 29)),  # leap year
        (date(2026, 11, 30), 2, date(2027, 1, 30)),
    ],
)
def test_add_months_keeps_calendar_sense(start, months, expected):
    assert add_months(start, months) == expected


def test_relative_follow_ups_are_calculated_from_the_printed_prescription_date():
    header, _, follow_ups = _validate()

    assert header.prescribed_on == date(2026, 10, 7)
    assert header.date_text == "07-Oct-2026" and header.prescriber_name == "Dr. Sample Physician"
    assert [(f.description, f.due_date, f.due_date_basis) for f in follow_ups] == [
        ("Kidney function test", date(2026, 11, 4), "calculated"),  # 4 weeks
        ("doctor visit", date(2026, 11, 4), "calculated"),
        ("CBC", date(2026, 12, 7), "written"),
        ("HbA1c", date(2027, 1, 7), "calculated"),  # 3 calendar months
        ("lipid profile", date(2027, 1, 7), "calculated"),
    ]
    assert all(f.review_reason is None for f in follow_ups)


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"date": None, "relative_amount": None, "relative_unit": None, "date_text": None}, NO_TIMING),
        ({"date": "07/12/2026", "relative_amount": None, "relative_unit": None}, UNREADABLE_DATE),
        ({"confidence": "medium"}, UNCLEAR_FOLLOW_UP),
        ({"relative_amount": 0}, UNCLEAR_FOLLOW_UP),
        ({"relative_amount": 30, "relative_unit": "months"}, UNCLEAR_FOLLOW_UP),  # beyond two years
        ({"date": "2026-09-01", "relative_amount": None, "relative_unit": None}, BEFORE_PRESCRIPTION),
    ],
)
def test_unclear_follow_ups_need_review(overrides, reason):
    _, _, [item] = _validate(follow_ups=[follow_up(**overrides)])

    assert item.review_reason == reason


def test_approximate_timing_is_kept_as_written_without_a_date():
    _, _, [item] = _validate(
        follow_ups=[follow_up(date_text="Mid-January 2027", relative_amount=None, relative_unit=None)]
    )

    assert (item.due_date, item.due_date_basis, item.date_text, item.review_reason) == (
        None,
        None,
        "Mid-January 2027",
        None,
    )


def test_relative_follow_up_without_a_prescription_date_needs_review():
    _, _, [item] = _validate(follow_ups=[follow_up()], prescription_date=None)

    assert (item.due_date, item.review_reason) == (None, NO_BASE_DATE)


# ---------- medicines ----------


def test_clear_medicines_are_kept_exactly_as_written():
    _, medications, _ = _validate()

    assert [(m.name, m.strength, m.instructions, m.duration_text) for m in medications] == [
        ("Atorvastatin", "10 mg", "once daily at night", "90 days"),
        ("Metformin", "500 mg", "once daily after dinner", "90 days"),
        ("Ferrous ascorbate + folic acid", None, "once daily after lunch", "60 days"),
        ("Vitamin D3", "60,000 IU", "once weekly", "8 weeks"),
    ]
    assert all(m.review_reason is None for m in medications)


@pytest.mark.parametrize(
    ("medications", "reasons"),
    [
        ([medication(confidence="low")], [UNCLEAR_MEDICATION]),
        ([medication(name="  ")], [UNCLEAR_MEDICATION]),
        ([medication(instructions=None)], [NO_INSTRUCTIONS]),
        ([medication(), medication(name="atorvastatin")], [None, DUPLICATE_MEDICATION]),
        ([medication(), medication(strength="20 mg")], [None, None]),  # a different strength is not a duplicate
    ],
)
def test_unclear_medicines_need_review(medications, reasons):
    _, validated, _ = _validate(medications=medications)

    assert [m.review_reason for m in validated] == reasons


@pytest.mark.parametrize(
    ("instructions", "duration", "expected"),
    [
        ("1 tablet once daily, At night, 90 days", "90 days", "1 tablet once daily, At night"),
        ("once weekly for 8 weeks", "8 weeks", "once weekly"),
        ("once daily; 60 Days.", "60 days", "once daily"),
        ("once daily, At night", "90 days", "once daily, At night"),  # no copy: unchanged
        ("take for 90 days", None, "take for 90 days"),  # no separate duration: nothing removed
        ("90 days", "90 days", "90 days"),  # nothing else written: kept rather than emptied
        ("once daily x 190 days", "90 days", "once daily x 190 days"),  # part of another number
    ],
)
def test_duration_is_not_repeated_in_instructions(instructions, duration, expected):
    _, validated, _ = _validate(medications=[medication(instructions=instructions, duration_text=duration)])

    assert (validated[0].instructions, validated[0].duration_text) == (expected, duration)


@pytest.mark.parametrize("instructions", ["625mg", "Dose: 625 mg", "dosage - 625 MG"])
def test_instructions_that_only_repeat_the_strength_are_not_identified(instructions):
    # A scan whose Frequency column OCR missed: the model filled instructions with the dose.
    _, [medicine], _ = _validate(
        medications=[medication(strength="625 mg", instructions=instructions, duration_text=None)]
    )

    assert (medicine.strength, medicine.instructions) == ("625 mg", NOT_IDENTIFIED)
    assert "instructions" in medicine.review_reason and "Check the original" in medicine.review_reason


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, False),  # name, strength, instructions, and duration all read
        ({"duration_text": None}, False),  # no duration printed (e.g. "SOS"): nothing to look for
        ({"strength": "625 mg", "instructions": "625 mg"}, True),  # the Frequency column was not read
        ({"instructions": None}, True),
        ({"unreadable": ["duration"], "duration_text": None}, True),
        ({"instructions": "once daily �"}, True),  # garbled by OCR
    ],
)
def test_which_medicines_need_a_second_look(overrides, expected):
    payload = PrescriptionPayload.model_validate(prescription(medications=[medication(**overrides)]))

    assert needs_second_look(payload.medications[0]) is expected


# ---------- summary ----------


def _rows(**overrides):
    header, medications, follow_ups = _validate(**overrides)
    job = ProcessingJob(
        document_date=header.prescribed_on, report_date_text=header.date_text, prescriber_name=header.prescriber_name
    )
    meds = [
        Medication(
            name=m.name,
            strength=m.strength,
            dosage_text=m.instructions,
            duration_text=m.duration_text,
            review_reason=m.review_reason,
        )
        for m in medications
    ]
    suggestions = [
        Suggestion(
            suggested_value=f.description,
            due_date=f.due_date,
            original_text=f.date_text,
            condition_text=f.condition,
            review_reason=f.review_reason,
            status="pending",
        )
        for f in follow_ups
    ]
    return job, meds, suggestions


def test_summary_groups_follow_ups_by_date_in_date_order():
    summary = summarise_prescription(*_rows())

    assert (summary.prescribed_on, summary.prescriber_name) == (date(2026, 10, 7), "Dr. Sample Physician")
    assert len(summary.medications) == 4
    assert [(f.due_date, f.description) for f in summary.follow_ups] == [
        (date(2026, 11, 4), "Kidney function test + doctor visit"),
        (date(2026, 12, 7), "CBC"),
        (date(2027, 1, 7), "HbA1c + lipid profile"),
    ]
    assert not any(line.unclear for line in [*summary.medications, *summary.follow_ups])
    assert summary.reminders == "available"


def test_unclear_items_stay_in_their_section_flagged():
    summary = summarise_prescription(
        *_rows(
            medications=[medication(), medication(name="Metformin", strength="500 mg", confidence="low")],
            follow_ups=[
                follow_up(description="Eye checkup", date_text=None, relative_amount=None),
                follow_up(description="Repeat creatinine", date_text="Mid-January 2027", relative_amount=None),
                follow_up(),
                follow_up(description="X-ray", confidence="low"),
            ],
        )
    )

    assert [(m.name, m.unclear, m.reason) for m in summary.medications] == [
        ("Atorvastatin", False, None),
        ("Metformin", True, UNCLEAR_MEDICATION),
    ]
    # Dated lines in date order (an unclear one is never merged into a clear one); undated last.
    assert [(f.due_date, f.description, f.unclear, f.reason, f.when_text) for f in summary.follow_ups] == [
        (date(2026, 11, 4), "Kidney function test", False, None, "after 4 weeks"),  # timing as written
        (date(2026, 11, 4), "X-ray", True, UNCLEAR_FOLLOW_UP, "after 4 weeks"),
        (None, "Eye checkup", True, NO_TIMING, None),
        (None, "Repeat creatinine", False, None, "Mid-January 2027"),  # approximate: shown, never added
    ]


def test_reminder_state():
    job, meds, suggestions = _rows()
    for suggestion in suggestions:
        suggestion.status = "accepted"
    assert summarise_prescription(job, meds, suggestions).reminders == "added"

    job, meds, _ = _rows()
    assert summarise_prescription(job, meds, []).reminders == "none"


SOS_REVIEW = follow_up(
    description="Review",
    kind="appointment",
    date_text="after 5 days",
    relative_amount=5,
    relative_unit="days",
    condition="if not better/SOS",
    source_text="Review after 5 days if not better/SOS",
)


def test_a_conditional_follow_up_keeps_its_condition_and_is_never_dated():
    _, _, [review] = _validate(follow_ups=[SOS_REVIEW])

    # Only if needed: no calculated date, so it can never show as an overdue appointment.
    assert (review.condition, review.due_date, review.review_reason) == ("if not better/SOS", None, None)


def test_a_conditional_follow_up_is_shown_as_only_if_needed_and_not_added():
    job, meds, suggestions = _rows(follow_ups=[SOS_REVIEW, follow_up()])
    summary = summarise_prescription(job, meds, suggestions)

    lines = {line.description: line for line in summary.follow_ups}
    assert (lines["Review"].condition, lines["Review"].when_text, lines["Review"].unclear) == (
        "if not better/SOS",
        "after 5 days",
        False,
    )
    assert [addable(s) for s in suggestions] == [False, True]  # only the dated follow-up can be added


# ---------- requests ----------


def test_prescription_request_uses_its_own_prompt_and_schema(settings):
    document = prepare(text_pdf(SYNTHETIC_PRESCRIPTION_LINES), "application/pdf")
    [request] = build_requests(document, settings, PRESCRIPTION_TASK)

    assert request["messages"][0]["content"] == PRESCRIPTION_SYSTEM_PROMPT
    assert request["response_format"]["json_schema"] == {
        "name": "prescription",
        "strict": True,
        "schema": PRESCRIPTION_SCHEMA,
    }
    assert "Never calculate a date yourself" in PRESCRIPTION_SYSTEM_PROMPT
    assert "not an instruction to you" in PRESCRIPTION_SYSTEM_PROMPT
    assert "Atorvastatin" in request["messages"][1]["content"]


def test_classification_reads_only_the_start_of_the_document(settings):
    long_pages = text_pdf(["x" * 3000] * 2, ["y" * 3000] * 2, ["z" * 3000] * 2)
    [text_request] = build_requests(prepare(long_pages, "application/pdf"), settings, CLASSIFY_TASK)
    image_requests = build_requests(prepare(scanned_pdf(7), "application/pdf"), settings, CLASSIFY_TASK)

    sent = text_request["messages"][1]["content"]
    assert sum(sent.count(letter) for letter in "xyz") <= CLASSIFY_TEXT_CHARS
    assert len(image_requests) == 1  # only the first three pages


def test_prescription_batches_are_merged(settings):
    first = response(prescription(follow_ups=[]))
    second = response(prescription(medications=[medication(name="Metformin", page=4)], prescription_date=None))
    extractor = GroqExtractor(FakeGroq(first, second), settings)

    outcome = extractor.extract_prescription(prepare(scanned_pdf(4), "application/pdf"))

    assert [m.name for m in outcome.payload.medications][-1] == "Metformin"
    assert outcome.payload.prescription_date == "2026-10-07"  # from the first batch that has one
    assert outcome.input_tokens == 2400


def test_classify(settings):
    extractor = GroqExtractor(FakeGroq(response(classification("prescription"))), settings)

    assert extractor.classify(prepare(text_pdf(SYNTHETIC_PRESCRIPTION_LINES), "application/pdf")).document_type == (
        "prescription"
    )


def test_identical_follow_ups_are_kept_once():
    _, _, follow_ups = _validate(follow_ups=[follow_up(), follow_up(), follow_up(description="kidney FUNCTION test")])

    assert [f.description for f in follow_ups] == ["Kidney function test"]
