from fastapi import APIRouter

from app.api.deps import CurrentUser, DbDep
from app.schemas.diagnoses import HealthIssueList, HealthIssueResponse, MentionResponse
from app.services.diagnosis_service import DiagnosisService

router = APIRouter(prefix="/diagnoses", tags=["diagnoses"])


@router.get("")
def list_health_issues(user: CurrentUser, session: DbDep) -> HealthIssueList:
    """Diagnoses, assessments, and impressions written in the user's documents, grouped by wording."""
    return HealthIssueList(
        items=[
            HealthIssueResponse(
                name=issue.name,
                kinds=issue.kinds,
                first_seen=issue.first_seen,
                last_seen=issue.last_seen,
                profile=issue.profile,
                condition_status=issue.condition_status,
                normal=issue.normal,
                mentions=[MentionResponse(**vars(mention)) for mention in issue.mentions],
            )
            for issue in DiagnosisService(session).issues(user.id)
        ]
    )
