"""Medication records the user keeps (backend_spec.md Section 7.3).

Medicines come from documents (status "unknown": never inferred as being taken) or are added by the
user. Only the user sets "taking" or "stopped". Every change keeps the values before it in
`medication_history`, so nothing is erased. No reminders (out of scope, goal_spec.md Section 7).
"""

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.document import Document
from app.models.prescription import Medication, MedicationHistory
from app.repositories.auth import AuditRepository
from app.schemas.medications import (
    MedicationCreate,
    MedicationHistoryEntry,
    MedicationHistoryResponse,
    MedicationListResponse,
    MedicationResponse,
    MedicationUpdate,
)

# The values kept in history and editable by the user.
TRACKED_FIELDS = (
    "name",
    "strength",
    "dosage_text",
    "duration_text",
    "prescriber_name",
    "start_date",
    "end_date",
    "notes",
    "status",
)


def _json(value: Any) -> Any:
    return value.isoformat() if isinstance(value, date) else value


def snapshot(medication: Medication) -> dict[str, Any]:
    return {field: _json(getattr(medication, field)) for field in TRACKED_FIELDS}


def user_touched(medication: Medication) -> bool:
    """Changed by the user: kept when the document is read again or deleted."""
    return medication.user_updated_at is not None


class MedicationService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.audit = AuditRepository(session)

    def _response(self, medication: Medication, document: Document | None, edited: bool) -> MedicationResponse:
        live = document is not None and document.deleted_at is None
        return MedicationResponse(
            id=medication.id,
            name=medication.name,
            strength=medication.strength,
            dosage_text=medication.dosage_text,
            duration_text=medication.duration_text,
            prescriber_name=medication.prescriber_name,
            start_date=medication.start_date,
            end_date=medication.end_date,
            notes=medication.notes,
            status=medication.status,
            origin=medication.origin,
            status_confirmed=medication.status_confirmed_at is not None,
            edited=edited and medication.origin != "user_entered",
            review_reason=medication.review_reason,
            source_document_id=medication.source_document_id,
            source_document_title=document.title if live else None,
            source_document_date=document.document_date if live else None,
            source_document_deleted=document is not None and not live,
            updated_at=medication.updated_at,
        )

    def _get(self, user_id: uuid.UUID, medication_id: uuid.UUID) -> Medication:
        medication = self.session.scalar(
            select(Medication).where(
                Medication.id == medication_id, Medication.user_id == user_id, Medication.deleted_at.is_(None)
            )
        )
        if medication is None:
            raise ApiError(404)
        return medication

    def _document(self, medication: Medication) -> Document | None:
        if medication.source_document_id is None:
            return None
        return self.session.get(Document, medication.source_document_id)

    def edited_ids(self, user_id: uuid.UUID, medication_ids: list[uuid.UUID]) -> set[uuid.UUID]:
        """Medicines whose details (not only the status) the user changed."""
        if not medication_ids:
            return set()
        return set(
            self.session.scalars(
                select(MedicationHistory.medication_id).where(
                    MedicationHistory.user_id == user_id,
                    MedicationHistory.change_origin == "edited",
                    MedicationHistory.medication_id.in_(medication_ids),
                )
            )
        )

    def _one(self, medication: Medication) -> MedicationResponse:
        edited = medication.id in self.edited_ids(medication.user_id, [medication.id])
        return self._response(medication, self._document(medication), edited)

    def _record(self, medication: Medication, change: str, before: dict, now: datetime) -> None:
        after = snapshot(medication)
        changes = {field: [before[field], after[field]] for field in TRACKED_FIELDS if before[field] != after[field]}
        self.session.add(
            MedicationHistory(
                medication_id=medication.id,
                user_id=medication.user_id,
                change_origin=change,
                snapshot=before,
                changes=changes,
                changed_at=now,
            )
        )

    # ---------- read ----------

    def list(self, user_id: uuid.UUID) -> MedicationListResponse:
        """Taking now, then not confirmed, then stopped; newest documents first within each."""
        rows = self.session.execute(
            select(Medication, Document)
            .outerjoin(Document, Document.id == Medication.source_document_id)
            .where(Medication.user_id == user_id, Medication.deleted_at.is_(None))
            .order_by(
                case((Medication.status == "active", 0), (Medication.status == "unknown", 1), else_=2),
                Document.document_date.desc().nulls_last(),
                Medication.source_document_id,
                Medication.position,
                Medication.created_at,
            )
        )
        rows = list(rows)
        edited = self.edited_ids(user_id, [m.id for m, _ in rows])
        return MedicationListResponse(items=[self._response(m, d, m.id in edited) for m, d in rows])

    def history(self, user_id: uuid.UUID, medication_id: uuid.UUID) -> MedicationHistoryResponse:
        medication = self._get(user_id, medication_id)
        entries = self.session.scalars(
            select(MedicationHistory)
            .where(MedicationHistory.medication_id == medication.id)
            .order_by(MedicationHistory.changed_at.desc(), MedicationHistory.id)
        )
        return MedicationHistoryResponse(
            items=[
                MedicationHistoryEntry(
                    id=entry.id,
                    change=entry.change_origin,
                    changed_at=entry.changed_at,
                    changes=entry.changes,
                    snapshot=entry.snapshot,
                )
                for entry in entries
            ]
        )

    # ---------- write ----------

    def create(self, user_id: uuid.UUID, data: MedicationCreate) -> MedicationResponse:
        now = datetime.now(UTC)
        medication = Medication(
            user_id=user_id,
            name=data.name,
            strength=data.strength,
            dosage_text=data.dosage_text,
            duration_text=data.duration_text,
            prescriber_name=data.prescriber_name,
            start_date=data.start_date,
            end_date=data.end_date,
            notes=data.notes,
            status=data.status,
            origin="user_entered",
            status_confirmed_at=now if data.status != "unknown" else None,
            user_updated_at=now,
            source_location={},
        )
        self.session.add(medication)
        self.session.flush()
        self._record(medication, "added", dict.fromkeys(TRACKED_FIELDS), now)
        self.audit.record("medication.created", "success", user_id, {"medication_id": str(medication.id)})
        self.session.commit()
        return self._response(medication, None, edited=False)

    def update(self, user_id: uuid.UUID, medication_id: uuid.UUID, change: MedicationUpdate) -> MedicationResponse:
        medication = self._get(user_id, medication_id)
        before = snapshot(medication)
        sent = change.model_fields_set
        for field in TRACKED_FIELDS:
            if field not in sent:
                continue
            value = getattr(change, field)
            if field in ("name", "status") and value is None:
                continue  # required values cannot be cleared
            setattr(medication, field, value)
        if medication.start_date and medication.end_date and medication.end_date < medication.start_date:
            raise ApiError(
                422,
                "VALIDATION_ERROR",
                "The end date cannot be before the start date.",
                [{"field": "end_date", "issue": "The end date cannot be before the start date."}],
            )

        after = snapshot(medication)
        if after == before:
            return self._one(medication)
        now = datetime.now(UTC)
        details_changed = any(before[f] != after[f] for f in TRACKED_FIELDS if f != "status")
        if after["status"] != before["status"]:
            medication.status_confirmed_at = now if medication.status != "unknown" else None
        if details_changed:
            medication.review_reason = None  # the user has checked and corrected it
        medication.user_updated_at = now
        self._record(medication, "edited" if details_changed else "status_changed", before, now)
        self.audit.record(
            "medication.updated", "success", user_id, {"medication_id": str(medication.id), "status": medication.status}
        )
        self.session.commit()
        return self._one(medication)

    def delete(self, user_id: uuid.UUID, medication_id: uuid.UUID) -> None:
        """Removed from the list; the row and its history are kept (soft delete)."""
        medication = self._get(user_id, medication_id)
        now = datetime.now(UTC)
        before = snapshot(medication)
        medication.deleted_at = now
        medication.user_updated_at = now
        self._record(medication, "removed", before, now)
        self.audit.record("medication.deleted", "success", user_id, {"medication_id": str(medication.id)})
        self.session.commit()
