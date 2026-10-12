"""Extracted results for a document (lab or prescription), re-extraction, and adding follow-ups."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.models.extraction import ACTIVE_JOB_STATUSES, Observation
from app.models.prescription import Condition, FollowUp, Medication, Suggestion
from app.repositories.auth import AuditRepository
from app.repositories.documents import DocumentRepository
from app.schemas.observations import (
    ConsultationSummaryResponse,
    DiagnosticTestSummaryResponse,
    DischargeSummaryResponse,
    DocumentExtractionResponse,
    ExtractionJobResponse,
    ImagingSummaryResponse,
    LabSummaryResponse,
    ObservationResponse,
    PrescriptionSummaryResponse,
)
from app.services import jobs
from app.services.discharge_summary import summarise_discharge
from app.services.lab_summary import summarise
from app.services.prescription_summary import addable, summarise_prescription
from app.services.report_summaries import summarise_consultation, summarise_imaging, summarise_test_report


class ObservationService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.documents = DocumentRepository(session)
        self.audit = AuditRepository(session)

    def _document(self, user_id: uuid.UUID, document_id: uuid.UUID):
        document = self.documents.get(user_id, document_id)
        if document is None:
            raise ApiError(404)
        return document

    def _response(self, observation: Observation) -> ObservationResponse:
        location = observation.source_location or {}
        return ObservationResponse(
            id=observation.id,
            name=observation.name,
            value_text=observation.value_text,
            value_numeric=observation.value_numeric,
            unit=observation.unit,
            reference_range_text=observation.reference_range_text,
            reference_low=observation.reference_low,
            reference_high=observation.reference_high,
            observed_at=observation.observed_at,
            observed_at_precision=observation.observed_at_precision,
            page=location.get("page"),
            source_snippet=location.get("snippet"),
            confidence=observation.confidence,
            needs_review=observation.needs_review,
            validation_findings=list(observation.validation_findings or []),
            notes=observation.notes,
        )

    # ---------- read ----------

    def _rows(self, model, user_id: uuid.UUID, document_id: uuid.UUID, job_id: uuid.UUID | None = None) -> list:
        """A document's extracted rows; with `job_id`, only those of that reading."""
        query = select(model).where(model.source_document_id == document_id, model.user_id == user_id)
        if job_id is not None:
            query = query.where(model.processing_job_id == job_id)
        if hasattr(model, "deleted_at"):
            query = query.where(model.deleted_at.is_(None))
        return list(self.session.scalars(query.order_by(model.position, model.created_at)))

    def for_document(self, user_id: uuid.UUID, document_id: uuid.UUID) -> DocumentExtractionResponse:
        document = self._document(user_id, document_id)
        job = jobs.latest_job(self.session, document.id)
        extracted = job is not None and job.status in ("completed", "completed_with_warnings")
        # Jobs from before prescriptions existed were all lab extractions.
        kind = (job.document_kind or "lab_report") if extracted and job else None

        # Only the latest reading is shown; an earlier one replaced by "Read again" is not.
        job_id = job.id if job is not None else None
        observations = self._rows(Observation, user_id, document.id, job_id)
        summary = prescription = discharge = consultation = imaging = test_report = None
        if kind == "lab_report":
            summary = LabSummaryResponse.model_validate(summarise(observations, job.report_date_text))
        elif kind == "discharge_summary":
            discharge = DischargeSummaryResponse.model_validate(
                summarise_discharge(
                    job,
                    self._rows(Condition, user_id, document.id, job_id),
                    observations,
                    self._rows(Medication, user_id, document.id, job_id),
                    self._rows(Suggestion, user_id, document.id, job_id),
                )
            )
        elif kind == "consultation_note":
            consultation = ConsultationSummaryResponse.model_validate(
                summarise_consultation(job, self._rows(Suggestion, user_id, document.id, job_id))
            )
        elif kind == "imaging_report":
            imaging = ImagingSummaryResponse.model_validate(summarise_imaging(job))
        elif kind == "test_report":
            test_report = DiagnosticTestSummaryResponse.model_validate(summarise_test_report(job))
        elif kind == "prescription":
            prescription = PrescriptionSummaryResponse.model_validate(
                summarise_prescription(
                    job,
                    self._rows(Medication, user_id, document.id, job_id),
                    self._rows(Suggestion, user_id, document.id, job_id),
                )
            )
        return DocumentExtractionResponse(
            extraction_enabled=self.settings.extraction_enabled,
            job=(
                ExtractionJobResponse(
                    status=job.status,
                    attempts=job.attempts,
                    error_category=job.error_category,
                    updated_at=job.updated_at,
                )
                if job
                else None
            ),
            document_kind=kind,
            items=[self._response(o) for o in observations],
            summary=summary,
            prescription=prescription,
            discharge=discharge,
            consultation=consultation,
            imaging=imaging,
            test_report=test_report,
        )

    # ---------- actions ----------

    def request_extraction(self, user_id: uuid.UUID, document_id: uuid.UUID) -> DocumentExtractionResponse:
        """Queue a (new) reading of a document: the first, a retry after a failure, or "Read again".

        AI reading varies from run to run, so a completed reading may be replaced. The earlier reading's
        rows are withdrawn; follow-ups the user already added are kept (data_model_spec.md Section 5.6).
        """
        document = self._document(user_id, document_id)
        job = jobs.latest_job(self.session, document.id)
        if job is not None and job.status in ACTIVE_JOB_STATUSES:
            raise ApiError(409, "EXTRACTION_IN_PROGRESS", "This document is already being processed.")
        if job is not None:
            self._withdraw_readings(document.id)

        jobs.enqueue_extraction(self.session, document, retry=job is not None)
        self.audit.record("ai.extraction_requested", "success", user_id, {"document_id": str(document.id)})
        self.session.commit()
        return self.for_document(user_id, document_id)

    def _withdraw_readings(self, document_id: uuid.UUID) -> None:
        now = datetime.now(UTC)
        for model in (Observation, Medication, Condition):
            self.session.execute(
                update(model)
                .where(model.source_document_id == document_id, model.deleted_at.is_(None))
                .values(deleted_at=now)
            )
        self.session.execute(
            update(Suggestion)
            .where(Suggestion.source_document_id == document_id, Suggestion.status == "pending")
            .values(status="superseded")
        )

    def add_follow_ups(self, user_id: uuid.UUID, document_id: uuid.UUID) -> DocumentExtractionResponse:
        """Add as reminders: turn the document's clear, dated follow-ups into tracked follow-ups.

        Only on this explicit request (DL_AI_spec.md Section 9.2). Items needing review are not added.
        """
        document = self._document(user_id, document_id)
        job = jobs.latest_job(self.session, document.id)
        to_add = [s for s in self._rows(Suggestion, user_id, document.id, job.id if job else None) if addable(s)]
        if not to_add:
            raise ApiError(409, "NOTHING_TO_ADD", "There are no follow-ups to add from this document.")

        now = datetime.now(UTC)
        existing = {
            (f.title.casefold(), f.due_date): f
            for f in self.session.scalars(
                select(FollowUp).where(FollowUp.user_id == user_id, FollowUp.source_document_id == document.id)
            )
        }
        for suggestion in to_add:
            # Already added from an earlier reading of this document: link it, don't add it twice.
            same = existing.get((suggestion.suggested_value.casefold(), suggestion.due_date))
            if same is not None:
                suggestion.status = "accepted"
                suggestion.reviewed_at = now
                suggestion.result_entity_id = same.id
                continue
            follow_up = FollowUp(
                user_id=user_id,
                title=suggestion.suggested_value,
                kind=suggestion.kind or "checkup",
                due_date=suggestion.due_date,
                status="scheduled",
                origin="suggestion_accepted",
                suggestion_id=suggestion.id,
                source_document_id=document.id,
            )
            self.session.add(follow_up)
            self.session.flush()
            suggestion.status = "accepted"
            suggestion.reviewed_at = now
            suggestion.result_entity_id = follow_up.id
        self.audit.record(
            "follow_up.added_from_document", "success", user_id, {"document_id": str(document.id), "count": len(to_add)}
        )
        self.session.commit()
        return self.for_document(user_id, document_id)
