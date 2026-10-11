"""Password hashing, access tokens (JWT), and opaque random tokens.

No custom cryptography: Argon2id via argon2-cffi, HS256 JWTs via PyJWT,
and secrets.token_urlsafe for refresh/reset tokens (stored only as SHA-256 hashes).
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import Settings

_password_hasher = PasswordHasher()  # Argon2id with library-recommended parameters

# Verified against when the email is unknown, so failed logins take similar time either way.
_DUMMY_HASH = _password_hasher.hash("dummy-password-for-timing-equalisation")

ACCESS_TOKEN_TYPE = "access"  # noqa: S105  (claim value, not a secret)
JWT_ALGORITHM = "HS256"
JWT_AUDIENCE = "healthcare-api"

PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 128


# ---------- Passwords ----------


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def burn_password_check(password: str) -> None:
    """Spend the same effort as a real verification (unknown-account path)."""
    verify_password(password, _DUMMY_HASH)


def password_policy_problem(password: str, email: str) -> str | None:
    """Return a user-safe reason the password is not allowed, or None if it is acceptable."""
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"Password must be at least {PASSWORD_MIN_LENGTH} characters."
    if len(password) > PASSWORD_MAX_LENGTH:
        return f"Password must be at most {PASSWORD_MAX_LENGTH} characters."
    if password.strip().lower() == email.strip().lower():
        return "Password must not be the same as your email address."
    return None


# ---------- Access tokens (JWT) ----------


@dataclass(frozen=True)
class AccessToken:
    token: str
    expires_in: int  # seconds


class InvalidTokenError(Exception):
    """Raised for any invalid, expired, or wrong-type access token."""


def create_access_token(user_id: uuid.UUID, settings: Settings) -> AccessToken:
    now = datetime.now(UTC)
    lifetime = timedelta(minutes=settings.access_token_minutes)
    payload = {
        "sub": str(user_id),
        "type": ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": now + lifetime,
        "jti": uuid.uuid4().hex,
        "iss": settings.jwt_issuer,
        "aud": JWT_AUDIENCE,
    }
    token = jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=JWT_ALGORITHM)
    return AccessToken(token=token, expires_in=int(lifetime.total_seconds()))


def decode_access_token(token: str, settings: Settings) -> uuid.UUID:
    """Return the user ID from a valid access token, or raise InvalidTokenError."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[JWT_ALGORITHM],  # fixed list: never trust the token's own "alg"
            audience=JWT_AUDIENCE,
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "type", "iss", "aud"]},
        )
        if payload.get("type") != ACCESS_TOKEN_TYPE:
            raise InvalidTokenError
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise InvalidTokenError from exc


# ---------- Opaque tokens (refresh, password reset) ----------


def new_opaque_token() -> str:
    """256 bits of randomness, URL-safe."""
    return secrets.token_urlsafe(32)


def hash_opaque_token(token: str) -> str:
    """SHA-256 is appropriate here: the token is already high-entropy random data."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
