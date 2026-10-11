"""Shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.security import InvalidTokenError, decode_access_token
from app.db.session import get_db
from app.models.auth import User
from app.repositories.auth import UserRepository
from app.services.email import EmailSender, get_email_sender

_bearer = HTTPBearer(auto_error=False)

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[Session, Depends(get_db)]


def _unauthenticated() -> ApiError:
    return ApiError(401, headers={"WWW-Authenticate": "Bearer"})


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: DbDep,
    settings: SettingsDep,
) -> User:
    """The authenticated user, from a valid Bearer access token. Identity never comes from the client body."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthenticated()
    try:
        user_id = decode_access_token(credentials.credentials, settings)
    except InvalidTokenError:
        raise _unauthenticated() from None

    user = UserRepository(session).get(user_id)
    if user is None or user.status != "active" or user.deleted_at is not None:
        raise _unauthenticated()
    return user


def provide_email_sender(settings: SettingsDep) -> EmailSender:
    return get_email_sender(settings)


CurrentUser = Annotated[User, Depends(get_current_user)]
EmailSenderDep = Annotated[EmailSender, Depends(provide_email_sender)]
