from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.schemas.auth import UserResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
def read_me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)
