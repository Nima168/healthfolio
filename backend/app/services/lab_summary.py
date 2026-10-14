"""Lab-result summary: which values fall outside the reference range printed in the report.

Deterministic rules, never the AI (AI_spec.md Section 9.1: rules decide):
1. Only the reference range printed next to each test is used; no outside or assumed ranges.
2. Values, units, and ranges are shown exactly as extracted; nothing is rounded.
3. No range, a value that is not a single number, an unreadable range, or an unclear
   value/unit/range goes to "Invalid Records" instead of being judged (shown as written, with the reason).
4. "< X", "<= X", "> X", ">= X" are applied exactly as written; "a - b" includes both ends.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal

from app.ai.validation import parse_number
from app.models.extraction import Observation

_NUMBER = r"\d+(?:,\d{3})*(?:\.\d+)?|\d+,\d+"
# Trailing text without digits (a unit, "(adult)") is allowed; anything with more numbers is not read.
_BETWEEN = re.compile(rf"^\s*({_NUMBER})\s*(?:-|–|—|to)\s*({_NUMBER})\s*[^\d]*$", re.IGNORECASE)
_BOUND = re.compile(rf"^\s*(<=|>=|≤|≥|<|>)\s*({_NUMBER})\s*[^\d]*$")

# Validation findings that mean the value, unit, or range is unclear (rule 3).
_UNCLEAR = {
    "numeric_value_mismatch": "The value may have been misread.",
    "missing_unit": "The unit is missing or unclear.",
    "invalid_reference_range": "The reference range looks reversed.",
    "value_truncated": "The value was too long to read completely.",
    # Checked against the document text (app/ai/source_check.py).
    "read_from_image": "Read from the page image, with no text to check it against. Check it against the original.",
    "name_not_matched": "This test's name could not be found in the document text. Check it against the original.",
    "value_not_matched": "The value could not be found on this test's line. Check it against the original.",
}


# More than this many times the upper limit, or below the lower limit divided by it, is unusual enough to
# suggest a misread ("162" for 7.2). Real critical values can be this far out (TSH 100), so the line is still
# grouped and alerted, only marked "check the original".
FAR_OUTSIDE = Decimal(10)
FAR_OUTSIDE_NOTE = "Unusually far outside the range: check the original."


@dataclass(frozen=True)
class SummaryLine:
    name: str
    value_text: str
    unit: str | None
    reference_range_text: str | None
    note: str | None = None


@dataclass(frozen=True)
class InvalidLine(SummaryLine):
    """A result that could not be judged against its range; shown as written, never as high/low/normal."""

    reason: str = ""


@dataclass
class LabSummary:
    report_date: str | None
    above: list[SummaryLine] = field(default_factory=list)
    below: list[SummaryLine] = field(default_factory=list)
    normal: list[SummaryLine] = field(default_factory=list)
    invalid: list[InvalidLine] = field(default_factory=list)


def range_check(value: Decimal, range_text: str) -> str | None:
    """ "above", "below", or "within" for a readable printed range; None when it cannot be read."""
    if match := _BETWEEN.match(range_text):
        low, high = parse_number(match.group(1)), parse_number(match.group(2))
        if low is None or high is None or low > high:
            return None
        return "below" if value < low else "above" if value > high else "within"
    if match := _BOUND.match(range_text):
        operator, limit = match.group(1), parse_number(match.group(2))
        if limit is None:
            return None
        if operator == "<":
            return "within" if value < limit else "above"
        if operator in ("<=", "≤"):
            return "within" if value <= limit else "above"
        if operator == ">":
            return "within" if value > limit else "below"
        return "within" if value >= limit else "below"  # ">=", "≥"
    return None


def far_outside(value: Decimal, range_text: str) -> bool:
    """Only two-sided printed ranges ("a - b") are used: a bound like "< 5.0" says nothing about how far is odd."""
    match = _BETWEEN.match(range_text)
    if not match:
        return False
    low, high = parse_number(match.group(1)), parse_number(match.group(2))
    if low is None or high is None or high <= 0:
        return False
    return value > high * FAR_OUTSIDE or (low > 0 and value < low / FAR_OUTSIDE)


def _unclear_reason(observation: Observation) -> str | None:
    for finding in observation.validation_findings or []:
        if finding in _UNCLEAR:
            return _UNCLEAR[finding]
    if observation.confidence in ("low", "medium"):
        return "The value, unit, or range was not clearly legible."
    return None


def classify(observation: Observation) -> tuple[str, str | None]:
    """("above" | "below" | "within", None) or ("invalid", reason)."""
    findings = observation.validation_findings or []
    if "value_in_other_row" in findings:
        return "invalid", "The value read for this test belongs to another row (Not identified). Check the original."
    if any(finding.endswith("_not_identified") for finding in findings):
        return "invalid", "Part of this result could not be read (Not identified). Check it against the original."
    range_text = (observation.reference_range_text or "").strip()
    if not range_text:
        return "invalid", "No reference range is printed for this test."
    if observation.value_numeric is None:
        return "invalid", f'The value "{observation.value_text}" is not a single number, so it was not compared.'
    if reason := _unclear_reason(observation):
        return "invalid", reason
    status = range_check(observation.value_numeric, range_text)
    if status is None:
        return "invalid", f'The reference range "{range_text}" could not be read.'
    return status, None


def summarise(observations: list[Observation], report_date_text: str | None) -> LabSummary:
    summary = LabSummary(report_date=report_date_text)
    for observation in observations:
        status, reason = classify(observation)
        if status == "invalid":
            summary.invalid.append(
                InvalidLine(
                    observation.name,
                    observation.value_text,
                    observation.unit,
                    observation.reference_range_text,
                    reason=reason or "",
                )
            )
            continue
        far = status != "within" and far_outside(observation.value_numeric, observation.reference_range_text or "")
        line = SummaryLine(
            observation.name,
            observation.value_text,
            observation.unit,
            observation.reference_range_text,
            note=FAR_OUTSIDE_NOTE if far else None,
        )
        {"above": summary.above, "below": summary.below, "within": summary.normal}[status].append(line)
    return summary
