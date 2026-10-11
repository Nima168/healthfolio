"""Authentication business rules (api_contract_spec.md Section 5.1.2).

Each public method is one transaction: it commits on success, and also commits
security bookkeeping (failed-login counters, audit events) before raising.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.core.security import (
    AccessToken,
    burn_password_check,
    create_access_token,
    hash_opaque_token,
    hash_password,
    new_opaque_token,
    password_policy_problem,
    verify_password,
)
from app.db.session import get_session_factory
from app.models.auth import EmailDelivery, PasswordResetToken, RefreshToken, User
from app.repositories.auth import (
    AuditRepository,
    EmailDeliveryRepository,
    PasswordResetTokenRepository,
    RefreshTokenRepository,
    UserRepository,
)
from app.schemas.auth import RegisterRequest
from app.services.email import EmailSender, EmailSendError

logger = logging.getLogger(__name__)

# Two tabs refreshing at the same moment both present the same cookie. A token that was
# rotated within this window is rejected without treating it as theft.
ROTATION_GRACE = timedelta(seconds=10)


def _invalid_credentials() -> ApiError:
    # One message for every login failure, so responses never reveal whether an account exists.
    return ApiError(401, "INVALID_CREDENTIALS", "Email or password is incorrect, or the account is temporarily locked.")


def _unauthenticated() -> ApiError:
    return ApiError(401, "UNAUTHENTICATED", "Your session has ended. Please log in again.")


@dataclass(frozen=True)
class AuthResult:
    """Result of a successful login/register/refresh."""

    user: User
    access: AccessToken
    refresh_token: str  # raw value: goes only into the HttpOnly cookie


def _now() -> datetime:
    return datetime.now(UTC)


class AuthService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.users = UserRepository(session)
        self.refresh_tokens = RefreshTokenRepository(session)
        self.reset_tokens = PasswordResetTokenRepository(session)
        self.audit = AuditRepository(session)

    # ---------- registration and login ----------

    def register(self, request: RegisterRequest) -> AuthResult:
        if self.users.get_by_email(request.email):
            raise ApiError(409, "EMAIL_ALREADY_REGISTERED", "An account with this email already exists.")

        user = User(
            email=request.email,
            password_hash=hash_password(request.password),
            display_name=request.display_name,
            last_login_at=_now(),
        )
        try:
            self.users.add(user)
        except IntegrityError as exc:  # two registrations for the same email at once
            self.session.rollback()
            raise ApiError(409, "EMAIL_ALREADY_REGISTERED", "An account with this email already exists.") from exc

        result = self._start_session(user, family_id=uuid.uuid4())
        self.audit.record("auth.register", "success", user.id)
        self.session.commit()
        return result

    def login(self, email: str, password: str) -> AuthResult:
        user = self.users.get_by_email(email)
        now = _now()

        if user is None or user.status != "active":
            burn_password_check(password)
            self.audit.record("auth.login", "failure", metadata={"reason": "unknown_account"})
            self.session.commit()
            raise _invalid_credentials()

        if user.locked_until and user.locked_until > now:
            burn_password_check(password)
            self.audit.record("auth.login", "failure", user.id, {"reason": "locked"})
            self.session.commit()
            raise _invalid_credentials()

        if not verify_password(password, user.password_hash):
            user.failed_login_count += 1
            self.audit.record("auth.login", "failure", user.id, {"reason": "bad_password"})
            if user.failed_login_count >= self.settings.login_max_failures:
                user.locked_until = now + timedelta(minutes=self.settings.lockout_minutes)
                user.failed_login_count = 0
                self.audit.record("auth.lockout", "success", user.id)
            self.session.commit()
            raise _invalid_credentials()

        user.failed_login_count = 0
        user.locked_until = None
        user.last_login_at = now
        result = self._start_session(user, family_id=uuid.uuid4())
        self.audit.record("auth.login", "success", user.id)
        self.session.commit()
        return result

    # ---------- refresh and logout ----------

    def refresh(self, raw_token: str | None) -> AuthResult:
        if not raw_token:
            raise _unauthenticated()

        now = _now()
        token = self.refresh_tokens.get_by_hash(hash_opaque_token(raw_token), for_update=True)
        if token is None:
            raise _unauthenticated()

        if token.revoked_at is not None:
            recently_rotated = token.replaced_by_id is not None and now - token.revoked_at < ROTATION_GRACE
            if not recently_rotated:
                # A revoked token being used again suggests it was stolen: end that whole login.
                self.refresh_tokens.revoke_family(token.family_id, now)
                self.audit.record("auth.refresh_reuse", "failure", token.user_id)
                self.session.commit()
            raise _unauthenticated()

        if token.expires_at <= now:
            raise _unauthenticated()

        user = self.users.get(token.user_id)
        if user is None or user.status != "active" or user.deleted_at is not None:
            raise _unauthenticated()

        result = self._start_session(user, family_id=token.family_id, replacing=token)
        self.session.commit()
        return result

    def logout(self, raw_token: str | None) -> None:
        if not raw_token:
            return
        token = self.refresh_tokens.get_by_hash(hash_opaque_token(raw_token))
        if token is None:
            return
        self.refresh_tokens.revoke_family(token.family_id, _now())
        self.audit.record("auth.logout", "success", token.user_id)
        self.session.commit()

    # ---------- password reset ----------

    def request_password_reset(self, email: str) -> tuple[uuid.UUID, str, str] | None:
        """Create a reset token. Returns (user_id, email, raw_token) for the caller to email, or None."""
        user = self.users.get_by_email(email)
        if user is None or user.status != "active":
            return None

        now = _now()
        self.reset_tokens.invalidate_unused_for_user(user.id, now)
        raw_token = new_opaque_token()
        self.reset_tokens.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_opaque_token(raw_token),
                expires_at=now + timedelta(minutes=self.settings.password_reset_minutes),
            )
        )
        self.audit.record("auth.password_reset_requested", "success", user.id)
        self.session.commit()
        return user.id, user.email, raw_token

    def reset_password(self, raw_token: str, new_password: str) -> None:
        now = _now()
        token = self.reset_tokens.get_by_hash(hash_opaque_token(raw_token))
        if token is None or token.used_at is not None or token.expires_at <= now:
            raise ApiError(400, "INVALID_OR_EXPIRED_TOKEN", "This reset link is invalid or has expired.")

        user = self.users.get(token.user_id)
        if user is None or user.status != "active":
            raise ApiError(400, "INVALID_OR_EXPIRED_TOKEN", "This reset link is invalid or has expired.")

        problem = password_policy_problem(new_password, user.email)
        if problem:
            raise ApiError(422, details=[{"field": "new_password", "issue": problem}])

        user.password_hash = hash_password(new_password)
        user.failed_login_count = 0
        user.locked_until = None
        token.used_at = now
        self.reset_tokens.invalidate_unused_for_user(user.id, now)
        self.refresh_tokens.revoke_all_for_user(user.id, now)
        self.audit.record("auth.password_reset_completed", "success", user.id)
        self.session.commit()

    # ---------- helpers ----------

    def _start_session(self, user: User, family_id: uuid.UUID, replacing: RefreshToken | None = None) -> AuthResult:
        now = _now()
        raw_token = new_opaque_token()
        new_token = self.refresh_tokens.add(
            RefreshToken(
                user_id=user.id,
                family_id=family_id,
                token_hash=hash_opaque_token(raw_token),
                expires_at=now + timedelta(days=self.settings.refresh_token_days),
            )
        )
        if replacing is not None:
            replacing.revoked_at = now
            replacing.replaced_by_id = new_token.id
        return AuthResult(user=user, access=create_access_token(user.id, self.settings), refresh_token=raw_token)


def send_password_reset_email(
    user_id: uuid.UUID, email: str, raw_token: str, settings: Settings, sender: EmailSender
) -> None:
    """Runs after the response is sent (BackgroundTasks), with its own database session."""
    link = f"{settings.frontend_base_url.rstrip('/')}/reset-password#token={raw_token}"
    body = (
        "We received a request to reset the password for your Health Records account.\n\n"
        f"Reset your password using this link (valid for {settings.password_reset_minutes} minutes):\n"
        f"{link}\n\n"
        "If you did not ask for this, you can ignore this email; your password will not change.\n"
    )
    session = get_session_factory()()
    try:
        delivery = EmailDeliveryRepository(session).add(
            EmailDelivery(user_id=user_id, template="password_reset", provider=sender.provider, attempts=1)
        )
        try:
            delivery.provider_message_id = sender.send(email, "Reset your Health Records password", body)
            delivery.status = "sent"
        except EmailSendError as exc:
            delivery.status = "failed"
            delivery.error_category = str(exc)
            logger.warning("password reset email failed", extra={"error_category": str(exc)})
        session.commit()
    finally:
        session.close()
