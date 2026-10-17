"""Request and response schemas for authentication (api_contract_spec.md Section 5.1.1)."""

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from app.core.security import PASSWORD_MAX_LENGTH, password_policy_problem

# Deliberately simple: one "@", a dot in the domain, no spaces. Deliverability is not checked.
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalise_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 254 or not _EMAIL_PATTERN.match(email):
        raise ValueError("Enter a valid email address.")
    return email


class _EmailField(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def check_email(cls, value: str) -> str:
        return normalise_email(value)


def _check_new_password(password: str, info: ValidationInfo) -> str:
    problem = password_policy_problem(password, info.data.get("email", ""))
    if problem:
        raise ValueError(problem)
    return password


class RegisterRequest(_EmailField):
    password: str = Field(max_length=PASSWORD_MAX_LENGTH * 4)  # policy check below gives the friendly message
    display_name: str | None = Field(default=None, max_length=100)

    @field_validator("password")
    @classmethod
    def check_password(cls, value: str, info: ValidationInfo) -> str:
        return _check_new_password(value, info)

    @field_validator("display_name")
    @classmethod
    def tidy_display_name(cls, value: str | None) -> str | None:
        value = value.strip() if value else None
        return value or None


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(max_length=100)

    @field_validator("display_name")
    @classmethod
    def tidy_display_name(cls, value: str | None) -> str | None:
        value = value.strip() if value else None
        return value or None


class LoginRequest(BaseModel):
    # Not validated beyond length: login must not reveal policy details or account existence.
    email: str = Field(max_length=254)
    password: str = Field(max_length=PASSWORD_MAX_LENGTH * 4)

    @field_validator("email")
    @classmethod
    def lower_email(cls, value: str) -> str:
        return value.strip().lower()


class ForgotPasswordRequest(_EmailField):
    pass


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    new_password: str = Field(max_length=PASSWORD_MAX_LENGTH * 4)

    @field_validator("new_password")
    @classmethod
    def check_password(cls, value: str, info: ValidationInfo) -> str:
        return _check_new_password(value, info)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str | None
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_in: int
    user: UserResponse


class MessageResponse(BaseModel):
    message: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=PASSWORD_MAX_LENGTH * 4)
    new_password: str = Field(max_length=PASSWORD_MAX_LENGTH * 4)  # policy checked with the user's email


class DeleteAccountRequest(BaseModel):
    password: str = Field(max_length=PASSWORD_MAX_LENGTH * 4)
    confirmation: str = Field(max_length=20)
