"""Summaries for consultation notes, imaging, pathology, specialist, and other test reports (e.g. ECG).

Built from the processing job's `details` (exactly as written) and, for consultation notes, the
follow-up suggestions. Test-report measurements outside their printed range are flagged high/low with
the lab-summary range rule; measurements without a printed range are never judged.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.ai.report_validation import plain_number
from app.models.extraction import ProcessingJob
from app.models.prescription import Suggestion
from app.services.lab_summary import range_check
from app.services.prescription_summary import FollowUpLine, summarise_prescription


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


@dataclass
class ConsultationSummary:
    visit_date: date | None
    visit_text: str | None
    clinician_name: str | None
    symptoms: list[str] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    assessment: list[str] = field(default_factory=list)
    plan: list[str] = field(default_factory=list)
    follow_ups: list[FollowUpLine] = field(default_factory=list)
    reminders: str = "none"


@dataclass
class ImagingSummary:
    is_written_report: bool
    exam_name: str | None
    report_id: str | None
    facility_name: str | None
    exam_date: date | None
    exam_text: str | None
    report_date: date | None
    report_text: str | None
    body_region: str | None
    findings: list[str] = field(default_factory=list)
    impression: list[str] = field(default_factory=list)
    uncertainty: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Measurement:
    name: str
    value_text: str
    unit: str | None
    reference_range_text: str | None
    flag: str | None  # "high" / "low" against the printed range; None when in range or not comparable
    unclear: bool


@dataclass(frozen=True)
class Interpretation:
    source: str  # "machine", "physician", "other"
    confirmed: bool
    text: str


@dataclass
class DiagnosticTestSummary:
    test_type: str | None
    test_name: str | None
    report_id: str | None
    facility_name: str | None
    report_form: str
    test_date: date | None
    test_text: str | None
    measurements: list[Measurement] = field(default_factory=list)
    interpretations: list[Interpretation] = field(default_factory=list)
    visual_content: list[str] = field(default_factory=list)


def summarise_consultation(job: ProcessingJob, suggestions: list[Suggestion]) -> ConsultationSummary:
    details = job.details or {}
    follow_ups = summarise_prescription(job, [], suggestions)
    return ConsultationSummary(
        visit_date=_date(details.get("visit_date")),
        visit_text=details.get("visit_text"),
        clinician_name=details.get("clinician_name"),
        symptoms=list(details.get("symptoms") or []),
        observations=list(details.get("observations") or []),
        assessment=list(details.get("assessment") or []),
        plan=list(details.get("plan") or []),
        follow_ups=follow_ups.follow_ups,
        reminders=follow_ups.reminders,
    )


def summarise_imaging(job: ProcessingJob) -> ImagingSummary:
    details = job.details or {}
    return ImagingSummary(
        is_written_report=bool(details.get("is_written_report")),
        exam_name=details.get("exam_name"),
        report_id=details.get("report_id"),
        facility_name=details.get("facility_name"),
        exam_date=_date(details.get("exam_date")),
        exam_text=details.get("exam_text"),
        report_date=_date(details.get("report_date")),
        report_text=details.get("report_text"),
        body_region=details.get("body_region"),
        findings=list(details.get("findings") or []),
        impression=list(details.get("impression") or []),
        uncertainty=list(details.get("uncertainty") or []),
    )


def _flag(value_text: str, range_text: str | None) -> str | None:
    value = plain_number(value_text)
    if value is None or not range_text:
        return None
    return {"above": "high", "below": "low"}.get(range_check(value, range_text) or "")


_SOURCE_ORDER = {"machine": 0, "physician": 1, "other": 2}


def summarise_test_report(job: ProcessingJob) -> DiagnosticTestSummary:
    details = job.details or {}
    return DiagnosticTestSummary(
        test_type=details.get("test_type"),
        test_name=details.get("test_name"),
        report_id=details.get("report_id"),
        facility_name=details.get("facility_name"),
        report_form=details.get("report_form") or "unknown",
        test_date=_date(details.get("test_date")),
        test_text=details.get("test_text"),
        measurements=_measurements(details.get("measurements")),
        interpretations=_interpretations(details.get("interpretations")),
        visual_content=list(details.get("visual_content") or []),
    )


def _measurements(items: list[dict] | None) -> list[Measurement]:
    return [
        Measurement(
            m["name"],
            m["value_text"],
            m.get("unit"),
            m.get("reference_range_text"),
            _flag(m["value_text"], m.get("reference_range_text")),
            bool(m.get("unclear")),
        )
        for m in items or []
    ]


def _interpretations(items: list[dict] | None) -> list[Interpretation]:
    """Machine first, then physician, then other (stable within each), as in the agreed format."""
    return sorted(
        (Interpretation(item["source"], bool(item.get("confirmed")), item["text"]) for item in items or []),
        key=lambda item: _SOURCE_ORDER.get(item.source, 2),
    )


@dataclass
class PathologySummary:
    """Exactly as written. Header fields are None and sections empty when the report does not have them."""

    test_name: str | None
    specimen_label: str | None
    report_id: str | None
    facility_name: str | None
    pathologist_name: str | None
    collected_date: date | None
    collected_text: str | None
    received_date: date | None
    received_text: str | None
    reported_date: date | None
    reported_text: str | None
    specimen: list[str] = field(default_factory=list)
    clinical_history: list[str] = field(default_factory=list)
    gross_description: list[str] = field(default_factory=list)
    microscopic_description: list[str] = field(default_factory=list)
    diagnosis: list[str] = field(default_factory=list)
    tumour_details: list[str] = field(default_factory=list)
    special_tests: list[str] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)


_PATHOLOGY_TEXTS = (
    "test_name",
    "specimen_label",
    "report_id",
    "facility_name",
    "pathologist_name",
    "collected_text",
    "received_text",
    "reported_text",
)
_PATHOLOGY_LISTS = (
    "specimen",
    "clinical_history",
    "gross_description",
    "microscopic_description",
    "diagnosis",
    "tumour_details",
    "special_tests",
    "comments",
)


def summarise_pathology(job: ProcessingJob) -> PathologySummary:
    details = job.details or {}
    return PathologySummary(
        **{name: details.get(name) for name in _PATHOLOGY_TEXTS},
        collected_date=_date(details.get("collected_date")),
        received_date=_date(details.get("received_date")),
        reported_date=_date(details.get("reported_date")),
        **{name: list(details.get(name) or []) for name in _PATHOLOGY_LISTS},
    )


@dataclass
class SpecialistSummary:
    """Exactly as written. Header fields are None and sections empty when the report does not have them."""

    test_name: str | None
    specialty: str | None
    report_id: str | None
    facility_name: str | None
    reported_by: str | None
    test_date: date | None
    test_text: str | None
    reason: list[str] = field(default_factory=list)
    measurements: list[Measurement] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    conclusions: list[Interpretation] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    follow_ups: list[FollowUpLine] = field(default_factory=list)
    reminders: str = "none"
    visual_content: list[str] = field(default_factory=list)


def summarise_specialist(job: ProcessingJob, suggestions: list[Suggestion]) -> SpecialistSummary:
    details = job.details or {}
    follow_ups = summarise_prescription(job, [], suggestions)
    return SpecialistSummary(
        test_name=details.get("test_name"),
        specialty=details.get("specialty"),
        report_id=details.get("report_id"),
        facility_name=details.get("facility_name"),
        reported_by=details.get("reported_by"),
        test_date=_date(details.get("test_date")),
        test_text=details.get("test_text"),
        reason=list(details.get("reason") or []),
        measurements=_measurements(details.get("measurements")),
        findings=list(details.get("findings") or []),
        conclusions=_interpretations(details.get("conclusions")),
        recommendations=list(details.get("recommendations") or []),
        follow_ups=follow_ups.follow_ups,
        reminders=follow_ups.reminders,
        visual_content=list(details.get("visual_content") or []),
    )
