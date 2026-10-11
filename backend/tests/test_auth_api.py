"""Authentication API against the real PostgreSQL test database (api_contract_spec.md Section 5.1)."""

from datetime import UTC, datetime, timedelta
from email import message_from_bytes, policy
from urllib.parse import urlsplit

import pytest
from sqlalchemy import select, update

from app.models.auth import AuditEvent, EmailDelivery, PasswordResetToken, RefreshToken, User

pytestmark = pytest.mark.integration

EMAIL = "asha@example.com"
PASSWORD = "a long enough passphrase"
NEW_PASSWORD = "another long passphrase"
CSRF = {"X-CSRF-Protection": "1", "Origin": "http://localhost:5173"}


# ---------- helpers ----------


def register(client, email=EMAIL, password=PASSWORD, **extra):
    return client.post("/api/v1/auth/register", json={"email": email, "password": password, **extra})


def login(client, email=EMAIL, password=PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def refresh(client, headers=CSRF):
    return client.post("/api/v1/auth/refresh", headers=headers)


def refresh_with_cookie(client, refresh_token):
    """Replay a specific refresh token, ignoring whatever the client's cookie jar holds."""
    client.cookies.clear()
    return client.post("/api/v1/auth/refresh", headers={**CSRF, "Cookie": f"refresh_token={refresh_token}"})


def me(client, access_token):
    return client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {access_token}"})


def reset_token_from_mail(mail_dir):
    messages = list(mail_dir.glob("*.eml"))
    assert len(messages) == 1, f"expected one email, found {len(messages)}"
    # Parse properly: the body may be quoted-printable encoded ("=" becomes "=3D", long lines wrap).
    body = message_from_bytes(messages[0].read_bytes(), policy=policy.default).get_content()
    link = next(word for word in body.split() if "/reset-password#token=" in word)
    return urlsplit(link).fragment.removeprefix("token=")


def error_code(response):
    return response.json()["error"]["code"]


# ---------- registration ----------


def test_register_logs_user_in_and_sets_secure_cookie(client, db):
    response = register(client, display_name="  Asha  ")

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == 900
    assert body["user"]["email"] == EMAIL and body["user"]["display_name"] == "Asha"
    assert "password" not in response.text

    cookie = response.headers["set-cookie"].lower()
    for attribute in ("refresh_token=", "httponly", "secure", "samesite=strict", "path=/api/v1/auth"):
        assert attribute in cookie
    assert response.headers["cache-control"] == "no-store"

    assert me(client, body["access_token"]).json()["email"] == EMAIL


def test_register_normalises_email_and_rejects_duplicates(client, db):
    assert register(client, email="  Asha@Example.COM ").status_code == 201

    duplicate = register(client, email="asha@example.com")
    assert duplicate.status_code == 409
    assert error_code(duplicate) == "EMAIL_ALREADY_REGISTERED"


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"email": "not-an-email", "password": PASSWORD}, "email"),
        ({"email": EMAIL, "password": "short"}, "password"),
        ({"email": EMAIL, "password": EMAIL}, "password"),
    ],
)
def test_register_validation_errors(client, db, payload, field):
    response = client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == field
    assert payload["password"] not in response.text  # submitted values are never echoed


def test_password_is_stored_hashed(client, db):
    register(client)

    user = db.scalar(select(User).where(User.email == EMAIL))
    assert user.password_hash.startswith("$argon2id$")
    assert PASSWORD not in user.password_hash


# ---------- login and lockout ----------


def test_login_success_returns_tokens(client, db):
    register(client)

    response = login(client)
    assert response.status_code == 200
    assert me(client, response.json()["access_token"]).status_code == 200


def test_wrong_password_and_unknown_email_look_identical(client, db):
    register(client)

    wrong_password = login(client, password="wrong password value")
    unknown_email = login(client, email="nobody@example.com")

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json()["error"]["code"] == unknown_email.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert wrong_password.json()["error"]["message"] == unknown_email.json()["error"]["message"]


def test_lockout_after_five_failures_blocks_even_correct_password(client, db):
    register(client)
    for _ in range(5):
        assert login(client, password="wrong password value").status_code == 401

    locked = login(client)
    assert locked.status_code == 401
    assert error_code(locked) == "INVALID_CREDENTIALS"
    assert db.scalar(select(AuditEvent).where(AuditEvent.event_type == "auth.lockout")) is not None


def test_lockout_expires(client, db):
    register(client)
    for _ in range(5):
        login(client, password="wrong password value")

    db.execute(update(User).values(locked_until=datetime.now(UTC) - timedelta(seconds=1)))
    db.commit()

    assert login(client).status_code == 200


def test_login_rate_limit(client, db):
    for _ in range(10):
        login(client, email="nobody@example.com")

    limited = login(client, email="nobody@example.com")
    assert limited.status_code == 429
    assert error_code(limited) == "RATE_LIMITED"


# ---------- access tokens ----------


def test_me_requires_valid_bearer_token(client, db):
    missing = client.get("/api/v1/users/me")
    garbage = me(client, "not.a.token")

    for response in (missing, garbage):
        assert response.status_code == 401
        assert error_code(response) == "UNAUTHENTICATED"
        assert response.headers["www-authenticate"] == "Bearer"


# ---------- refresh rotation ----------


def test_refresh_rotates_cookie_and_returns_new_access_token(client, db):
    register(client)
    old_cookie = client.cookies.get("refresh_token")

    response = refresh(client)
    assert response.status_code == 200
    assert client.cookies.get("refresh_token") != old_cookie
    assert me(client, response.json()["access_token"]).status_code == 200

    tokens = db.scalars(select(RefreshToken)).all()
    assert len(tokens) == 2
    assert sum(token.revoked_at is None for token in tokens) == 1


def test_refresh_requires_csrf_header_and_allowed_origin(client, db):
    register(client)

    no_header = refresh(client, headers={})
    bad_origin = refresh(client, headers={"X-CSRF-Protection": "1", "Origin": "https://evil.example"})

    for response in (no_header, bad_origin):
        assert response.status_code == 403
        assert error_code(response) == "CSRF_CHECK_FAILED"


def test_refresh_without_cookie_is_unauthenticated(client, db):
    response = refresh(client)

    assert response.status_code == 401
    assert error_code(response) == "UNAUTHENTICATED"


def test_reused_refresh_token_revokes_the_whole_login(client, db):
    register(client)
    stolen = client.cookies.get("refresh_token")
    assert refresh(client).status_code == 200  # legitimate rotation

    # Simulate the attacker replaying the old token after the grace window.
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.revoked_at.is_not(None))
        .values(revoked_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    db.commit()
    assert refresh_with_cookie(client, stolen).status_code == 401

    db.expire_all()
    assert all(token.revoked_at is not None for token in db.scalars(select(RefreshToken)))
    assert db.scalar(select(AuditEvent).where(AuditEvent.event_type == "auth.refresh_reuse")) is not None


def test_concurrent_refresh_within_grace_window_does_not_end_the_login(client, db):
    """Two tabs refreshing at once: the slower one is rejected, but the session survives."""
    register(client)
    original = client.cookies.get("refresh_token")
    assert refresh(client).status_code == 200
    newest = client.cookies.get("refresh_token")

    assert refresh_with_cookie(client, original).status_code == 401  # just rotated: not treated as theft
    assert refresh_with_cookie(client, newest).status_code == 200
    assert db.scalar(select(AuditEvent).where(AuditEvent.event_type == "auth.refresh_reuse")) is None


def test_expired_refresh_token_is_rejected(client, db):
    register(client)
    db.execute(update(RefreshToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    db.commit()

    assert refresh(client).status_code == 401


# ---------- logout ----------


def test_logout_revokes_session_and_clears_cookie(client, db):
    register(client)
    cookie = client.cookies.get("refresh_token")

    response = client.post("/api/v1/auth/logout", headers=CSRF)
    assert response.status_code == 204
    assert 'refresh_token=""' in response.headers["set-cookie"] or "max-age=0" in response.headers["set-cookie"].lower()

    assert refresh_with_cookie(client, cookie).status_code == 401


# ---------- password reset ----------


def test_forgot_password_is_identical_for_known_and_unknown_emails(client, db, mail_dir):
    register(client)

    known = client.post("/api/v1/auth/password/forgot", json={"email": EMAIL})
    unknown = client.post("/api/v1/auth/password/forgot", json={"email": "nobody@example.com"})

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert len(list(mail_dir.glob("*.eml"))) == 1  # only the real account got an email

    delivery = db.scalar(select(EmailDelivery))
    assert delivery.status == "sent" and delivery.template == "password_reset"


def test_password_reset_flow(client, db, mail_dir):
    register(client)
    client.post("/api/v1/auth/password/forgot", json={"email": EMAIL})
    token = reset_token_from_mail(mail_dir)

    response = client.post("/api/v1/auth/password/reset", json={"token": token, "new_password": NEW_PASSWORD})
    assert response.status_code == 204

    assert login(client, password=PASSWORD).status_code == 401
    assert login(client, password=NEW_PASSWORD).status_code == 200

    reused = client.post("/api/v1/auth/password/reset", json={"token": token, "new_password": "yet another passphrase"})
    assert reused.status_code == 400
    assert error_code(reused) == "INVALID_OR_EXPIRED_TOKEN"


def test_reset_link_can_be_copied_straight_from_the_dev_email_file(client, db, mail_dir):
    """Developers open the .eml file and copy the link, so it must appear intact on one line."""
    register(client)
    client.post("/api/v1/auth/password/forgot", json={"email": EMAIL})
    raw_text = next(mail_dir.glob("*.eml")).read_text(encoding="utf-8")

    link_line = next(line for line in raw_text.splitlines() if "/reset-password#token=" in line)
    copied_token = link_line.strip().split("#token=", 1)[1]
    assert "=3D" not in raw_text and not link_line.endswith("=")

    response = client.post("/api/v1/auth/password/reset", json={"token": copied_token, "new_password": NEW_PASSWORD})
    assert response.status_code == 204
    assert login(client, password=NEW_PASSWORD).status_code == 200


def test_password_reset_revokes_existing_sessions(client, db, mail_dir):
    register(client)
    client.post("/api/v1/auth/password/forgot", json={"email": EMAIL})
    token = reset_token_from_mail(mail_dir)

    client.post("/api/v1/auth/password/reset", json={"token": token, "new_password": NEW_PASSWORD})

    assert refresh(client).status_code == 401


def test_password_reset_clears_lockout(client, db, mail_dir):
    register(client)
    for _ in range(5):
        login(client, password="wrong password value")
    client.post("/api/v1/auth/password/forgot", json={"email": EMAIL})

    client.post(
        "/api/v1/auth/password/reset", json={"token": reset_token_from_mail(mail_dir), "new_password": NEW_PASSWORD}
    )
    assert login(client, password=NEW_PASSWORD).status_code == 200


def test_expired_reset_token_is_rejected(client, db, mail_dir):
    register(client)
    client.post("/api/v1/auth/password/forgot", json={"email": EMAIL})
    token = reset_token_from_mail(mail_dir)
    db.execute(update(PasswordResetToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    db.commit()

    response = client.post("/api/v1/auth/password/reset", json={"token": token, "new_password": NEW_PASSWORD})
    assert response.status_code == 400


def test_new_reset_request_invalidates_older_link(client, db, mail_dir):
    register(client)
    client.post("/api/v1/auth/password/forgot", json={"email": EMAIL})
    first = reset_token_from_mail(mail_dir)
    for message in mail_dir.glob("*.eml"):
        message.unlink()
    client.post("/api/v1/auth/password/forgot", json={"email": EMAIL})

    response = client.post("/api/v1/auth/password/reset", json={"token": first, "new_password": NEW_PASSWORD})
    assert response.status_code == 400


# ---------- audit and logging hygiene ----------


def test_audit_events_recorded_without_secrets(client, db, mail_dir):
    register(client)
    login(client, password="wrong password value")
    login(client)
    client.post("/api/v1/auth/password/forgot", json={"email": EMAIL})

    events = db.scalars(select(AuditEvent).order_by(AuditEvent.occurred_at)).all()
    types = [event.event_type for event in events]
    assert types[:4] == ["auth.register", "auth.login", "auth.login", "auth.password_reset_requested"]
    assert [event.outcome for event in events[:3]] == ["success", "failure", "success"]
    assert all(event.request_id for event in events)

    stored = " ".join(str(event.metadata_json) for event in events)
    for secret in (PASSWORD, "wrong password value", EMAIL):
        assert secret not in stored


def test_logs_never_contain_passwords_tokens_or_emails(client, db, mail_dir, capsys):
    capsys.readouterr()
    register(client)
    access = login(client).json()["access_token"]
    me(client, access)
    refresh(client)
    client.post("/api/v1/auth/password/forgot", json={"email": EMAIL})

    output = capsys.readouterr().out
    assert output, "expected log output"
    for secret in (PASSWORD, access, EMAIL, reset_token_from_mail(mail_dir)):
        assert secret not in output
