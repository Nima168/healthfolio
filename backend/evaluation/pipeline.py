"""Run one generated document through the app's real reading pipeline, and keep the result as JSON.

Same steps as the worker (backend/app/services/extraction_service.py) but without a database:
upload quality check → prepare (PyMuPDF / Tesseract / vision fallback) → Groq → validation rules.
"""

import time
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from app.ai.discharge_validation import validate_discharge
from app.ai.extractor import (
    CONSULTATION_PROMPT_VERSION,
    DISCHARGE_PROMPT_VERSION,
    IMAGING_PROMPT_VERSION,
    PRESCRIPTION_PROMPT_VERSION,
    PROMPT_VERSION,
    ExtractionError,
    GroqExtractor,
)
from app.ai.prescription_validation import validate_prescription
from app.ai.reading import Ocr, ReadingError, prepare
from app.ai.report_validation import validate_consultation, validate_imaging
from app.ai.validation import validate_payload
from app.core.config import Settings
from app.services import upload_quality
from app.services.lab_summary import classify

PROMPT_VERSIONS = {
    "lab_report": PROMPT_VERSION,
    "prescription": PRESCRIPTION_PROMPT_VERSION,
    "discharge_summary": DISCHARGE_PROMPT_VERSION,
    "consultation_note": CONSULTATION_PROMPT_VERSION,
    "imaging_report": IMAGING_PROMPT_VERSION,
}


def _plain(value: Any) -> Any:
    """JSON-friendly copies of dataclasses, dates, and decimals."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    return value


def _lab_items(results) -> list[dict]:
    items = []
    for r in results:
        row = SimpleNamespace(
            reference_range_text=r.reference_range_text,
            value_numeric=r.value_numeric,
            value_text=r.value_text,
            validation_findings=r.findings,
            confidence=r.confidence,
        )
        group, _ = classify(row)
        items.append(
            {
                "name": r.name,
                "value": r.value_text,
                "unit": r.unit,
                "range": r.reference_range_text,
                "date": r.observed_at,
                "confidence": r.confidence,
                "needs_review": r.needs_review,
                "findings": list(r.findings),
                "group": group,
            }
        )
    return items


def _medicines(medicines) -> list[dict]:
    return [
        {
            "name": m.name,
            "strength": m.strength,
            "instructions": m.instructions,
            "duration": m.duration_text,
            "needs_review": m.review_reason is not None,
        }
        for m in medicines
    ]


def _follow_ups(follow_ups) -> list[dict]:
    return [
        {"description": f.description, "due": f.due_date, "needs_review": f.review_reason is not None}
        for f in follow_ups
    ]


def _extract(extractor: GroqExtractor, kind: str, prepared) -> tuple[dict, Any]:
    if kind == "lab_report":
        outcome = extractor.extract(prepared)
        results = validate_payload(outcome.payload, prepared.page_count, date.today())
        return {"labs": _lab_items(results), "date": outcome.payload.report_date}, outcome
    if kind == "prescription":
        outcome = extractor.extract_prescription(prepared)
        header, medicines, follow_ups = validate_prescription(outcome.payload, prepared.page_count)
        return {
            "date": header.prescribed_on,
            "medicines": _medicines(medicines),
            "follow_ups": _follow_ups(follow_ups),
        }, outcome
    if kind == "discharge_summary":
        outcome = extractor.extract_discharge(prepared)
        v = validate_discharge(outcome.payload, prepared.page_count)
        labs = [
            {
                "name": r.name,
                "value": r.value_text,
                "unit": r.unit,
                "range": r.reference_range_text,
                "date": r.observed_at,
                "confidence": r.confidence,
                "needs_review": r.confidence != "high",
                "findings": [],
                "group": None,
            }
            for r in v.results
        ]
        return {
            "date": v.header.discharged_on,
            "admitted": v.header.admitted_on,
            "diagnoses": v.diagnoses,
            "labs": labs,
            "medicines": _medicines(v.medications),
            "follow_ups": _follow_ups(v.follow_ups),
        }, outcome
    if kind == "consultation_note":
        outcome = extractor.extract_report(prepared, kind)
        details, follow_ups = validate_consultation(outcome.payload, prepared.page_count)
        lists = {key: list(details.get(key) or []) for key in ("symptoms", "assessment", "plan")}
        return {"date": details.get("visit_date"), "lists": lists}, outcome
    outcome = extractor.extract_report(prepared, kind)
    details = validate_imaging(outcome.payload)
    lists = {key: list(details.get(key) or []) for key in ("findings", "impression")}
    return {"date": details.get("exam_date"), "lists": lists}, outcome


def run_document(
    content: bytes,
    kind: str,
    copy_type: str,
    *,
    settings: Settings,
    extractor: GroqExtractor,
    ocr: Ocr | None,
    max_waits: int = 6,
    wait_seconds: float = 65,
) -> dict:
    """The result of reading one document, as a JSON-friendly dict. Temporary AI errors are waited out."""
    result: dict[str, Any] = {"kind": kind, "copy_type": copy_type, "prompt_version": PROMPT_VERSIONS[kind]}
    quality = upload_quality.check(content, "application/pdf")
    result["upload_rejected"] = quality.problem is not None
    result["upload_problem"] = quality.message() if quality.problem else None

    started = time.perf_counter()
    try:
        prepared = prepare(content, "application/pdf", copy_type, ocr=ocr, min_confidence=settings.ocr_min_confidence)
    except ReadingError as exc:
        result.update(error=exc.category, seconds_reading=round(time.perf_counter() - started, 2))
        return result
    result["seconds_reading"] = round(time.perf_counter() - started, 2)
    result["method"] = prepared.method
    result["ocr_confidence"] = prepared.ocr_confidence
    result["ocr_text"] = "\n".join(p.text for p in prepared.texts if p.source == "ocr")
    result["pages"] = prepared.page_count

    for attempt in range(max_waits + 1):
        started = time.perf_counter()
        try:
            extracted, outcome = _extract(extractor, kind, prepared)
        except ExtractionError as exc:
            if exc.transient and attempt < max_waits:
                time.sleep(wait_seconds)  # the provider's per-minute limit
                continue
            result["error"] = exc.category
            return result
        result["seconds_ai"] = round(time.perf_counter() - started, 2)
        result["tokens"] = {"input": outcome.input_tokens, "output": outcome.output_tokens}
        result["extracted"] = _plain(extracted)
        return _plain(result)
    return result
