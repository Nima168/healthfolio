"""Prescription summary: medicines and upcoming follow-ups.

Deterministic, from stored rows. Clear follow-ups that fall on the same date are shown on one
line ("Kidney function test + doctor visit"), in date order. Unclear items stay in their own
section, flagged `unclear` with the reason, so nothing extracted is hidden (decision 2026-10-11).
"""

from dataclasses import dataclass, field
from datetime import date

from app.models.extraction import ProcessingJob
from app.models.prescription import Medication, Suggestion


@dataclass(frozen=True)
class MedicationLine:
    name: str
    strength: str | None
    instructions: str | None
    duration_text: str | None
    unclear: bool = False
    reason: str | None = None


@dataclass(frozen=True)
class FollowUpLine:
    due_date: date | None  # None for an approximate timing (see when_text) or an unclear one
    description: str
    unclear: bool = False
    reason: str | None = None
    when_text: str | None = None  # the timing as written, shown when there is no exact date


@dataclass
class PrescriptionSummary:
    prescribed_on: date | None
    date_text: str | None
    prescriber_name: str | None
    medications: list[MedicationLine] = field(default_factory=list)
    follow_ups: list[FollowUpLine] = field(default_factory=list)
    reminders: str = "none"  # "available": can be added; "added": already added; "none": nothing to add


def addable(suggestion: Suggestion) -> bool:
    """A follow-up that may be added to Checkups and Follow-ups: clear, dated, and not yet added."""
    return suggestion.status == "pending" and suggestion.review_reason is None and suggestion.due_date is not None


def summarise_prescription(
    job: ProcessingJob, medications: list[Medication], suggestions: list[Suggestion]
) -> PrescriptionSummary:
    summary = PrescriptionSummary(
        prescribed_on=job.document_date, date_text=job.report_date_text, prescriber_name=job.prescriber_name
    )
    summary.medications = [
        MedicationLine(
            m.name, m.strength, m.dosage_text, m.duration_text, unclear=bool(m.review_reason), reason=m.review_reason
        )
        for m in medications
    ]

    by_date: dict[date, list[str]] = {}
    unclear: list[FollowUpLine] = []
    for suggestion in suggestions:
        if suggestion.review_reason:
            unclear.append(
                FollowUpLine(
                    suggestion.due_date,
                    suggestion.suggested_value,
                    unclear=True,
                    reason=suggestion.review_reason,
                    when_text=suggestion.original_text,
                )
            )
            continue
        if suggestion.due_date is None:  # approximate, e.g. "mid-January 2027"
            unclear.append(FollowUpLine(None, suggestion.suggested_value, when_text=suggestion.original_text))
            continue
        descriptions = by_date.setdefault(suggestion.due_date, [])
        if suggestion.suggested_value not in descriptions:
            descriptions.append(suggestion.suggested_value)
    lines = [FollowUpLine(due, " + ".join(items)) for due, items in by_date.items()] + unclear
    # Date order; items without an exact date last.
    summary.follow_ups = sorted(lines, key=lambda line: (line.due_date is None, line.due_date or date.max))

    if any(addable(s) for s in suggestions):
        summary.reminders = "available"
    elif any(s.status == "accepted" for s in suggestions):
        summary.reminders = "added"
    return summary
