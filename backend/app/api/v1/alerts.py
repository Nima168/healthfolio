"""Safety alerts (api_contract_spec.md Section 6.8)."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, DbDep
from app.models.alerts import Alert, AlertEvent, SafetyRule
from app.models.document import Document
from app.schemas.alerts import AlertEventResponse, AlertListResponse, AlertResponse, AlertUpdate
from app.services.alert_service import AlertService
from app.services.jobs import shown_job

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _service(session: DbDep) -> AlertService:
    return AlertService(session)


ServiceDep = Annotated[AlertService, Depends(_service)]


def _response(service: AlertService, alert: Alert, document: Document | None, events: list[AlertEvent]):
    rule = service.session.get(SafetyRule, alert.rule_id)
    live = document is not None and document.deleted_at is None
    job = shown_job(service.session, document.id) if live else None
    report_type = (job.document_kind if job and job.document_kind else document.category) if live else None
    # The result's own date first (lab results carry it), then the report's date.
    result_date = (alert.input_refs or {}).get("result_date")
    report_date = None
    if live:
        report_date = (
            date.fromisoformat(result_date) if result_date else (job.document_date if job else None)
        ) or document.document_date
    return AlertResponse(
        id=alert.id,
        rule_code=rule.code if rule else "",
        rule_version=alert.rule_version,
        rule_description=rule.description if rule else "",
        severity=alert.severity,
        status=alert.status,
        title=alert.title,
        reason=alert.reason,
        uncertainty=alert.uncertainty,
        next_steps=alert.next_steps,
        explanation_text=alert.explanation_text,
        source_document_id=alert.source_document_id,
        source_document_title=document.title if live else None,
        report_type=report_type,
        report_date=report_date,
        created_at=alert.created_at,
        acknowledged_at=alert.acknowledged_at,
        resolved_at=alert.resolved_at,
        resolved_by=alert.resolved_by,
        resolution_note=alert.resolution_note,
        history=[
            AlertEventResponse(event=e.event, actor=e.actor, note=e.note, occurred_at=e.occurred_at) for e in events
        ],
    )


@router.get("")
def list_alerts(user: CurrentUser, service: ServiceDep) -> AlertListResponse:
    """Open first, then acknowledged, then resolved; the rules are applied to current records first."""
    return AlertListResponse(items=[_response(service, *row) for row in service.list_alerts(user.id)])


@router.patch("/{alert_id}")
def update_alert(alert_id: uuid.UUID, body: AlertUpdate, user: CurrentUser, service: ServiceDep) -> AlertResponse:
    return _response(service, *service.change_status(user.id, alert_id, body.status, body.note))
