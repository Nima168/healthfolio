import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import get_settings
from app.core.rate_limit import RateLimiter
from app.core.security import (
    JWT_ALGORITHM,
    JWT_AUDIENCE,
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_opaque_token,
    hash_password,
    new_opaque_token,
    password_policy_problem,
    verify_password,
)


@pytest.fixture
def settings():
    get_settings.cache_clear()
    return get_settings()


def test_password_hash_is_argon2id_and_verifies():
    hashed = hash_password("correct horse battery")

    assert hashed.startswith("$argon2id$")
    assert "correct horse battery" not in hashed
    assert verify_password("correct horse battery", hashed)
    assert not verify_password("wrong password here", hashed)


def test_verify_password_handles_garbage_hash():
    assert verify_password("anything", "not-a-real-hash") is False


@pytest.mark.parametrize(
    ("password", "expected"),
    [
        ("short", "at least 12"),
        ("x" * 129, "at most 128"),
        ("asha@example.com", "same as your email"),
        ("a perfectly fine passphrase", None),
    ],
)
def test_password_policy(password, expected):
    problem = password_policy_problem(password, "asha@example.com")
    if expected is None:
        assert problem is None
    else:
        assert expected in problem


def test_access_token_round_trip(settings):
    user_id = uuid.uuid4()
    token = create_access_token(user_id, settings)

    assert token.expires_in == settings.access_token_minutes * 60
    assert decode_access_token(token.token, settings) == user_id


def _encode(settings, **overrides):
    now = datetime.now(UTC)
    payload = {
        "sub": str(uuid.uuid4()),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "iss": settings.jwt_issuer,
        "aud": JWT_AUDIENCE,
    } | overrides
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=JWT_ALGORITHM)


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": datetime.now(UTC) - timedelta(seconds=1)},  # expired
        {"type": "refresh"},  # wrong token type
        {"aud": "someone-else"},  # wrong audience
        {"iss": "someone-else"},  # wrong issuer
    ],
)
def test_rejects_invalid_claims(settings, overrides):
    with pytest.raises(InvalidTokenError):
        decode_access_token(_encode(settings, **overrides), settings)


def test_rejects_tampered_and_foreign_tokens(settings):
    token = create_access_token(uuid.uuid4(), settings).token
    tampered = token[:-2] + ("AA" if token[-2:] != "AA" else "BB")
    forged = jwt.encode({"sub": str(uuid.uuid4()), "type": "access"}, "other-secret-" + "z" * 30, algorithm="HS256")
    unsigned = jwt.encode({"sub": str(uuid.uuid4()), "type": "access"}, None, algorithm="none")

    for bad in (tampered, forged, unsigned, "not-a-jwt"):
        with pytest.raises(InvalidTokenError):
            decode_access_token(bad, settings)


def test_opaque_tokens_are_random_and_hash_is_stable():
    first, second = new_opaque_token(), new_opaque_token()

    assert first != second and len(first) >= 43
    assert hash_opaque_token(first) == hash_opaque_token(first)
    assert hash_opaque_token(first) != first


def test_rate_limiter_sliding_window():
    now = [0.0]
    limiter = RateLimiter(clock=lambda: now[0])

    assert all(limiter.allow("k", 3, 60) for _ in range(3))
    assert limiter.allow("k", 3, 60) is False
    assert limiter.allow("other", 3, 60) is True  # keys are independent
    now[0] = 61.0
    assert limiter.allow("k", 3, 60) is True
