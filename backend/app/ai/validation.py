"""Pipeline stages 6–7: normalise and validate extracted results (AI_spec.md Section 4.5).

Deterministic checks only. Structural validity is not medical correctness, so anything
uncertain is flagged for the user to review rather than corrected silently.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from app.ai.dates import ambiguous
from app.ai.readability import NOT_IDENTIFIED, REPLACEMENT_CHARACTER, check_result, not_a_result
from app.ai.schema import ExtractedResult, ExtractionPayload
from app.ai.source_check import SourceText, check_all, near

_NUMBER = re.compile(r"[-+]?\d+(?:,\d{3})*(?:[.,]\d+)?")
_THOUSANDS = re.compile(r"[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?")
_COMPARATOR = re.compile(r"^\s*(<=?|>=?|≤|≥)")

LIMITS = {"name": 200, "value_text": 200, "unit": 50, "reference_range_text": 200, "snippet": 500}


@dataclass
class ValidatedResult:
    name: str
    value_text: str
    value_numeric: Decimal | None
    unit: str | None
    reference_range_text: str | None
    reference_low: Decimal | None
    reference_high: Decimal | None
    observed_at: date | None
    observed_at_precision: str | None
    page: int | None
    snippet: str | None
    confidence: str
    notes: str | None
    findings: list[str] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        # Anything less than clearly legible, or any failed check, goes to the user.
        return self.confidence != "high" or any(f in REVIEW_FINDINGS for f in self.findings)


# Findings that require a person to check the value. Others are informational.
REVIEW_FINDINGS = {
    "numeric_value_mismatch",
    "missing_unit",
    "date_in_future",
    "implausible_date",
    "invalid_date",
    "invalid_reference_range",
    "possible_duplicate",
    "value_truncated",
    "unreadable_characters",
    # Printed but not readable: shown as "Not identified" (app/ai/readability.py).
    "value_not_identified",
    "unit_not_identified",
    "range_not_identified",
    # Checked against the document text (app/ai/source_check.py).
    "read_from_image",
    "name_not_matched",
    "value_not_matched",
    "unit_not_matched",
    "range_not_matched",
}


def parse_number(text: str | None) -> Decimal | None:
    """The single number in a value as written, or None ('<0.5', 'Negative', '5-7' are not single numbers)."""
    if not text or _COMPARATOR.match(text):
        return None
    numbers = _NUMBER.findall(text)
    if len(numbers) != 1:
        return None
    token = numbers[0]
    # "1,200" / "12,500.5" use commas for thousands; otherwise a comma is a decimal point ("5,4").
    token = token.replace(",", "") if _THOUSANDS.fullmatch(token) else token.replace(",", ".")
    try:
        return Decimal(token)
    except InvalidOperation:
        return None


def _decimal(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _clip(value: str | None, limit: int) -> tuple[str | None, bool]:
    if value is None:
        return None, False
    value = value.strip()
    return (value[:limit], True) if len(value) > limit else (value or None, False)


def _parse_date(value: str | None, precision: str | None, today: date, findings: list[str]):
    if not value:
        return None, None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        findings.append("invalid_date")
        return None, None
    if parsed > today:
        findings.append("date_in_future")
    elif parsed.year < 1900:
        findings.append("implausible_date")
    precision = precision or "day"
    if precision == "month":
        parsed = parsed.replace(day=1)
    elif precision == "year":
        parsed = parsed.replace(month=1, day=1)
    return parsed, precision


def _validate_one(
    result: ExtractedResult,
    payload: ExtractionPayload,
    page_count: int | None,
    today: date,
    source: SourceText | None = None,
    located: str | None = None,
):
    findings: list[str] = []

    name, _ = _clip(result.test_name, LIMITS["name"])
    value_text, truncated = _clip(result.value_text, LIMITS["value_text"])
    if not name or not (value_text or "value" in result.unreadable):
        return None  # nothing usable to review
    unit, _ = _clip(result.unit, LIMITS["unit"])
    reference_text, _ = _clip(result.reference_range_text, LIMITS["reference_range_text"])
    if not_a_result(name, value_text, unit, reference_text):
        return None  # a report date or patient detail read as if it were a test
    if truncated:
        findings.append("value_truncated")

    # Printed but unreadable parts become "Not identified", never a guess.
    value_text, unit, reference_text, not_identified = check_result(
        value_text, unit, reference_text, list(result.unreadable)
    )
    findings.extend(f"{part}_not_identified" for part in not_identified)

    # Checked against the line it was printed on: a value from another test's row is not this test's value.
    if located == "value_in_other_row" and value_text != NOT_IDENTIFIED:
        value_text = NOT_IDENTIFIED
        findings.extend(["value_not_identified", "value_in_other_row"])
    elif located and located != "value_in_other_row":
        findings.append(located)
    if source is not None and located is None:
        for part, text in (("unit", unit), ("range", reference_text)):
            if text and text != NOT_IDENTIFIED and not near(source, name, text, result.page):
                findings.append(f"{part}_not_matched")

    # Our own parse of the written value wins; a disagreement with the model is flagged.
    numeric = None if value_text == NOT_IDENTIFIED else parse_number(value_text)
    model_numeric = _decimal(result.value_numeric)
    if value_text != NOT_IDENTIFIED and model_numeric is not None and (numeric is None or numeric != model_numeric):
        findings.append("numeric_value_mismatch")

    if numeric is not None and not unit:
        findings.append("missing_unit")

    low, high = _decimal(result.reference_low), _decimal(result.reference_high)
    if "range" in not_identified:
        low = high = None
    if low is not None and high is not None and low > high:
        findings.append("invalid_reference_range")

    if ambiguous(result.result_date_text):  # e.g. "03/04": day and month could be swapped (app/ai/dates.py)
        findings.append("ambiguous_date")
        observed_at, precision = None, None
    else:
        observed_at, precision = _parse_date(result.result_date, result.result_date_precision, today, findings)
    if observed_at is None and not result.result_date and payload.report_date:
        if ambiguous(payload.report_date_text):
            findings.append("ambiguous_date")  # e.g. "02/09/26": no calendar date is guessed (app/ai/dates.py)
        else:
            observed_at, precision = _parse_date(payload.report_date, payload.report_date_precision, today, findings)
            if observed_at is not None:
                findings.append("date_from_report")

    page = result.page
    if page is not None and (page < 1 or (page_count is not None and page > page_count)):
        findings.append("page_out_of_range")
        page = None

    snippet, _ = _clip(result.source_text, LIMITS["snippet"])
    if REPLACEMENT_CHARACTER in name:
        findings.append("unreadable_characters")
    return ValidatedResult(
        name=name,
        value_text=value_text,
        value_numeric=numeric,
        unit=unit,
        reference_range_text=reference_text,
        reference_low=low,
        reference_high=high,
        observed_at=observed_at,
        observed_at_precision=precision,
        page=page,
        snippet=snippet,
        confidence=result.confidence,
        notes=(result.notes or "").strip() or None,
        findings=findings,
    )


def validate_payload(
    payload: ExtractionPayload, page_count: int | None, today: date, source: SourceText | None = None
) -> list[ValidatedResult]:
    """`source` is the document text the results were read from; without it nothing is cross-checked."""
    located: list[str | None] = [None] * len(payload.lab_results)
    if source is not None:
        located = check_all(
            source, [((r.test_name or "").strip(), (r.value_text or "").strip(), r.page) for r in payload.lab_results]
        )
    validated = [
        item
        for item in (
            _validate_one(r, payload, page_count, today, source, where)
            for r, where in zip(payload.lab_results, located, strict=True)
        )
        if item
    ]

    seen: dict[tuple, ValidatedResult] = {}
    for item in validated:
        key = (item.name.casefold(), item.value_text, (item.unit or "").casefold(), item.observed_at)
        if key in seen:
            item.findings.append("possible_duplicate")
            if "possible_duplicate" not in seen[key].findings:
                seen[key].findings.append("possible_duplicate")
        else:
            seen[key] = item
    return validated
