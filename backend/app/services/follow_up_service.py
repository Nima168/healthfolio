"""Checkups and follow-ups the user tracks (backend_spec.md Section 7.4).

No reminders are sent yet (deferred); this is the list and its status. "Overdue" is computed
from the due date, never stored (data_model_spec.md Section 5.6).
"""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.document import Document
from app.models.prescription import FollowUp
from app.repositories.auth import AuditRepository
from app.schemas.follow_ups import FollowUpListResponse, FollowUpResponse, FollowUpUpdate


def today() -> date:
    return datetime.now(UTC).date()


class FollowUpService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.audit = AuditRepository(session)

    def _response(self, follow_up: FollowUp, document_title: str | None) -> FollowUpResponse:
        return FollowUpResponse(
            id=follow_up.id,
            title=follow_up.title,
            kind=follow_up.kind,
            due_date=follow_up.due_date,
            status=follow_up.status,
            overdue=follow_up.status == "scheduled" and follow_up.due_date < today(),
            completed_at=follow_up.completed_at,
            source_document_id=follow_up.source_document_id,
            source_document_title=document_title,
        )

    def _title(self, follow_up: FollowUp) -> str | None:
        if follow_up.source_document_id is None:
            return None
        document = self.session.get(Document, follow_up.source_document_id)
        return document.title if document and document.deleted_at is None else None

    def list(self, user_id: uuid.UUID) -> FollowUpListResponse:
        """Scheduled first (soonest due first), then completed and cancelled."""
        rows = self.session.execute(
            select(FollowUp, Document.title, Document.deleted_at)
            .outerjoin(Document, Document.id == FollowUp.source_document_id)
            .where(FollowUp.user_id == user_id)
            .order_by(case((FollowUp.status == "scheduled", 0), else_=1), FollowUp.due_date, FollowUp.created_at)
        )
        return FollowUpListResponse(
            items=[self._response(f, title if deleted_at is None else None) for f, title, deleted_at in rows]
        )

    def update(self, user_id: uuid.UUID, follow_up_id: uuid.UUID, change: FollowUpUpdate) -> FollowUpResponse:
        follow_up = self.session.scalar(
            select(FollowUp).where(FollowUp.id == follow_up_id, FollowUp.user_id == user_id)
        )
        if follow_up is None:
            raise ApiError(404)
        follow_up.status = change.status
        follow_up.completed_at = datetime.now(UTC) if change.status == "completed" else None
        self.audit.record(
            "follow_up.updated", "success", user_id, {"follow_up_id": str(follow_up.id), "status": change.status}
        )
        self.session.commit()
        return self._response(follow_up, self._title(follow_up))
