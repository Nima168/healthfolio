"""Validate an extracted discharge summary (DL_AI_spec.md Sections 4.5, 8, 9.2).

Deterministic code only. The model copies what is written; this module decides:
- the length of stay (calendar days, admission and discharge day both counted);
- each result's date, adding the admission year to dates written without one ("12-Aug");
- whether a result is a single number (only a plain number is; "13-Aug" inside a text result is not);
- medicines and follow-ups with the prescription rules, follow-ups counted from the discharge date.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from app.ai.dates import ambiguous
from app.ai.prescription_validation import (
    PrescriptionHeader,
    ValidatedFollowUp,
    ValidatedMedication,
    _clean,
    _follow_up,
    _medication,
    _page,
    header_date,
    strengths_located,
)
from app.ai.readability import NOT_IDENTIFIED, check_result, not_a_result
from app.ai.schema import DischargePayload, ExtractedDischargeResult
from app.ai.source_check import SourceText, check_all
from app.ai.validation import parse_number

_PLAIN_NUMBER = re.compile(r"^\s*[-+]?\d[\d,]*(?:\.\d+)?\s*$")
# Numeric day/month forms are read day first only when that is the only possible reading
# ("25/08"); "12/08" could be either, so it gets no date (app/ai/dates.py).
_FULL_DATE_FORMATS = ("%d-%b-%Y", "%d %b %Y", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d")
_DAY_MONTH_FORMATS = ("%d-%b", "%d %b", "%d/%m", "%d-%m")


@dataclass
class DischargeHeader:
    facility_name: str | None
    admitted_on: date | None
    admitted_text: str | None
    discharged_on: date | None
    discharged_text: str | None
    discharged_ambiguous: bool = False

    @property
    def stay_days(self) -> int | None:
        """Calendar days in hospital, counting both the admission and the discharge day."""
        if self.admitted_on and self.discharged_on and self.discharged_on >= self.admitted_on:
            return (self.discharged_on - self.admitted_on).days + 1
        return None


@dataclass
class ValidatedDischargeResult:
    name: str
    value_text: str
    value_numeric: object  # Decimal | None
    unit: str | None
    reference_range_text: str | None
    observed_at: date | None
    page: int | None
    confidence: str
    not_identified: list[str] = field(default_factory=list)  # parts printed but not readable
    unchecked: str | None = None  # not found on its own line in the document text (app/ai/source_check.py)

    @property
    def needs_review(self) -> bool:
        return self.confidence != "high" or bool(self.not_identified) or self.unchecked is not None

    @property
    def findings(self) -> list[str]:
        found = [f"{part}_not_identified" for part in self.not_identified]
        return found + ([self.unchecked] if self.unchecked else [])


@dataclass
class ValidatedDischarge:
    header: DischargeHeader
    diagnoses: list[str] = field(default_factory=list)
    results: list[ValidatedDischargeResult] = field(default_factory=list)
    medications: list[ValidatedMedication] = field(default_factory=list)
    follow_ups: list[ValidatedFollowUp] = field(default_factory=list)
    warning_signs: list[str] = field(default_factory=list)


def result_date(text: str | None, admitted_on: date | None) -> date | None:
    """A result date as written; a missing year is the admission year (the next year if it wraps past December)."""
    text = (text or "").strip().rstrip(".")
    if not text or ambiguous(text):
        return None
    for fmt in _FULL_DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    if admitted_on is None:
        return None
    for fmt in _DAY_MONTH_FORMATS:
        try:
            # Parsed with a leap year so "29-Feb" is accepted, then moved to the admission year.
            parsed = datetime.strptime(f"{text} 2000", f"{fmt} %Y").date()
        except ValueError:
            continue
        year = admitted_on.year + (1 if parsed.month < admitted_on.month else 0)
        try:
            return parsed.replace(year=year)
        except ValueError:
            return None
    return None


def _number(value_text: str):
    return parse_number(value_text) if _PLAIN_NUMBER.match(value_text) else None


def _unique(texts: list[str], limit: int) -> list[str]:
    seen, unique = set(), []
    for text in texts:
        cleaned = _clean(text, limit)
        if cleaned and cleaned.casefold() not in seen:
            seen.add(cleaned.casefold())
            unique.append(cleaned)
    return unique


def _result(
    item: ExtractedDischargeResult, header: DischargeHeader, page_count: int | None, located: str | None = None
):
    name = _clean(item.test_name, 200)
    value = _clean(item.value_text, 200)
    if not name or not (value or "value" in item.unreadable):
        return None
    unit, reference = _clean(item.unit, 50), _clean(item.reference_range_text, 200)
    if not_a_result(name, value, unit, reference):
        return None
    value, unit, reference, not_identified = check_result(value, unit, reference, list(item.unreadable))
    unchecked = located
    if located == "value_in_other_row":  # taken from another test's row: not this test's value
        value, unchecked = NOT_IDENTIFIED, "value_in_other_row"
        not_identified = [*dict.fromkeys([*not_identified, "value"])]
    return ValidatedDischargeResult(
        name=name,
        value_text=value,
        value_numeric=None if "value" in not_identified else _number(value),
        unit=unit,
        reference_range_text=reference,
        observed_at=result_date(item.result_date_text, header.admitted_on),
        page=_page(item.page, page_count),
        confidence=item.confidence,
        not_identified=not_identified,
        unchecked=unchecked,
    )


def _located(payload: DischargePayload, source: SourceText | None) -> list[str | None]:
    if source is None:
        return [None] * len(payload.results)
    return check_all(
        source, [((r.test_name or "").strip(), (r.value_text or "").strip(), r.page) for r in payload.results]
    )


def validate_discharge(
    payload: DischargePayload, page_count: int | None, source: SourceText | None = None
) -> ValidatedDischarge:
    """`source` is the document text the results were read from; without it nothing is cross-checked."""
    admitted_text = _clean(payload.admission_date_text, 100)
    discharged_text = _clean(payload.discharge_date_text, 100)
    discharged_on, discharged_ambiguous = header_date(payload.discharge_date, discharged_text)
    header = DischargeHeader(
        facility_name=_clean(payload.facility_name, 200),
        admitted_on=header_date(payload.admission_date, admitted_text)[0],
        admitted_text=admitted_text,
        discharged_on=discharged_on,
        discharged_text=discharged_text,
        discharged_ambiguous=discharged_ambiguous,
    )
    # Follow-ups written as "after 2 weeks" count from the discharge date.
    base = PrescriptionHeader(header.discharged_on, header.discharged_text, None, discharged_ambiguous)

    seen_medicines: set[tuple[str, str]] = set()
    follow_ups: list[ValidatedFollowUp] = []
    seen_follow_ups: set[tuple[str, object]] = set()
    for item in payload.follow_ups:
        follow_up = _follow_up(item, base, page_count)
        key = (follow_up.description.casefold(), follow_up.due_date or follow_up.date_text)
        if key not in seen_follow_ups:
            seen_follow_ups.add(key)
            follow_ups.append(follow_up)

    return ValidatedDischarge(
        header=header,
        diagnoses=_unique(payload.diagnoses, 300),
        results=[
            r
            for r in (
                _result(item, header, page_count, where)
                for item, where in zip(payload.results, _located(payload, source), strict=True)
            )
            if r is not None
        ],
        medications=[
            _medication(item, page_count, seen_medicines, where)
            for item, where in zip(payload.medications, strengths_located(payload.medications, source), strict=True)
        ],
        follow_ups=follow_ups,
        warning_signs=_unique(payload.warning_signs, 500),
    )
