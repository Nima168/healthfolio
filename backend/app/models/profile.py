"""Health profile values and their history (data_model_spec.md Section 5.4)."""

import uuid
from datetime import date, datetime, time

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, Time, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.auth import TimestampMixin
from app.models.document import _in
from app.models.extraction import ORIGINS

# Single-valued fields hold one live row each; allergies use one row per allergy.
PROFILE_FIELDS = (
    "date_of_birth",
    "sex",
    "blood_group",
    "height",
    "weight",
    "blood_pressure",
    "heart_rate",
    "allergy",
)
ALLERGY_CATEGORIES = ("drug", "food", "environmental", "other")
RECORD_KINDS = ("surgery", "hospitalization", "family")
PROFILE_CHANGES = ("added", "changed", "removed")


class ProfileValue(TimestampMixin, Base):
    __tablename__ = "profile_values"
    __table_args__ = (
        CheckConstraint(_in("field", PROFILE_FIELDS), name="ck_profile_values_field"),
        CheckConstraint(_in("origin", ORIGINS), name="ck_profile_values_origin"),
        CheckConstraint(
            f"category IS NULL OR {_in('category', ALLERGY_CATEGORIES)}", name="ck_profile_values_category"
        ),
        Index("ix_profile_values_user_field", "user_id", "field"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    field: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[str] = mapped_column(String(200), nullable=False)  # as entered (dates ISO, numbers as text)
    unit: Mapped[str | None] = mapped_column(String(20))
    category: Mapped[str | None] = mapped_column(String(20))  # allergies: drug, food, environmental, other
    detail: Mapped[str | None] = mapped_column(String(300))  # allergies: the reaction, as entered
    origin: Mapped[str] = mapped_column(String(32), default="user_entered", nullable=False)
    suggestion_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("suggestions.id", ondelete="SET NULL"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProfileValueHistory(Base):
    """One change to a profile value. Never edited."""

    __tablename__ = "profile_value_history"
    __table_args__ = (
        CheckConstraint(_in("change_origin", PROFILE_CHANGES), name="ck_profile_value_history_change"),
        Index("ix_profile_value_history_user", "user_id", "changed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    profile_value_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profile_values.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    field: Mapped[str] = mapped_column(String(32), nullable=False)
    previous_value: Mapped[str | None] = mapped_column(String(200))
    new_value: Mapped[str | None] = mapped_column(String(200))
    change_origin: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MedicalRecordItem(TimestampMixin, Base):
    """Past surgeries, hospitalizations, and family medical history, as entered by the user."""

    __tablename__ = "medical_record_items"
    __table_args__ = (
        CheckConstraint(_in("kind", RECORD_KINDS), name="ck_medical_record_items_kind"),
        Index("ix_medical_record_items_user_kind", "user_id", "kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)  # the surgery, reason for stay, or condition
    occurred_on: Mapped[date | None] = mapped_column(Date)  # surgeries and hospitalizations
    relation: Mapped[str | None] = mapped_column(String(50))  # family history: e.g. Mother
    notes: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VitalReading(TimestampMixin, Base):
    """One blood pressure and/or heart rate reading at a point in time, as entered by the user.

    Kept as separate dated readings because these values change over time; never labelled high or low.
    """

    __tablename__ = "vital_readings"
    __table_args__ = (
        CheckConstraint("systolic IS NOT NULL OR heart_rate IS NOT NULL", name="ck_vital_readings_something_measured"),
        CheckConstraint("(systolic IS NULL) = (diastolic IS NULL)", name="ck_vital_readings_pressure_pair"),
        Index("ix_vital_readings_user_measured", "user_id", "measured_on"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    measured_on: Mapped[date] = mapped_column(Date, nullable=False)
    measured_time: Mapped[time | None] = mapped_column(Time)
    systolic: Mapped[int | None] = mapped_column(Integer)  # mmHg
    diastolic: Mapped[int | None] = mapped_column(Integer)  # mmHg
    heart_rate: Mapped[int | None] = mapped_column(Integer)  # beats per minute
    context: Mapped[str | None] = mapped_column(String(200))  # e.g. "morning, at home, sitting"
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
