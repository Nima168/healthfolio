"""Discharge summary: stay, diagnoses, key results, discharge medicines, follow-ups, warning signs.

Deterministic, from stored rows (decisions 2026-10-12):
- Diagnoses and warning signs exactly as written; nothing is reworded.
- Key results: a test is listed when its last value is outside the reference range printed in the
  document (the same rule as the lab summary), or when its result is text (e.g. a culture report).
  "still" means the first value was outside the range on the same side. "last tested" is shown when
  the last result is from before the discharge date. No "slightly": the document gives no threshold.
- Medicines and follow-ups as in the prescription summary (follow-ups counted from discharge).
"""

from dataclasses import dataclass, field
from datetime import date

from app.models.extraction import Observation, ProcessingJob
from app.models.prescription import Condition, Medication, Suggestion
from app.services.lab_summary import range_check
from app.services.prescription_summary import FollowUpLine, MedicationLine, summarise_prescription

# Not found on the test's own line in the document text: shown, but never judged high or low.
_UNCHECKED = {"read_from_image", "name_not_matched", "value_not_matched", "value_in_other_row"}


@dataclass(frozen=True)
class KeyResult:
    name: str
    first_value: str | None  # shown as "first → last" when tested more than once
    last_value: str
    unit: str | None
    reference_range_text: str | None
    flag: str | None  # "high" / "low"; None for text results
    still: bool
    last_tested: date | None  # set when the last test was before the discharge date
    unclear: bool


@dataclass
class DischargeSummary:
    facility_name: str | None
    admitted_on: date | None
    admitted_text: str | None
    discharged_on: date | None
    discharged_text: str | None
    stay_days: int | None
    diagnoses: list[str] = field(default_factory=list)
    key_results: list[KeyResult] = field(default_factory=list)
    medications: list[MedicationLine] = field(default_factory=list)
    follow_ups: list[FollowUpLine] = field(default_factory=list)
    reminders: str = "none"
    warning_signs: list[str] = field(default_factory=list)


def _date(value: object) -> date | None:
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _key_result(rows: list[Observation], discharged_on: date | None) -> KeyResult | None:
    rows = sorted(rows, key=lambda row: (row.observed_at or date.max, row.position))
    first, last = rows[0], rows[-1]
    range_text = next((row.reference_range_text for row in reversed(rows) if row.reference_range_text), None)
    unclear = any(row.confidence != "high" or row.needs_review for row in rows)
    unchecked = bool(_UNCHECKED & set(last.validation_findings or []))
    last_tested = last.observed_at if discharged_on and last.observed_at and last.observed_at < discharged_on else None

    if last.value_numeric is None or unchecked:  # a text result, e.g. "No enteric pathogens isolated"
        return KeyResult(last.name, None, last.value_text, last.unit, range_text, None, False, None, unclear)
    if not range_text:
        return None
    status = range_check(last.value_numeric, range_text)
    if status not in ("above", "below"):
        return None
    earlier = first if first is not last and first.value_numeric is not None else None
    still = earlier is not None and range_check(earlier.value_numeric, range_text) == status
    return KeyResult(
        name=last.name,
        first_value=earlier.value_text if earlier else None,
        last_value=last.value_text,
        unit=last.unit,
        reference_range_text=range_text,
        flag="high" if status == "above" else "low",
        still=still,
        last_tested=last_tested,
        unclear=unclear,
    )


def summarise_discharge(
    job: ProcessingJob,
    conditions: list[Condition],
    observations: list[Observation],
    medications: list[Medication],
    suggestions: list[Suggestion],
) -> DischargeSummary:
    details = job.details or {}
    admitted_on, discharged_on = _date(details.get("admitted_on")), _date(details.get("discharged_on"))
    stay_days = None
    if admitted_on and discharged_on and discharged_on >= admitted_on:
        stay_days = (discharged_on - admitted_on).days + 1  # both days counted

    by_test: dict[str, list[Observation]] = {}
    for row in observations:
        by_test.setdefault(row.name.casefold(), []).append(row)
    key_results = [result for rows in by_test.values() if (result := _key_result(rows, discharged_on))]

    medicines_and_follow_ups = summarise_prescription(job, medications, suggestions)
    return DischargeSummary(
        facility_name=details.get("facility_name"),
        admitted_on=admitted_on,
        admitted_text=details.get("admitted_text"),
        discharged_on=discharged_on,
        discharged_text=details.get("discharged_text"),
        stay_days=stay_days,
        diagnoses=[condition.name for condition in conditions],
        key_results=key_results,
        medications=medicines_and_follow_ups.medications,
        follow_ups=medicines_and_follow_ups.follow_ups,
        reminders=medicines_and_follow_ups.reminders,
        warning_signs=list(details.get("warning_signs") or []),
    )
