"""Validate consultation notes, imaging reports, and other test reports (AI_spec.md Sections 4.5, 9.2).

Deterministic code only; everything is kept exactly as written (decision 2026-10-12). The result is a
JSON-safe `details` dict stored on the processing job, plus follow-ups for consultation notes, which
use the prescription rules with relative timings counted from the consultation date.
"""

import re
from typing import Any

from app.ai.prescription_validation import PrescriptionHeader, ValidatedFollowUp, _clean, _follow_up, header_date
from app.ai.schema import ConsultationPayload, ImagingPayload, OtherReportPayload
from app.ai.validation import parse_number

_PLAIN_NUMBER = re.compile(r"^\s*[-+]?\d[\d,]*(?:\.\d+)?\s*$")


def _one_line(value: str | None, limit: int) -> str | None:
    """As written, with line breaks from the page layout joined into single spaces."""
    return _clean(" ".join((value or "").split()), limit)


def _texts(items: list[str], limit: int = 500) -> list[str]:
    """Cleaned, without empties or exact repeats, in document order."""
    seen, kept = set(), []
    for item in items:
        text = _one_line(item, limit)
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            kept.append(text)
    return kept


def _iso(value: str | None, printed: str | None) -> str | None:
    """The calendar date as YYYY-MM-DD, or None when missing or ambiguous as printed (app/ai/dates.py)."""
    parsed = header_date(value, printed)[0]
    return parsed.isoformat() if parsed else None


def validate_consultation(
    payload: ConsultationPayload, page_count: int | None
) -> tuple[dict[str, Any], list[ValidatedFollowUp]]:
    visit_text = _clean(payload.visit_date_text, 100)
    visit_on, visit_ambiguous = header_date(payload.visit_date, visit_text)
    details = {
        "visit_date": visit_on.isoformat() if visit_on else None,
        "visit_text": visit_text,
        "clinician_name": _clean(payload.clinician_name, 200),
        "symptoms": _texts(payload.symptoms),
        "observations": _texts(payload.observations),
        "assessment": _texts(payload.assessment),
        "plan": _texts(payload.plan),
    }
    # "After 4 weeks" counts from the consultation date.
    base = PrescriptionHeader(visit_on, visit_text, None, visit_ambiguous)
    follow_ups: list[ValidatedFollowUp] = []
    seen: set[tuple[str, object]] = set()
    for item in payload.follow_ups:
        follow_up = _follow_up(item, base, page_count)
        key = (follow_up.description.casefold(), follow_up.due_date or follow_up.date_text)
        if key not in seen:
            seen.add(key)
            follow_ups.append(follow_up)
    return details, follow_ups


def validate_imaging(payload: ImagingPayload) -> dict[str, Any]:
    written = payload.is_written_report and bool(payload.findings or payload.impression)
    return {
        "is_written_report": written,
        "exam_name": _clean(payload.exam_name, 200),
        "report_id": _clean(payload.report_id, 100),
        "facility_name": _clean(payload.facility_name, 200),
        "exam_date": _iso(payload.exam_date, payload.exam_date_text),
        "exam_text": _clean(payload.exam_date_text, 100),
        "report_date": _iso(payload.report_date, payload.report_date_text),
        "report_text": _clean(payload.report_date_text, 100),
        "body_region": _clean(payload.body_region, 200),
        "findings": _texts(payload.findings) if written else [],
        "impression": _texts(payload.impression) if written else [],
        "uncertainty": _texts(payload.uncertainty) if written else [],
    }


def validate_test_report(payload: OtherReportPayload) -> dict[str, Any]:
    measurements, seen = [], set()
    for item in payload.measurements:
        name, value = _clean(item.name, 200), _clean(item.value_text, 100)
        if not name or not value or (name.casefold(), value) in seen:
            continue
        seen.add((name.casefold(), value))
        measurements.append(
            {
                "name": name,
                "value_text": value,
                "unit": _clean(item.unit, 50),
                "reference_range_text": _clean(item.reference_range_text, 200),
                "unclear": item.confidence != "high",
            }
        )
    interpretations = [
        {"source": item.source, "confirmed": item.confirmed, "text": text}
        for item in payload.interpretations
        if (text := _one_line(item.text, 1000))
    ]
    return {
        "test_type": _clean(payload.test_type, 50),
        "test_name": _clean(payload.test_name, 200),
        "report_id": _clean(payload.report_id, 100),
        "facility_name": _clean(payload.facility_name, 200),
        "report_form": payload.report_form,
        "test_date": _iso(payload.test_date, payload.test_date_text),
        "test_text": _clean(payload.test_date_text, 100),
        "measurements": measurements,
        "interpretations": interpretations,
        "visual_content": _texts(payload.visual_content, 200),
    }


def plain_number(value_text: str):
    """Only a plain number is compared with a range; "<5", "+38°", or text are not."""
    return parse_number(value_text) if _PLAIN_NUMBER.match(value_text) else None
