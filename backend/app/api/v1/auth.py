"""Authentication endpoints (api_contract_spec.md Section 5.1.1)."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, Header, Response, status

from app.api.deps import CurrentUser, DbDep, EmailSenderDep, SettingsDep
from app.core.config import Settings
from app.core.errors import ApiError
from app.core.rate_limit import rate_limit
from app.schemas.auth import (
    ChangePasswordRequest,
    DeleteAccountRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
)
from app.services.account_service import AccountService
from app.services.auth_service import AuthResult, AuthService, send_password_reset_email
from app.services.storage import get_document_storage

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"
CSRF_HEADER = "X-CSRF-Protection"
FORGOT_PASSWORD_MESSAGE = "If an account exists for that email, a password reset link has been sent."  # noqa: S105

RefreshCookie = Annotated[str | None, Cookie(alias=REFRESH_COOKIE)]


# ---------- helpers ----------


def _token_response(result: AuthResult, response: Response, settings: Settings) -> TokenResponse:
    response.set_cookie(
        REFRESH_COOKIE,
        result.refresh_token,
        max_age=settings.refresh_token_days * 24 * 60 * 60,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
    return TokenResponse(
        access_token=result.access.token,
        expires_in=result.access.expires_in,
        user=UserResponse.model_validate(result.user),
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        REFRESH_COOKIE, path=REFRESH_COOKIE_PATH, httponly=True, secure=settings.cookie_secure, samesite="strict"
    )


def require_csrf_protection(
    settings: SettingsDep,
    csrf: Annotated[str | None, Header(alias=CSRF_HEADER)] = None,
    origin: Annotated[str | None, Header()] = None,
) -> None:
    """Cookie-authenticated endpoints need a custom header (forces a CORS preflight) and an allowed Origin."""
    if csrf != "1" or (origin is not None and origin not in settings.cors_origins):
        raise ApiError(403, "CSRF_CHECK_FAILED", "The request could not be verified.")


CsrfCheck = Depends(require_csrf_protection)


# ---------- endpoints ----------


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("register", 5, 60))],
)
def register(body: RegisterRequest, response: Response, session: DbDep, settings: SettingsDep) -> TokenResponse:
    result = AuthService(session, settings).register(body)
    return _token_response(result, response, settings)


@router.post("/login", dependencies=[Depends(rate_limit("login", 10, 60))])
def login(body: LoginRequest, response: Response, session: DbDep, settings: SettingsDep) -> TokenResponse:
    result = AuthService(session, settings).login(body.email, body.password)
    return _token_response(result, response, settings)


@router.post("/refresh", dependencies=[Depends(rate_limit("refresh", 30, 60)), CsrfCheck])
def refresh(
    response: Response, session: DbDep, settings: SettingsDep, refresh_token: RefreshCookie = None
) -> TokenResponse:
    result = AuthService(session, settings).refresh(refresh_token)
    return _token_response(result, response, settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[CsrfCheck])
def logout(response: Response, session: DbDep, settings: SettingsDep, refresh_token: RefreshCookie = None) -> None:
    AuthService(session, settings).logout(refresh_token)
    _clear_refresh_cookie(response, settings)


@router.post(
    "/password/forgot",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("forgot", 5, 3600))],
)
def forgot_password(
    body: ForgotPasswordRequest,
    background: BackgroundTasks,
    session: DbDep,
    settings: SettingsDep,
    sender: EmailSenderDep,
) -> MessageResponse:
    issued = AuthService(session, settings).request_password_reset(body.email)
    if issued is not None:
        # Sent after the response, so timing does not reveal whether the account exists.
        background.add_task(send_password_reset_email, *issued, settings, sender)
    return MessageResponse(message=FORGOT_PASSWORD_MESSAGE)


@router.post(
    "/password/reset",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit("reset", 10, 3600))],
)
def reset_password(body: ResetPasswordRequest, session: DbDep, settings: SettingsDep) -> None:
    AuthService(session, settings).reset_password(body.token, body.new_password)


# ---------- account settings (under /auth so the refresh cookie is sent) ----------


@router.post(
    "/password/change",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit("password_change", 10, 3600)), CsrfCheck],
)
def change_password(
    body: ChangePasswordRequest,
    user: CurrentUser,
    session: DbDep,
    settings: SettingsDep,
    refresh_token: RefreshCookie = None,
) -> None:
    """Other devices are signed out; this one stays signed in."""
    AccountService(session, settings).change_password(user, body.current_password, body.new_password, refresh_token)


@router.post(
    "/account/delete",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit("account_delete", 10, 3600)), CsrfCheck],
)
def delete_account(
    body: DeleteAccountRequest, user: CurrentUser, response: Response, session: DbDep, settings: SettingsDep
) -> None:
    """Permanently deletes the account, its files, and its records, then signs out."""
    AccountService(session, settings).delete_account(
        user, body.password, body.confirmation, get_document_storage(settings)
    )
    _clear_refresh_cookie(response, settings)
