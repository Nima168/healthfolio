"""Runs one extraction job end to end (backend_spec.md Sections 6.4–6.6, DL_AI_spec.md Section 13).

read original → prepare (PyMuPDF text for digital PDFs, Tesseract OCR for scanned copies, page images
for pages OCR cannot read) → [classify, only if the user chose no type] → organise into fields with the
AI model (Groq) → validate (deterministic) → persist.
Lab reports become observations; prescriptions become medications and follow-up suggestions.
"""

import logging
import time
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.discharge_validation import validate_discharge
from app.ai.extractor import (
    CLASSIFY_PROMPT_VERSION,
    CONSULTATION_PROMPT_VERSION,
    DISCHARGE_PROMPT_VERSION,
    IMAGING_PROMPT_VERSION,
    PRESCRIPTION_PROMPT_VERSION,
    PROMPT_VERSION,
    TEST_REPORT_PROMPT_VERSION,
    ExtractionError,
    GroqExtractor,
)
from app.ai.prescription_validation import ValidatedFollowUp, ValidatedMedication, validate_prescription
from app.ai.reading import Ocr, PreparedDocument, ReadingError, prepare
from app.ai.report_validation import validate_consultation, validate_imaging, validate_test_report
from app.ai.source_check import SourceText
from app.ai.validation import ValidatedResult, validate_payload
from app.core.config import Settings
from app.models.document import Document
from app.models.extraction import Observation, ProcessingJob
from app.models.prescription import Condition, Medication, Suggestion
from app.repositories.auth import AuditRepository
from app.services import jobs
from app.services.alert_service import AlertService
from app.services.storage import DocumentStorage, StorageError

logger = logging.getLogger(__name__)

TASK_VERSIONS = {
    "lab_report": PROMPT_VERSION,
    "prescription": PRESCRIPTION_PROMPT_VERSION,
    "discharge_summary": DISCHARGE_PROMPT_VERSION,
    "consultation_note": CONSULTATION_PROMPT_VERSION,
    "imaging_report": IMAGING_PROMPT_VERSION,
    "test_report": TEST_REPORT_PROMPT_VERSION,
}
# Upload types that decide the reading directly; anything else ("other", "not set") is classified first.
DIRECT_KINDS = ("lab_report", "prescription", "discharge_summary", "consultation_note", "imaging_report")


class JobCancelled(Exception):
    """The document was deleted (or the job cancelled) while the job was running."""


def _to_observation(job: ProcessingJob, item: ValidatedResult, position: int) -> Observation:
    return Observation(
        position=position,
        user_id=job.user_id,
        source_document_id=job.document_id,
        processing_job_id=job.id,
        kind="lab_result",
        name=item.name,
        value_text=item.value_text,
        value_numeric=item.value_numeric,
        unit=item.unit,
        reference_range_text=item.reference_range_text,
        reference_low=item.reference_low,
        reference_high=item.reference_high,
        observed_at=item.observed_at,
        observed_at_precision=item.observed_at_precision,
        source_location={"page": item.page, "snippet": item.snippet},
        origin="document_extracted",
        confidence=item.confidence,
        needs_review=item.needs_review,
        validation_findings=item.findings,
        notes=item.notes,
    )


def _medication_key(name: str, strength: str | None) -> tuple[str, str]:
    return " ".join(name.lower().split()), " ".join((strength or "").lower().split())


def _to_medication(job: ProcessingJob, item: ValidatedMedication, position: int) -> Medication:
    return Medication(
        position=position,
        user_id=job.user_id,
        source_document_id=job.document_id,
        processing_job_id=job.id,
        name=item.name,
        strength=item.strength,
        dosage_text=item.instructions,
        duration_text=item.duration_text,
        prescriber_name=job.prescriber_name,
        status="unknown",  # never inferred as active from a prescription (backend_spec.md Section 7.3)
        origin="document_extracted",
        confidence=item.confidence,
        review_reason=item.review_reason,
        source_location={"page": item.page, "snippet": item.snippet},
        notes=item.notes,
    )


def _to_suggestion(job: ProcessingJob, item: ValidatedFollowUp, position: int) -> Suggestion:
    return Suggestion(
        position=position,
        user_id=job.user_id,
        suggestion_type="follow_up",
        source_document_id=job.document_id,
        processing_job_id=job.id,
        suggested_value=item.description,
        kind=item.kind,
        original_text=item.date_text,
        due_date=item.due_date,
        due_date_basis=item.due_date_basis,
        confidence=item.confidence,
        review_reason=item.review_reason,
        source_location={"page": item.page, "snippet": item.snippet},
        notes=item.notes,
    )


class ExtractionRunner:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        storage: DocumentStorage,
        extractor: GroqExtractor,
        ocr: Ocr | None = None,
    ):
        self.session = session
        self.settings = settings
        self.storage = storage
        self.extractor = extractor
        self.ocr = ocr  # None: scanned pages are read by the AI from their images

    def _live_document(self, job: ProcessingJob) -> Document:
        self.session.refresh(job)
        document = self.session.get(Document, job.document_id)
        if job.status == "cancelled" or document is None or document.deleted_at is not None:
            raise JobCancelled
        return document

    def run(self, job: ProcessingJob) -> None:
        started = time.perf_counter()
        audit = AuditRepository(self.session)
        try:
            document = self._live_document(job)

            jobs.heartbeat(self.session, job, "reading")
            try:
                content = b"".join(self.storage.open(document.storage_key or ""))
            except (StorageError, ValueError) as exc:
                raise ExtractionError("file_unavailable", transient=True) from exc
            prepared = prepare(
                content,
                document.media_type,
                document.copy_type,
                ocr=self.ocr,
                min_confidence=self.settings.ocr_min_confidence,
            )
            job.reading_method = prepared.method
            job.ocr_confidence = prepared.ocr_confidence

            # The user's chosen type decides; the AI classifies only when none was chosen.
            kind = document.category if document.category in DIRECT_KINDS else None
            versions: list[str] = []
            job.input_tokens = job.output_tokens = 0
            if kind is None:
                jobs.heartbeat(self.session, job, "classifying")
                classified = self.extractor.classify(prepared)
                self._add_usage(job, classified.model, classified.input_tokens, classified.output_tokens)
                versions.append(CLASSIFY_PROMPT_VERSION)
                kind = classified.document_type
            job.document_kind = kind
            if kind == "discharge_summary" and prepared.page_count > 1:
                raise ReadingError("discharge_too_many_pages")  # one page only, due to AI reading limits

            if kind in TASK_VERSIONS:
                versions.append(TASK_VERSIONS[kind])
            job.prompt_version = "+".join(versions) or None

            jobs.heartbeat(self.session, job, f"extracting_{prepared.mode}")
            if kind == "lab_report":
                counts = self._lab_report(job, prepared)
            elif kind == "prescription":
                counts = self._prescription(job, prepared)
            elif kind == "discharge_summary":
                counts = self._discharge(job, prepared)
            elif kind in ("consultation_note", "imaging_report", "test_report"):
                counts = self._report(job, prepared, kind)
            else:  # not a supported kind of document: nothing to extract
                jobs.heartbeat(self.session, job, "validating")
                self._live_document(job)
                counts = {"results": 0, "needs_review": 0, "warnings": False}

            jobs.finish(self.session, job, "completed_with_warnings" if counts["warnings"] else "completed")
            self.session.flush()
            AlertService(self.session).try_sync(job.user_id)  # approved safety rules on the new results
            audit.record(
                "ai.extraction_completed",
                "success",
                job.user_id,
                {
                    "job_id": str(job.id),
                    "document_kind": kind,
                    "results": counts["results"],
                    "needs_review": counts["needs_review"],
                },
            )
            self.session.commit()
            outcome_label = job.status
        except JobCancelled:
            self.session.rollback()
            outcome_label = "cancelled"
        except ReadingError as exc:
            self._fail(job, exc.category, audit)
            outcome_label = "failed"
        except ExtractionError as exc:
            self.session.rollback()
            if exc.transient and jobs.schedule_retry(
                self.session, job, exc.category, self.settings.extraction_max_attempts
            ):
                outcome_label = "retry_scheduled"
            else:
                jobs.finish(self.session, job, "failed", exc.category)
                audit.record(
                    "ai.extraction_failed", "failure", job.user_id, {"job_id": str(job.id), "reason": exc.category}
                )
                outcome_label = "failed"
            self.session.commit()
        except Exception:
            self.session.rollback()
            logger.exception("extraction job crashed", extra={"job_id": str(job.id)})
            self._fail(job, "internal_error", audit)
            outcome_label = "failed"

        # IDs, sizes, and timings only: never document text, prompts, or responses.
        logger.info(
            "extraction job finished",
            extra={
                "job_id": str(job.id),
                "outcome": outcome_label,
                "error_category": job.error_category,
                "attempt": job.attempts,
                "model": job.model_version,
                # Not named "*token*": the log redactor masks those keys.
                "ai_usage": {"input": job.input_tokens, "output": job.output_tokens},
                "reading_method": job.reading_method,
                "duration_ms": round((time.perf_counter() - started) * 1000),
            },
        )

    @staticmethod
    def _add_usage(job: ProcessingJob, model: str, input_tokens: int, output_tokens: int) -> None:
        job.model_version = model
        job.input_tokens = (job.input_tokens or 0) + input_tokens
        job.output_tokens = (job.output_tokens or 0) + output_tokens

    def _lab_report(self, job: ProcessingJob, prepared: PreparedDocument) -> dict:
        outcome = self.extractor.extract(prepared)
        self._add_usage(job, outcome.model, outcome.input_tokens, outcome.output_tokens)
        printed_date = (outcome.payload.report_date_text or "").strip()
        job.report_date_text = printed_date[:100] or None

        jobs.heartbeat(self.session, job, "validating")
        results = validate_payload(
            outcome.payload, prepared.page_count, datetime.now(UTC).date(), SourceText.of(prepared)
        )

        self._live_document(job)  # deleted while we were waiting for the model?
        for position, item in enumerate(results):
            self.session.add(_to_observation(job, item, position))
        needs_review = sum(item.needs_review for item in results)
        return {
            "results": len(results),
            "needs_review": needs_review,
            "warnings": bool(outcome.payload.warnings) or needs_review > 0,
        }

    def _report(self, job: ProcessingJob, prepared: PreparedDocument, kind: str) -> dict:
        """Consultation note, imaging report, or other test report: kept exactly as written in job.details."""
        outcome = self.extractor.extract_report(prepared, kind)
        self._add_usage(job, outcome.model, outcome.input_tokens, outcome.output_tokens)
        follow_ups = []
        if kind == "consultation_note":
            details, follow_ups = validate_consultation(outcome.payload, prepared.page_count)
            job.report_date_text = details["visit_text"]
            date_value = details["visit_date"]
            unclear = sum(item.review_reason is not None for item in follow_ups)
            items = sum(len(details[key]) for key in ("symptoms", "observations", "assessment", "plan"))
        elif kind == "imaging_report":
            details = validate_imaging(outcome.payload)
            job.report_date_text = details["exam_text"]
            date_value = details["exam_date"]
            unclear = 0 if details["is_written_report"] else 1  # scan images only: nothing read
            items = len(details["findings"]) + len(details["impression"])
        else:
            details = validate_test_report(outcome.payload)
            job.report_date_text = details["test_text"]
            date_value = details["test_date"]
            unclear = sum(m["unclear"] for m in details["measurements"])
            items = len(details["measurements"]) + len(details["interpretations"])
        job.details = details
        job.document_date = date.fromisoformat(date_value) if date_value else None

        jobs.heartbeat(self.session, job, "validating")
        self._live_document(job)  # deleted while we were waiting for the model?
        for position, follow_up in enumerate(follow_ups):
            self.session.add(_to_suggestion(job, follow_up, position))
        return {
            "results": items + len(follow_ups),
            "needs_review": unclear,
            "warnings": bool(outcome.payload.warnings) or unclear > 0,
        }

    def _discharge(self, job: ProcessingJob, prepared: PreparedDocument) -> dict:
        outcome = self.extractor.extract_discharge(prepared)
        self._add_usage(job, outcome.model, outcome.input_tokens, outcome.output_tokens)
        validated = validate_discharge(outcome.payload, prepared.page_count, SourceText.of(prepared))
        header = validated.header
        job.document_date = header.discharged_on
        job.report_date_text = header.discharged_text
        job.details = {
            "facility_name": header.facility_name,
            "admitted_on": header.admitted_on.isoformat() if header.admitted_on else None,
            "admitted_text": header.admitted_text,
            "discharged_on": header.discharged_on.isoformat() if header.discharged_on else None,
            "discharged_text": header.discharged_text,
            "warning_signs": validated.warning_signs,
        }

        jobs.heartbeat(self.session, job, "validating")
        self._live_document(job)  # deleted while we were waiting for the model?
        for position, name in enumerate(validated.diagnoses):
            self.session.add(
                Condition(
                    position=position,
                    user_id=job.user_id,
                    source_document_id=job.document_id,
                    processing_job_id=job.id,
                    name=name,
                    status="unknown",
                    origin="document_extracted",
                )
            )
        for position, result in enumerate(validated.results):
            self.session.add(
                Observation(
                    position=position,
                    user_id=job.user_id,
                    source_document_id=job.document_id,
                    processing_job_id=job.id,
                    kind="lab_result",
                    name=result.name,
                    value_text=result.value_text,
                    value_numeric=result.value_numeric,
                    unit=result.unit,
                    reference_range_text=result.reference_range_text,
                    observed_at=result.observed_at,
                    observed_at_precision="day" if result.observed_at else None,
                    source_location={"page": result.page, "snippet": None},
                    origin="document_extracted",
                    confidence=result.confidence,
                    needs_review=result.needs_review,
                    validation_findings=result.findings,
                )
            )
        self._add_medications(job, validated.medications)
        for position, follow_up in enumerate(validated.follow_ups):
            self.session.add(_to_suggestion(job, follow_up, position))
        unclear = sum(item.review_reason is not None for item in [*validated.medications, *validated.follow_ups])
        unclear += sum(result.needs_review for result in validated.results)
        return {
            "results": len(validated.results) + len(validated.medications) + len(validated.follow_ups),
            "needs_review": unclear,
            "warnings": bool(outcome.payload.warnings) or unclear > 0,
        }

    def _add_medications(self, job: ProcessingJob, medications: list[ValidatedMedication]) -> None:
        """Save the medicines read; one the user already changed (kept by "Read again") is re-linked, not doubled.

        A kept medicine matches on the same name and strength (ignoring case and spacing).
        """
        kept = list(
            self.session.scalars(
                select(Medication).where(
                    Medication.source_document_id == job.document_id,
                    Medication.deleted_at.is_(None),
                    Medication.user_updated_at.is_not(None),
                )
            )
        )
        by_key = {_medication_key(m.name, m.strength): m for m in kept}
        for position, item in enumerate(medications):
            match = by_key.pop(_medication_key(item.name, item.strength), None)
            if match is not None:
                match.processing_job_id = job.id  # shown in the new reading, with the user's values
                match.position = position
            else:
                self.session.add(_to_medication(job, item, position))

    def _prescription(self, job: ProcessingJob, prepared: PreparedDocument) -> dict:
        outcome = self.extractor.extract_prescription(prepared)
        self._add_usage(job, outcome.model, outcome.input_tokens, outcome.output_tokens)
        header, medications, follow_ups = validate_prescription(
            outcome.payload, prepared.page_count, SourceText.of(prepared)
        )
        job.report_date_text = header.date_text
        job.document_date = header.prescribed_on
        job.prescriber_name = header.prescriber_name

        jobs.heartbeat(self.session, job, "validating")
        self._live_document(job)  # deleted while we were waiting for the model?
        self._add_medications(job, medications)
        for position, follow_up in enumerate(follow_ups):
            self.session.add(_to_suggestion(job, follow_up, position))
        needs_review = sum(item.review_reason is not None for item in [*medications, *follow_ups])
        return {
            "results": len(medications) + len(follow_ups),
            "needs_review": needs_review,
            "warnings": bool(outcome.payload.warnings) or needs_review > 0,
        }

    def _fail(self, job: ProcessingJob, category: str, audit: AuditRepository) -> None:
        self.session.rollback()
        jobs.finish(self.session, job, "failed", category)
        audit.record("ai.extraction_failed", "failure", job.user_id, {"job_id": str(job.id), "reason": category})
        self.session.commit()
