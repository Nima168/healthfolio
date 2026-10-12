"""Lab-result summary: which values fall outside the reference range printed in the report.

Deterministic rules, never the AI (DL_AI_spec.md Section 9.1: rules decide):
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
}


@dataclass(frozen=True)
class SummaryLine:
    name: str
    value_text: str
    unit: str | None
    reference_range_text: str | None


@dataclass(frozen=True)
class InvalidLine(SummaryLine):
    """A result that could not be judged against its range; shown as written, never as high/low/normal."""

    reason: str


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


def _unclear_reason(observation: Observation) -> str | None:
    for finding in observation.validation_findings or []:
        if finding in _UNCLEAR:
            return _UNCLEAR[finding]
    if observation.confidence in ("low", "medium"):
        return "The value, unit, or range was not clearly legible."
    return None


def classify(observation: Observation) -> tuple[str, str | None]:
    """("above" | "below" | "within", None) or ("invalid", reason)."""
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
                    reason or "",
                )
            )
            continue
        line = SummaryLine(observation.name, observation.value_text, observation.unit, observation.reference_range_text)
        {"above": summary.above, "below": summary.below, "within": summary.normal}[status].append(line)
    return summary
