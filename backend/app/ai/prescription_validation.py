"""Validate an extracted prescription and settle follow-up dates (AI_spec.md Sections 4.5, 8, 9.2).

Deterministic code only. The model copies what is written; this module decides:
- the follow-up date: a written calendar date, or one calculated here from the printed
  prescription date for timings such as "after 4 weeks" (the model never calculates dates);
- what needs review, with a plain reason, instead of guessing.
"""

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta

from app.ai.dates import ambiguous, document_date
from app.ai.readability import NOT_IDENTIFIED, garbled_text
from app.ai.schema import ExtractedFollowUp, ExtractedMedication, PrescriptionPayload
from app.ai.source_check import SourceText, check_all

LIMITS = {
    "name": 200,
    "strength": 100,
    "instructions": 300,
    "duration": 100,
    "description": 300,
    "date_text": 200,
    "condition": 200,
}
MAX_RELATIVE = {"days": 730, "weeks": 104, "months": 24}  # beyond two years is treated as unclear

UNCLEAR_MEDICATION = "The name, strength, or instructions were not clearly legible."
NO_INSTRUCTIONS = "How to take it is not written or unclear."
DUPLICATE_MEDICATION = "This medicine appears more than once."
NOT_IDENTIFIED_MEDICATION = "Some details could not be read ({parts}): shown as Not identified. Check the original."
STRENGTH_NOT_MATCHED = "The strength could not be found on this medicine's line. Check the original."
UNCLEAR_FOLLOW_UP = "The follow-up was not clearly legible."
NO_TIMING = "No follow-up date or timing is written."
UNREADABLE_DATE = "The follow-up date could not be read."
NO_BASE_DATE = "The prescription or discharge date is missing, so the follow-up date cannot be calculated."
BEFORE_PRESCRIPTION = "The follow-up date is before the prescription or discharge date."
AMBIGUOUS_DATE = "The date could mean two different days (day and month can be swapped). Check the original."
AMBIGUOUS_BASE = (
    "The document date could mean two different days (day and month can be swapped), "
    "so the follow-up date was not calculated. Check the original."
)


@dataclass
class PrescriptionHeader:
    prescribed_on: date | None
    date_text: str | None
    prescriber_name: str | None
    date_ambiguous: bool = False  # a printed date whose day and month could be swapped: no calendar date kept


@dataclass
class ValidatedMedication:
    name: str
    strength: str | None
    instructions: str | None
    duration_text: str | None
    page: int | None
    snippet: str | None
    confidence: str
    notes: str | None
    review_reason: str | None


@dataclass
class ValidatedFollowUp:
    description: str
    kind: str
    date_text: str | None
    due_date: date | None
    due_date_basis: str | None  # "written" or "calculated"; None for an approximate timing
    page: int | None
    snippet: str | None
    confidence: str
    notes: str | None
    review_reason: str | None
    condition: str | None = None  # "if not better / SOS": only if needed, never a fixed date


def _clean(value: str | None, limit: int) -> str | None:
    value = (value or "").strip()
    return value[:limit] or None


def _iso_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError:
        return None


def header_date(value: str | None, printed: str | None) -> tuple[date | None, bool]:
    """The document's calendar date (None if ambiguous, app/ai/dates.py) and whether it was ambiguous."""
    parsed = document_date(value, printed)
    return parsed, parsed is None and _iso_date(value) is not None and ambiguous(printed)


def add_months(start: date, months: int) -> date:
    """Calendar months; the day is kept, or moved back to the last day of a shorter month."""
    year, month = divmod(start.month - 1 + months, 12)
    year += start.year
    month += 1
    return start.replace(year=year, month=month, day=min(start.day, calendar.monthrange(year, month)[1]))


def calculate_due_date(base: date, amount: int, unit: str) -> date:
    if unit == "days":
        return base + timedelta(days=amount)
    if unit == "weeks":
        return base + timedelta(weeks=amount)
    return add_months(base, amount)


_DOSE_LABEL = re.compile(r"^\s*(dose|dosage|strength)\s*[:\-]\s*", re.IGNORECASE)


def _same_text(instructions: str, strength: str) -> bool:
    """The instructions only repeat the strength, ignoring case, spaces, and a "Dose:" label ("Dose: 625mg")."""
    bare = _DOSE_LABEL.sub("", instructions)
    return "".join(bare.split()).casefold() == "".join(strength.split()).casefold()


def needs_second_look(item: ExtractedMedication) -> bool:
    """Its strength, how to take it, or its duration is printed but was not read: on a scan, OCR text can lose a
    table's columns, so the page is read again as an image before anything is shown as Not identified
    (decision 2026-10-17)."""
    strength, instructions = (item.strength or "").strip(), (item.instructions or "").strip()
    return (
        bool(item.unreadable)
        or not instructions
        or any(garbled_text(text) for text in (item.strength, item.instructions, item.duration_text))
        or bool(strength and _same_text(instructions, strength))
    )


def without_duration(instructions: str | None, duration: str | None) -> str | None:
    """Instructions without a trailing copy of the duration ("…, At night, 90 days" with duration "90 days")."""
    if not instructions or not duration:
        return instructions
    pattern = rf"(?:\s*[,;]\s*|\s+)(?:for\s+)?{re.escape(duration)}\s*\.?\s*$"
    trimmed = re.sub(pattern, "", instructions, flags=re.IGNORECASE)
    return trimmed or instructions


def _page(page: int | None, page_count: int | None) -> int | None:
    return page if page is not None and page >= 1 and (page_count is None or page <= page_count) else None


def _medication(
    item: ExtractedMedication, page_count: int | None, seen: set[tuple[str, str]], located: str | None = None
) -> ValidatedMedication:
    name = _clean(item.name, LIMITS["name"]) or "Unnamed medicine"
    strength = _clean(item.strength, LIMITS["strength"])
    instructions = _clean(item.instructions, LIMITS["instructions"])
    duration = _clean(item.duration_text, LIMITS["duration"])
    # A table's columns are joined into instructions; the duration is shown from duration_text only.
    instructions = without_duration(instructions, duration)

    # Printed but unreadable details become "Not identified", never a guess (app/ai/readability.py).
    unreadable = [
        part
        for part, text in (("strength", strength), ("instructions", instructions), ("duration", duration))
        if part in item.unreadable or garbled_text(text)
    ]
    # Checked against the line it was printed on (app/ai/source_check.py): another medicine's strength
    # is not this one's.
    if located == "value_in_other_row" and "strength" not in unreadable:
        unreadable.insert(0, "strength")
    # Instructions that are only the strength again ("625 mg" for 625 mg): the how-to-take column was not
    # read (e.g. an OCR scan that missed the table's Frequency column), so it is not shown as if it were.
    if instructions and strength and _same_text(instructions, strength) and "instructions" not in unreadable:
        unreadable.append("instructions")
    strength = NOT_IDENTIFIED if "strength" in unreadable else strength
    instructions = NOT_IDENTIFIED if "instructions" in unreadable else instructions
    duration = NOT_IDENTIFIED if "duration" in unreadable else duration

    reason = None
    if unreadable:
        reason = NOT_IDENTIFIED_MEDICATION.format(parts=", ".join(unreadable))
    elif item.confidence != "high" or name == "Unnamed medicine":
        reason = UNCLEAR_MEDICATION
    elif located == "value_not_matched":
        reason = STRENGTH_NOT_MATCHED
    elif instructions is None:
        reason = NO_INSTRUCTIONS
    key = (name.casefold(), (strength or "").casefold())
    if reason is None and key in seen:
        reason = DUPLICATE_MEDICATION
    seen.add(key)

    return ValidatedMedication(
        name=name,
        strength=strength,
        instructions=instructions,
        duration_text=duration,
        page=_page(item.page, page_count),
        snippet=_clean(item.source_text, 500),
        confidence=item.confidence,
        notes=_clean(item.notes, 1000),
        review_reason=reason,
    )


def _follow_up(item: ExtractedFollowUp, header: PrescriptionHeader, page_count: int | None) -> ValidatedFollowUp:
    due, basis, reason = None, None, None
    condition = _clean(item.condition, LIMITS["condition"])
    if condition:
        # Only if needed ("Review after 5 days if not better/SOS"): kept with its timing as written, never
        # dated or added as an appointment, so it can never show as overdue (decision 2026-10-17).
        pass
    elif item.date:
        due = document_date(item.date, item.date_text)
        basis = "written" if due else None
        if due is None:
            reason = AMBIGUOUS_DATE if _iso_date(item.date) else UNREADABLE_DATE
    elif item.relative_amount is not None and item.relative_unit is not None:
        if not 0 < item.relative_amount <= MAX_RELATIVE[item.relative_unit]:
            reason = UNCLEAR_FOLLOW_UP
        elif header.prescribed_on is None:
            reason = AMBIGUOUS_BASE if header.date_ambiguous else NO_BASE_DATE
        else:
            due = calculate_due_date(header.prescribed_on, item.relative_amount, item.relative_unit)
            basis = "calculated"
    elif not (item.date_text or "").strip():
        reason = NO_TIMING
    # Otherwise an approximate timing such as "mid-January 2027": shown as written, never dated or added
    # (decision 2026-10-12).

    if reason is None and item.confidence != "high":
        reason = UNCLEAR_FOLLOW_UP
    if reason is None and due and header.prescribed_on and due < header.prescribed_on:
        reason = BEFORE_PRESCRIPTION

    return ValidatedFollowUp(
        description=_clean(item.description, LIMITS["description"]) or "Follow-up",
        kind=item.kind,
        date_text=_clean(item.date_text, LIMITS["date_text"]),
        due_date=due,
        due_date_basis=basis,
        page=_page(item.page, page_count),
        snippet=_clean(item.source_text, 500),
        confidence=item.confidence,
        notes=_clean(item.notes, 1000),
        review_reason=reason,
        condition=condition,
    )


def strengths_located(medications: list[ExtractedMedication], source: SourceText | None) -> list[str | None]:
    """Each medicine's strength checked against its own line; medicines without a strength are not checked."""
    if source is None:
        return [None] * len(medications)
    with_strength = [i for i, m in enumerate(medications) if (m.strength or "").strip() and (m.name or "").strip()]
    outcomes = check_all(
        source,
        [(medications[i].name.strip(), medications[i].strength.strip(), medications[i].page) for i in with_strength],
    )
    located: list[str | None] = [None] * len(medications)
    for i, outcome in zip(with_strength, outcomes, strict=True):
        # Only a strength off its own line counts; handwriting read from an image is flagged by confidence.
        located[i] = outcome if outcome in ("value_in_other_row", "value_not_matched") else None
    return located


def validate_prescription(
    payload: PrescriptionPayload, page_count: int | None, source: SourceText | None = None
) -> tuple[PrescriptionHeader, list[ValidatedMedication], list[ValidatedFollowUp]]:
    date_text = _clean(payload.prescription_date_text, 100)
    prescribed_on, date_ambiguous = header_date(payload.prescription_date, date_text)
    header = PrescriptionHeader(
        prescribed_on=prescribed_on,
        date_text=date_text,
        prescriber_name=_clean(payload.prescriber_name, 200),
        date_ambiguous=date_ambiguous,
    )
    seen: set[tuple[str, str]] = set()
    medications = [
        _medication(item, page_count, seen, where)
        for item, where in zip(payload.medications, strengths_located(payload.medications, source), strict=True)
    ]
    follow_ups: list[ValidatedFollowUp] = []
    seen_follow_ups: set[tuple[str, object]] = set()
    for item in payload.follow_ups:
        follow_up = _follow_up(item, header, page_count)
        # The same test on the same date listed twice is one follow-up (never added as two reminders).
        key = (follow_up.description.casefold(), follow_up.due_date or follow_up.date_text)
        if key in seen_follow_ups:
            continue
        seen_follow_ups.add(key)
        follow_ups.append(follow_up)
    return header, medications, follow_ups
