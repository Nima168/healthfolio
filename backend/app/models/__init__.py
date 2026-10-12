"""Import every model here so Base.metadata is complete (Alembic autogenerate, tests)."""

from app.models.alerts import Alert, AlertEvent, SafetyRule
from app.models.auth import AuditEvent, EmailDelivery, PasswordResetToken, RefreshToken, User
from app.models.document import Document
from app.models.extraction import Observation, ProcessingJob
from app.models.prescription import Condition, FollowUp, Medication, MedicationHistory, Suggestion

__all__ = [
    "Alert",
    "AlertEvent",
    "AuditEvent",
    "Condition",
    "Document",
    "EmailDelivery",
    "FollowUp",
    "Medication",
    "MedicationHistory",
    "Observation",
    "PasswordResetToken",
    "ProcessingJob",
    "RefreshToken",
    "SafetyRule",
    "Suggestion",
    "User",
]
