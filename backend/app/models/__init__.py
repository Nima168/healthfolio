"""Import every model here so Base.metadata is complete (Alembic autogenerate, tests)."""

from app.models.auth import AuditEvent, EmailDelivery, PasswordResetToken, RefreshToken, User
from app.models.document import Document
from app.models.extraction import Observation, ProcessingJob
from app.models.prescription import Condition, FollowUp, Medication, Suggestion

__all__ = [
    "AuditEvent",
    "Condition",
    "Document",
    "EmailDelivery",
    "FollowUp",
    "Medication",
    "Observation",
    "PasswordResetToken",
    "ProcessingJob",
    "RefreshToken",
    "Suggestion",
    "User",
]
