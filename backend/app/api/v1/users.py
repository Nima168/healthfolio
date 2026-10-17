from fastapi import APIRouter

from app.api.deps import CurrentUser, DbDep
from app.repositories.auth import AuditRepository
from app.schemas.auth import UserResponse, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
def read_me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)


@router.patch("/me")
def update_me(body: UserUpdate, user: CurrentUser, session: DbDep) -> UserResponse:
    """The user's name, shown in the app and in Health Profile; null or blank removes it."""
    user.display_name = body.display_name
    AuditRepository(session).record("user.updated", "success", user.id, {"fields": ["display_name"]})
    session.commit()
    return UserResponse.model_validate(user)
