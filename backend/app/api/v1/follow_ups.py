"""Checkups and follow-ups (api_contract_spec.md Section 6.3)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, DbDep
from app.schemas.follow_ups import FollowUpListResponse, FollowUpResponse, FollowUpUpdate
from app.services.follow_up_service import FollowUpService

router = APIRouter(prefix="/follow-ups", tags=["follow-ups"])


def _service(session: DbDep) -> FollowUpService:
    return FollowUpService(session)


ServiceDep = Annotated[FollowUpService, Depends(_service)]


@router.get("")
def list_follow_ups(user: CurrentUser, service: ServiceDep) -> FollowUpListResponse:
    return service.list(user.id)


@router.patch("/{follow_up_id}")
def update_follow_up(
    follow_up_id: uuid.UUID, body: FollowUpUpdate, user: CurrentUser, service: ServiceDep
) -> FollowUpResponse:
    return service.update(user.id, follow_up_id, body)


@router.delete("/{follow_up_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_follow_up(follow_up_id: uuid.UUID, user: CurrentUser, service: ServiceDep) -> None:
    """Removed permanently; it leaves Follow-ups, the timeline, the dashboard, search, and exports."""
    service.delete(user.id, follow_up_id)
