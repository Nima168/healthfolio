"""Database access for account and security entities. No business rules here."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.logging import request_id_var
from app.models.auth import AuditEvent, EmailDelivery, PasswordResetToken, RefreshToken, User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, user_id: uuid.UUID) -> User | None:
        return self.session.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        return self.session.scalar(select(User).where(User.email == email, User.deleted_at.is_(None)))

    def add(self, user: User) -> User:
        self.session.add(user)
        self.session.flush()
        return user


class RefreshTokenRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, token: RefreshToken) -> RefreshToken:
        self.session.add(token)
        self.session.flush()
        return token

    def get_by_hash(self, token_hash: str, *, for_update: bool = False) -> RefreshToken | None:
        query = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        if for_update:
            query = query.with_for_update()  # serialises concurrent refreshes of the same token
        return self.session.scalar(query)

    def revoke_family(self, family_id: uuid.UUID, at: datetime) -> None:
        self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=at)
        )

    def revoke_all_for_user(self, user_id: uuid.UUID, at: datetime) -> None:
        self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=at)
        )


class PasswordResetTokenRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, token: PasswordResetToken) -> PasswordResetToken:
        self.session.add(token)
        self.session.flush()
        return token

    def get_by_hash(self, token_hash: str) -> PasswordResetToken | None:
        return self.session.scalar(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash).with_for_update()
        )

    def invalidate_unused_for_user(self, user_id: uuid.UUID, at: datetime) -> None:
        """Older unused links stop working when a new one is issued or a reset completes."""
        self.session.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.user_id == user_id, PasswordResetToken.used_at.is_(None))
            .values(used_at=at)
        )


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record(
        self,
        event_type: str,
        outcome: str,
        user_id: uuid.UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.session.add(
            AuditEvent(
                event_type=event_type,
                outcome=outcome,
                user_id=user_id,
                request_id=request_id_var.get(),
                metadata_json=metadata or {},
            )
        )


class EmailDeliveryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, delivery: EmailDelivery) -> EmailDelivery:
        self.session.add(delivery)
        self.session.flush()
        return delivery
