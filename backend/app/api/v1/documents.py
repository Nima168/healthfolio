"""Medical document endpoints (api_contract_spec.md Section 6.1.1)."""

import uuid
from datetime import date
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BeforeValidator

from app.api.deps import CurrentUser, DbDep, SettingsDep
from app.core.errors import ApiError
from app.core.rate_limit import check_user_rate_limit
from app.repositories.documents import DocumentFilters
from app.schemas.documents import (
    Category,
    CopyType,
    DatePrecision,
    DocumentPage,
    DocumentResponse,
    DocumentUpdate,
    Pagination,
    ProviderList,
    ProviderName,
    ProviderOption,
    check_title,
    empty_to_none,
)
from app.services.document_service import DocumentService, UploadMetadata
from app.services.storage import DocumentStorage, get_document_storage

router = APIRouter(prefix="/documents", tags=["documents"])


def provide_storage(settings: SettingsDep) -> DocumentStorage:
    return get_document_storage(settings)


StorageDep = Annotated[DocumentStorage, Depends(provide_storage)]


def _service(session: DbDep, settings: SettingsDep, storage: StorageDep) -> DocumentService:
    return DocumentService(session, settings, storage)


ServiceDep = Annotated[DocumentService, Depends(_service)]

# Blank form fields arrive as "" from browsers; treat them as "not provided".
FormCategory = Annotated[Category | None, BeforeValidator(empty_to_none), Form()]
FormDate = Annotated[date | None, BeforeValidator(empty_to_none), Form()]
FormPrecision = Annotated[DatePrecision | None, BeforeValidator(empty_to_none), Form()]
FormProvider = Annotated[ProviderName, Form()]
FormCopyType = Annotated[CopyType | None, BeforeValidator(empty_to_none), Form()]


def _content_disposition(disposition: str, filename: str) -> str:
    """RFC 6266: an ASCII fallback plus the exact UTF-8 name."""
    fallback = "".join(c if 32 <= ord(c) < 127 and c not in '"\\' else "_" for c in filename) or "document"
    return f"{disposition}; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"


@router.post("", status_code=status.HTTP_201_CREATED)
def upload_document(
    user: CurrentUser,
    settings: SettingsDep,
    service: ServiceDep,
    file: Annotated[UploadFile, File()],
    # Optional here only so a missing and a blank name give the same friendly message below.
    title: Annotated[str | None, Form()] = None,
    category: FormCategory = None,
    document_date: FormDate = None,
    document_date_precision: FormPrecision = None,
    provider_name: FormProvider = None,
    # Digital PDF or scanned copy: decides between reading the PDF's text and OCR. Detected when absent.
    copy_type: FormCopyType = None,
) -> DocumentResponse:
    try:
        title = check_title(title or "")
    except ValueError as exc:
        raise ApiError(422, details=[{"field": "title", "issue": str(exc)}]) from None
    check_user_rate_limit("upload", user.id, settings.upload_rate_limit_per_hour, 3600)
    metadata = UploadMetadata(title, category, document_date, document_date_precision, provider_name, copy_type)
    document = service.upload(user.id, file.file, file.filename, metadata)
    return DocumentResponse.model_validate(document)


@router.get("")
def list_documents(
    user: CurrentUser,
    service: ServiceDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    category: Category | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    provider: Annotated[str | None, Query(max_length=200)] = None,
    provider_missing: bool = False,
) -> DocumentPage:
    """Filters combine; dates are the report's own date, and the hospital matches ignoring case and spacing."""
    filters = DocumentFilters(
        category=category,
        date_from=date_from,
        date_to=date_to,
        provider=provider.strip() or None if provider else None,
        provider_missing=provider_missing,
    )
    items, next_cursor = service.list_documents(user.id, limit, cursor, filters)
    return DocumentPage(
        items=[DocumentResponse.model_validate(item) for item in items],
        pagination=Pagination(limit=limit, next_cursor=next_cursor),
    )


@router.get("/providers")
def list_providers(user: CurrentUser, service: ServiceDep) -> ProviderList:
    """The hospitals and clinics in the user's documents, for the filter (api_contract_spec.md Section 6.1.1)."""
    names, missing = service.providers(user.id)
    return ProviderList(
        items=[ProviderOption(name=name, document_count=count) for name, count in names], without_provider=missing
    )


@router.get("/{document_id}")
def get_document(document_id: uuid.UUID, user: CurrentUser, service: ServiceDep) -> DocumentResponse:
    return DocumentResponse.model_validate(service.get(user.id, document_id))


@router.get("/{document_id}/file")
def download_document(
    document_id: uuid.UUID, user: CurrentUser, service: ServiceDep, download: bool = False
) -> StreamingResponse:
    document, chunks = service.open_file(user.id, document_id)
    disposition = "attachment" if download else "inline"
    return StreamingResponse(
        chunks,
        media_type=document.media_type,
        headers={
            "Content-Disposition": _content_disposition(disposition, document.original_filename or "document"),
            "Content-Length": str(document.size_bytes),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.patch("/{document_id}")
def update_document(
    document_id: uuid.UUID, changes: DocumentUpdate, user: CurrentUser, service: ServiceDep
) -> DocumentResponse:
    return DocumentResponse.model_validate(service.update(user.id, document_id, changes))


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: uuid.UUID, user: CurrentUser, service: ServiceDep) -> None:
    service.delete(user.id, document_id)
