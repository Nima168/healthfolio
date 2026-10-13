"""Account settings: change password, and delete the account with all its data (backend_spec.md Section 5.5).

Deletion is immediate and permanent for live data: every stored file, then every row the user owns. Audit
events stay for their retention period, detached from the user and without personal or medical content.
Database backups are not touched; they expire on their own schedule (30 days).
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.core.security import hash_opaque_token, hash_password, password_policy_problem, verify_password
from app.models.alerts import Alert, AlertEvent
from app.models.auth import AuditEvent, EmailDelivery, PasswordResetToken, RefreshToken, User
from app.models.document import Document
from app.models.extraction import Observation, ProcessingJob
from app.models.prescription import Condition, FollowUp, Medication, MedicationHistory, Suggestion
from app.models.profile import MedicalRecordItem, ProfileValue, ProfileValueHistory, VitalReading
from app.models.summary import AiSummary
from app.repositories.auth import AuditRepository
from app.services.storage import DocumentStorage, StorageError

logger = logging.getLogger(__name__)

DELETE_CONFIRMATION = "DELETE"

# Children before parents, so no foreign key is ever left pointing at a deleted row.
_OWNED = (
    AiSummary,
    ProfileValueHistory,
    ProfileValue,
    FollowUp,
    MedicationHistory,
    Medication,
    Observation,
    Condition,
    Suggestion,
    ProcessingJob,
    MedicalRecordItem,
    VitalReading,
    Document,
    RefreshToken,
    PasswordResetToken,
    EmailDelivery,
)


def _wrong_password() -> ApiError:
    return ApiError(422, details=[{"field": "current_password", "issue": "This password is not correct."}])


class AccountService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.audit = AuditRepository(session)

    def change_password(self, user: User, current: str, new: str, refresh_token: str | None) -> None:
        """Other devices are signed out; this one stays signed in."""
        if not verify_password(current, user.password_hash):
            self.audit.record("auth.password_change", "failure", user.id, {"reason": "wrong_password"})
            self.session.commit()
            raise _wrong_password()
        problem = password_policy_problem(new, user.email)
        if problem:
            raise ApiError(422, details=[{"field": "new_password", "issue": problem}])
        if verify_password(new, user.password_hash):
            raise ApiError(
                422, details=[{"field": "new_password", "issue": "Choose a password you are not using now."}]
            )

        user.password_hash = hash_password(new)
        now = datetime.now(UTC)
        keep = None
        if refresh_token:
            keep = self.session.scalar(
                select(RefreshToken.family_id).where(
                    RefreshToken.token_hash == hash_opaque_token(refresh_token), RefreshToken.user_id == user.id
                )
            )
        others = update(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        if keep is not None:
            others = others.where(RefreshToken.family_id != keep)
        self.session.execute(others.values(revoked_at=now))
        self.audit.record("auth.password_changed", "success", user.id)
        self.session.commit()

    def delete_account(self, user: User, password: str, confirmation: str, storage: DocumentStorage) -> None:
        if confirmation.strip() != DELETE_CONFIRMATION:
            raise ApiError(422, details=[{"field": "confirmation", "issue": "Type DELETE to confirm."}])
        if not verify_password(password, user.password_hash):
            self.audit.record("account.delete", "failure", user.id, {"reason": "wrong_password"})
            self.session.commit()
            raise _wrong_password()

        user_id = user.id
        # Files first: if one cannot be removed, nothing else changes and the user can try again.
        keys = self.session.scalars(
            select(Document.storage_key).where(Document.user_id == user_id, Document.storage_key.is_not(None))
        ).all()
        try:
            for key in keys:
                storage.delete(key)
        except StorageError as exc:
            logger.error("account deletion stopped: a file could not be removed")
            raise ApiError(503, message="Your account could not be deleted right now. Please try again.") from exc

        alerts = select(Alert.id).where(Alert.user_id == user_id)
        self.session.execute(delete(AlertEvent).where(AlertEvent.alert_id.in_(alerts)))
        self.session.execute(delete(Alert).where(Alert.user_id == user_id))
        # Conditions point at each other (accepted suggestion -> profile condition): unlink first.
        self.session.execute(update(Condition).where(Condition.user_id == user_id).values(profile_condition_id=None))
        for model in _OWNED:
            self.session.execute(delete(model).where(model.user_id == user_id))
        # Audit history stays for its retention period, no longer linked to anyone.
        self.session.execute(update(AuditEvent).where(AuditEvent.user_id == user_id).values(user_id=None))
        self.session.execute(delete(User).where(User.id == user_id))
        self.audit.record("account.deleted", "success", None, {"files_removed": len(keys)})
        self.session.commit()
        logger.info("account deleted", extra={"files_removed": len(keys)})


def owned_models() -> tuple[type, ...]:
    """Every table holding a user's data (used by tests to prove nothing is left behind)."""
    return (*_OWNED, Alert)
