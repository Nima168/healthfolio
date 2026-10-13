"""Exports of the signed-in user's data (api_contract_spec.md Section 6.13). Built on request, never stored."""

from datetime import UTC, datetime

from fastapi import APIRouter
from fastapi.responses import Response, StreamingResponse

from app.api.deps import CurrentUser, DbDep, SettingsDep
from app.core.rate_limit import check_user_rate_limit
from app.repositories.auth import AuditRepository
from app.services.export_service import ExportService
from app.services.health_pdf import HealthPdf
from app.services.storage import get_document_storage

router = APIRouter(prefix="/account/export", tags=["account"])

EXPORTS_PER_HOUR = 30


def _headers(filename: str) -> dict[str, str]:
    return {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    }


def _name(kind: str, extension: str) -> str:
    return f"health-{kind}-{datetime.now(UTC).date().isoformat()}.{extension}"


def _record(session: DbDep, user: CurrentUser, export_format: str) -> None:
    check_user_rate_limit("export", user.id, EXPORTS_PER_HOUR, 3600)
    AuditRepository(session).record("account.exported", "success", user.id, {"format": export_format})
    session.commit()


@router.get("/pdf")
def export_pdf(user: CurrentUser, session: DbDep) -> Response:
    _record(session, user, "pdf")
    return Response(
        HealthPdf(session).build(user), media_type="application/pdf", headers=_headers(_name("summary", "pdf"))
    )


@router.get("/json")
def export_json(user: CurrentUser, session: DbDep) -> Response:
    _record(session, user, "json")
    body = ExportService(session).json_export(user)
    return Response(body, media_type="application/json", headers=_headers(_name("data", "json")))


@router.get("/csv")
def export_csv(user: CurrentUser, session: DbDep) -> Response:
    _record(session, user, "csv")
    body = ExportService(session).csv_export(user)
    return Response(body, media_type="application/zip", headers=_headers(_name("data-csv", "zip")))


@router.get("/documents")
def export_documents(user: CurrentUser, session: DbDep, settings: SettingsDep) -> StreamingResponse:
    _record(session, user, "documents")
    stream = ExportService(session).documents_export(user.id, get_document_storage(settings))
    return StreamingResponse(stream, media_type="application/zip", headers=_headers(_name("documents", "zip")))
