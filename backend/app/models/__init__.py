"""Import every model here so Base.metadata is complete (Alembic autogenerate, tests)."""

from app.models.alerts import Alert, AlertEvent, SafetyRule
from app.models.auth import AuditEvent, EmailDelivery, PasswordResetToken, RefreshToken, User
from app.models.document import Document
from app.models.extraction import Observation, ProcessingJob
from app.models.prescription import Condition, FollowUp, Medication, MedicationHistory, Suggestion
from app.models.profile import MedicalRecordItem, ProfileValue, ProfileValueHistory

__all__ = [
    "Alert",
    "AlertEvent",
    "AuditEvent",
    "Condition",
    "Document",
    "EmailDelivery",
    "FollowUp",
    "MedicalRecordItem",
    "Medication",
    "MedicationHistory",
    "Observation",
    "PasswordResetToken",
    "ProfileValue",
    "ProfileValueHistory",
    "ProcessingJob",
    "RefreshToken",
    "SafetyRule",
    "Suggestion",
    "User",
]
