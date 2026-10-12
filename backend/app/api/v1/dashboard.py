"""Dashboard overview (api_contract_spec.md Section 6.11)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, DbDep
from app.api.v1.profile import latest_vital
from app.schemas.dashboard import (
    DashboardAlert,
    DashboardDocument,
    DashboardFollowUp,
    DashboardResponse,
    DocumentCount,
)
from app.schemas.timeline import TimelineEntryResponse
from app.services.dashboard_service import SHOWN, DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _service(session: DbDep) -> DashboardService:
    return DashboardService(session)


ServiceDep = Annotated[DashboardService, Depends(_service)]


def _follow_up(follow_up) -> DashboardFollowUp:
    return DashboardFollowUp(
        id=follow_up.id,
        title=follow_up.title,
        due_date=follow_up.due_date,
        source_document_id=follow_up.source_document_id,
    )


@router.get("")
def dashboard(user: CurrentUser, service: ServiceDep) -> DashboardResponse:
    data = service.overview(user.id)
    documents, follow_ups, alerts = data["documents"], data["follow_ups"], data["alerts"]
    review, profile = data["review"], data["profile"]
    return DashboardResponse(
        documents_total=documents["total"],
        documents_reading=documents["reading"],
        recent_documents=[
            DashboardDocument(
                id=item["document"].id,
                title=item["document"].title,
                category=item["document"].category,
                uploaded_at=item["document"].created_at,
                reading_status=item["status"],
                read_as=item["kind"],
            )
            for item in documents["recent"]
        ],
        overdue_follow_ups=[_follow_up(f) for f in follow_ups["overdue"][:SHOWN]],
        upcoming_follow_ups=[_follow_up(f) for f in follow_ups["upcoming"][:SHOWN]],
        alerts_open=alerts["open"],
        alerts_acknowledged=alerts["acknowledged"],
        alerts_urgent=alerts["urgent"],
        top_alerts=[
            DashboardAlert(
                id=alert.id,
                title=alert.title,
                severity=alert.severity,
                source_document_title=document.title if document and document.deleted_at is None else None,
            )
            for alert, document in alerts["shown"]
        ],
        profile_suggestions=review["profile_suggestions"],
        unconfirmed_medicines=review["unconfirmed_medicines"],
        follow_ups_to_add=[DocumentCount(id=d.id, title=d.title, count=n) for d, n in review["follow_ups_to_add"]],
        failed_documents=[DocumentCount(id=d.id, title=d.title, count=1) for d in review["failed_documents"]],
        profile_filled=profile["filled"],
        profile_total=profile["total"],
        profile_missing=profile["missing"],
        allergies=profile["allergies"],
        conditions=profile["conditions"],
        active_medications=profile["active_medications"],
        bmi=profile["bmi"],
        bmi_category=profile["bmi_category"],
        latest_blood_pressure=latest_vital(profile["latest_vitals"]["blood_pressure"], "blood_pressure"),
        latest_heart_rate=latest_vital(profile["latest_vitals"]["heart_rate"], "heart_rate"),
        recent_activity=[TimelineEntryResponse.model_validate(entry) for entry in data["recent_activity"]],
    )
