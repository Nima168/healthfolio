"""The dashboard: a short overview built from the user's existing records (frontend_spec.md Section 6).

Nothing is calculated here that the other pages do not already show; missing information is reported as
missing, never as good health.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.alerts import Alert
from app.models.document import Document
from app.models.extraction import ACTIVE_JOB_STATUSES
from app.models.prescription import FollowUp, Medication, Suggestion
from app.services import jobs
from app.services.alert_service import AlertService
from app.services.prescription_summary import addable
from app.services.profile_service import SINGLE_FIELDS, ProfileService
from app.services.timeline_service import TimelineService
from app.services.vitals_service import VitalsService

RECENT_DOCUMENTS = 5
UPCOMING_DAYS = 30
SHOWN = 5


class DashboardService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _documents(self, user_id: uuid.UUID) -> dict:
        documents = list(
            self.session.scalars(
                select(Document)
                .where(Document.user_id == user_id, Document.deleted_at.is_(None))
                .order_by(Document.created_at.desc())
            )
        )
        recent, reading, failed = [], 0, []
        for index, document in enumerate(documents):
            job = jobs.latest_job(self.session, document.id)
            status = job.status if job else None
            if status in ACTIVE_JOB_STATUSES:
                reading += 1
            elif status == "failed":
                failed.append(document)
            if index < RECENT_DOCUMENTS:
                recent.append({"document": document, "status": status, "kind": job.document_kind if job else None})
        return {"total": len(documents), "recent": recent, "reading": reading, "failed": failed}

    def _follow_ups(self, user_id: uuid.UUID) -> dict:
        today = datetime.now(UTC).date()
        scheduled = list(
            self.session.scalars(
                select(FollowUp)
                .where(FollowUp.user_id == user_id, FollowUp.status == "scheduled")
                .order_by(FollowUp.due_date, FollowUp.created_at)
            )
        )
        overdue = [f for f in scheduled if f.due_date < today]
        upcoming = [f for f in scheduled if today <= f.due_date <= today + timedelta(days=UPCOMING_DAYS)]
        return {"overdue": overdue, "upcoming": upcoming}

    def _alerts(self, user_id: uuid.UUID) -> dict:
        service = AlertService(self.session)
        service.try_sync(user_id)  # the same rules the Alerts page applies
        self.session.commit()
        live = list(
            self.session.scalars(
                select(Alert)
                .where(Alert.user_id == user_id, Alert.status.in_(("open", "acknowledged")))
                .order_by(Alert.created_at.desc())
            )
        )
        opened = [a for a in live if a.status == "open"]
        urgent = [a for a in opened if a.severity == "urgent"]
        shown = (urgent + [a for a in opened if a.severity != "urgent"])[:3]
        return {
            "open": len(opened),
            "acknowledged": len(live) - len(opened),
            "urgent": len(urgent),
            "shown": [
                (a, self.session.get(Document, a.source_document_id) if a.source_document_id else None) for a in shown
            ],
        }

    def _review(self, user_id: uuid.UUID, failed: list[Document]) -> dict:
        unconfirmed = self.session.scalar(
            select(func.count())
            .select_from(Medication)
            .join(Document, Document.id == Medication.source_document_id)
            .where(
                Medication.user_id == user_id,
                Medication.deleted_at.is_(None),
                Medication.status == "unknown",
                Document.deleted_at.is_(None),
            )
        )
        rows = self.session.execute(
            select(Suggestion, Document)
            .join(Document, Document.id == Suggestion.source_document_id)
            .where(Suggestion.user_id == user_id, Suggestion.status == "pending", Document.deleted_at.is_(None))
        )
        to_add: dict[uuid.UUID, tuple[Document, int]] = {}
        for suggestion, document in rows:
            if addable(suggestion):
                _, count = to_add.get(document.id, (document, 0))
                to_add[document.id] = (document, count + 1)
        return {
            "profile_suggestions": len(ProfileService(self.session).suggestions(user_id)),
            "unconfirmed_medicines": unconfirmed or 0,
            "follow_ups_to_add": list(to_add.values()),
            "failed_documents": failed,
        }

    def _profile(self, user_id: uuid.UUID) -> dict:
        data = ProfileService(self.session).profile(user_id)
        filled = [field for field in SINGLE_FIELDS if data["values"].get(field)]
        return {
            "filled": len(filled),
            "total": len(SINGLE_FIELDS),
            "missing": [field for field in SINGLE_FIELDS if field not in filled],
            "allergies": [a.value for a in data["allergies"]],
            "conditions": len(data["conditions"]),
            "active_medications": len(data["active_medications"]),
            "bmi": data["bmi"],
            "bmi_category": data["bmi_category"],
            "latest_vitals": VitalsService(self.session).latest(user_id),
        }

    def overview(self, user_id: uuid.UUID) -> dict:
        documents = self._documents(user_id)
        return {
            "documents": documents,
            "follow_ups": self._follow_ups(user_id),
            "alerts": self._alerts(user_id),
            "review": self._review(user_id, documents["failed"]),
            "profile": self._profile(user_id),
            # What already happened: dated entries up to today (upcoming follow-ups have their own card).
            "recent_activity": [
                entry
                for entry in TimelineService(self.session).entries(user_id)
                if entry.date is not None and entry.date <= datetime.now(UTC).date()
            ][:SHOWN],
        }
