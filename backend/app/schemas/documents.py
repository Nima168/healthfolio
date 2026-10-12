"""Document request/response schemas (api_contract_spec.md Section 6.1.1)."""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, StringConstraints, model_validator

Category = Literal[
    "lab_report", "prescription", "discharge_summary", "consultation_note", "imaging_report", "other", "unknown"
]
DatePrecision = Literal["day", "month", "year", "unknown"]


def empty_to_none(value: object) -> object:
    """HTML forms send empty strings for blank optional fields."""
    if isinstance(value, str) and not value.strip():
        return None
    return value.strip() if isinstance(value, str) else value


# The length limit sits on the text type itself, so a missing value (None) is never length-checked.
ProviderName = Annotated[Annotated[str, StringConstraints(max_length=200)] | None, BeforeValidator(empty_to_none)]


TITLE_MAX_LENGTH = 200


def check_title(value: str) -> str:
    """The user's name for a document: required, trimmed, at most 200 characters."""
    value = value.strip()
    if not value:
        raise ValueError("Enter a name for this document.")
    if len(value) > TITLE_MAX_LENGTH:
        raise ValueError(f"Name must be at most {TITLE_MAX_LENGTH} characters.")
    return value


DocumentTitle = Annotated[str, AfterValidator(check_title)]


def normalise_date(document_date: date | None, precision: str | None) -> tuple[date | None, str | None]:
    """Store month/year precision as the first day of the period; a date without precision is a day."""
    if document_date is None:
        return None, None
    precision = precision or "day"
    if precision == "month":
        document_date = document_date.replace(day=1)
    elif precision == "year":
        document_date = document_date.replace(month=1, day=1)
    return document_date, precision


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    original_filename: str | None
    media_type: str
    size_bytes: int
    category: Category
    document_date: date | None
    document_date_precision: DatePrecision | None
    provider_name: str | None
    processing_status: str
    created_at: datetime
    updated_at: datetime


class Pagination(BaseModel):
    limit: int
    next_cursor: str | None


class ProviderOption(BaseModel):
    name: str  # the most used spelling; case and spacing variants are counted together
    document_count: int


class ProviderList(BaseModel):
    items: list[ProviderOption]
    without_provider: int  # documents with no hospital or clinic given


class DocumentPage(BaseModel):
    items: list[DocumentResponse]
    pagination: Pagination


class DocumentUpdate(BaseModel):
    """PATCH body: only fields present are changed; null clears a field."""

    model_config = ConfigDict(extra="forbid")

    title: DocumentTitle | None = None
    category: Category | None = None
    document_date: Annotated[date | None, BeforeValidator(empty_to_none)] = None
    document_date_precision: DatePrecision | None = None
    provider_name: ProviderName = None

    @model_validator(mode="after")
    def title_cannot_be_cleared(self) -> "DocumentUpdate":
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("Enter a name for this document.")
        return self

    @model_validator(mode="after")
    def precision_needs_date(self) -> "DocumentUpdate":
        if (
            "document_date_precision" in self.model_fields_set
            and self.document_date_precision is not None
            and "document_date" not in self.model_fields_set
        ):
            raise ValueError("document_date is required when setting document_date_precision.")
        return self
