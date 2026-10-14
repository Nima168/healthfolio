"""The accuracy evaluation itself: generated documents, pipeline wiring, and scoring (fake AI, no network)."""

import pymupdf
import pytest

from app.ai.extractor import GroqExtractor
from app.ai.validation import parse_number
from app.core.config import get_settings
from evaluation.cases import build_cases
from evaluation.pipeline import run_document
from evaluation.render import digital_pdf
from evaluation.score import cer, pair, score, signature
from tests.ai_fakes import FakeGroq, follow_up, medication, payload, prescription, response, result

CASES = {case.id: case for case in build_cases()}


@pytest.fixture
def settings():
    get_settings.cache_clear()
    return get_settings()


def _read(settings, case, reply):
    content, _ = digital_pdf(case)
    return run_document(
        content, case.kind, "digital", settings=settings, extractor=GroqExtractor(FakeGroq(reply), settings), ocr=None
    )


def _lab_reply(case, **changes):
    rows = []
    for item in case.labs:
        number = parse_number(item.value)
        rows.append(
            result(
                test_name=item.name,
                value_text=item.value,
                value_numeric=float(number) if number is not None else None,
                unit=item.unit,
                reference_range_text=item.range_text,
                reference_low=None,
                reference_high=None,
                source_text=item.name,
            )
            | changes.get(item.name, {})
        )
    return response(
        payload(rows + changes.get("extra", []), report_date=case.doc_date.isoformat(), report_date_text=case.date_text)
    )


# ---------- generated documents ----------


def test_cases_are_reproducible():
    assert [c.labs for c in build_cases()] == [c.labs for c in build_cases()]


def test_digital_documents_print_their_known_values():
    case = CASES["lab04"]
    content, printed = digital_pdf(case)
    text = " ".join(page.get_text() for page in pymupdf.open(stream=content, filetype="pdf"))

    for item in case.labs:
        assert item.name in text and item.value in text and item.name in printed
    assert case.date_text in text


def test_two_page_reports_have_two_pages():
    content, _ = digital_pdf(CASES["lab05"])
    assert len(pymupdf.open(stream=content, filetype="pdf")) == 2


# ---------- scoring ----------


def test_a_perfect_lab_reading_scores_full_marks(settings):
    case = CASES["lab04"]  # includes missing units, a missing range, and a "<" value
    reading = _read(settings, case, _lab_reply(case))
    counts = score(case, reading)

    assert reading["method"] == "digital"
    assert (counts.items_found, counts.items_extra) == (len(case.labs), 0)
    assert counts.fields_correct == counts.fields_checked == 3 * len(case.labs)
    assert counts.groups_correct == counts.groups_checked, counts.errors
    assert counts.blanks_honest == counts.blanks_expected == 3
    assert counts.dates_correct == 1
    assert counts.printed_dates_correct == counts.printed_dates_checked == 1
    assert counts.errors == []


def test_dates_are_scored_as_printed_and_never_guessed(settings):
    case = CASES["lab04"]
    printed = "03/04/2026"  # 3 April or 4 March: no calendar date is the right answer
    ambiguous_case = type(case)(**{**vars(case), "date_text": printed})
    reading = {"extracted": {"labs": [], "date": None, "date_text": printed}}

    counts = score(ambiguous_case, reading)
    assert (counts.dates_correct, counts.printed_dates_correct) == (1, 1)

    guessed = score(ambiguous_case, {"extracted": {"labs": [], "date": "2026-04-03", "date_text": "2026-04-03"}})
    assert (guessed.dates_correct, guessed.printed_dates_correct) == (0, 0)


def test_wrong_and_invented_values_are_counted(settings):
    case = CASES["lab01"]
    first = case.labs[0]
    reply = _lab_reply(
        case,
        **{first.name: {"value_text": "999", "value_numeric": 999.0}},
        extra=[result(test_name="Imaginary Marker", value_text="1.0", value_numeric=1.0)],
    )
    counts = score(case, _read(settings, case, reply))

    assert counts.items_extra == 1
    assert counts.wrong_items == 1
    # High confidence and a consistent number, but 999 is not on the test's line in the document.
    assert counts.wrong_items_flagged == 1
    assert any("Imaginary Marker" in e for e in counts.errors)


def test_not_identified_is_an_honest_gap_but_a_wrong_value_is_misleading(settings):
    case = CASES["lab01"]
    first, second = case.labs[0], case.labs[1]
    reply = _lab_reply(
        case,
        **{
            first.name: {"value_text": "", "value_numeric": None, "unreadable": ["value"]},
            second.name: {"value_text": "999", "value_numeric": 999.0},
        },
    )
    counts = score(case, _read(settings, case, reply))

    assert counts.fields_not_identified == 1
    assert counts.fields_misleading == 1
    assert counts.wrong_items == 1  # only the misleading one counts as wrong


def test_a_guessed_unit_is_not_an_honest_blank(settings):
    case = CASES["lab04"]
    no_unit = next(item for item in case.labs if item.unit is None)
    counts = score(case, _read(settings, case, _lab_reply(case, **{no_unit.name: {"unit": "mg/dL"}})))

    assert counts.blanks_honest == counts.blanks_expected - 1


def test_a_perfect_prescription_reading(settings):
    case = CASES["rx01"]
    meds = [
        medication(name=m.name, strength=m.strength, instructions=m.instructions, duration_text=m.duration)
        for m in case.medicines
    ]
    review, test = case.follow_ups
    follow_ups = [
        follow_up(
            description=review.description,
            kind="appointment",
            date=None,
            date_text=review.timing,
            relative_amount=2,
            relative_unit="weeks",
        ),
        follow_up(
            description=test.description,
            date=test.due.isoformat(),
            date_text=test.timing,
            relative_amount=None,
            relative_unit=None,
        ),
    ]
    reply = response(
        prescription(
            meds, follow_ups, prescription_date=case.doc_date.isoformat(), prescription_date_text=case.date_text
        )
    )
    counts = score(case, _read(settings, case, reply))

    assert counts.items_found == counts.items_expected == len(case.medicines) + 2, counts.errors
    assert counts.fields_correct == counts.fields_checked
    assert counts.dates_correct == counts.dates_checked == 3


def test_a_failed_reading_misses_everything():
    case = CASES["img01"]
    counts = score(case, {"error": "ai_unavailable"})

    assert counts.items_found == 0 and counts.items_expected == 6


def test_helpers():
    assert cer("abc", "abd") == pytest.approx(1 / 3)
    assert pair(["Haemoglobin", "Sodium"], ["sodium", "Hemoglobin"]) == [(1, 0), (0, 1)]
    same = {"extracted": {"labs": [{"name": "A", "value": "1", "unit": "x", "range": "1 - 2"}]}}
    other = {"extracted": {"labs": [{"name": "A", "value": "7", "unit": "x", "range": "1 - 2"}]}}
    assert signature(same) == signature(same) != signature(other)
