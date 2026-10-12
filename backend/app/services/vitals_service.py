"""Vital sign readings: dated blood pressure and heart rate entered by the user (decision 2026-10-13).

Readings are kept separately because they change over time. They are shown as recorded: never labelled high
or low, and not compared or trended (deferred, goal_spec.md Section 6).
"""

import uuid
from datetime import UTC, date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.profile import VitalReading
from app.repositories.auth import AuditRepository

SYSTOLIC = (50, 260)  # mmHg; outside these is a typing mistake
DIASTOLIC = (30, 160)
HEART_RATE = (20, 250)  # beats per minute


def _invalid(field: str, issue: str) -> ApiError:
    return ApiError(422, "VALIDATION_ERROR", issue, [{"field": field, "issue": issue}])


def _check(field: str, value: int | None, bounds: tuple[int, int], label: str, unit: str) -> None:
    if value is not None and not bounds[0] <= value <= bounds[1]:
        raise _invalid(field, f"Check the {label}: it should be between {bounds[0]} and {bounds[1]} {unit}.")


def _sort_key(reading: VitalReading) -> tuple:
    return (reading.measured_on, reading.measured_time or time.min, reading.created_at)


class VitalsService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.audit = AuditRepository(session)

    def readings(self, user_id: uuid.UUID) -> list[VitalReading]:
        """Newest first."""
        readings = self.session.scalars(
            select(VitalReading).where(VitalReading.user_id == user_id, VitalReading.deleted_at.is_(None))
        )
        return sorted(readings, key=_sort_key, reverse=True)

    def latest(self, user_id: uuid.UUID) -> dict[str, VitalReading | None]:
        """The latest reading that has a blood pressure, and the latest that has a heart rate."""
        readings = self.readings(user_id)
        return {
            "blood_pressure": next((r for r in readings if r.systolic is not None), None),
            "heart_rate": next((r for r in readings if r.heart_rate is not None), None),
        }

    def add(
        self,
        user_id: uuid.UUID,
        measured_on: date,
        measured_time: time | None,
        systolic: int | None,
        diastolic: int | None,
        heart_rate: int | None,
        context: str | None,
    ) -> VitalReading:
        if systolic is None and diastolic is None and heart_rate is None:
            raise _invalid("systolic", "Enter a blood pressure, a heart rate, or both.")
        if (systolic is None) != (diastolic is None):
            field = "diastolic" if diastolic is None else "systolic"
            raise _invalid(field, "Enter both blood pressure numbers, for example 120 and 80.")
        _check("systolic", systolic, SYSTOLIC, "first (systolic) number", "mmHg")
        _check("diastolic", diastolic, DIASTOLIC, "second (diastolic) number", "mmHg")
        if systolic is not None and diastolic is not None and diastolic >= systolic:
            raise _invalid("diastolic", "The first number (systolic) should be higher than the second (diastolic).")
        _check("heart_rate", heart_rate, HEART_RATE, "heart rate", "bpm")
        today = datetime.now(UTC).date()
        if measured_on > today:
            raise _invalid("measured_on", "The date cannot be in the future.")
        if measured_on.year < 1900:
            raise _invalid("measured_on", "Enter a date after 1900.")

        reading = VitalReading(
            user_id=user_id,
            measured_on=measured_on,
            measured_time=measured_time,
            systolic=systolic,
            diastolic=diastolic,
            heart_rate=heart_rate,
            context=context,
        )
        self.session.add(reading)
        self.audit.record("vitals.added", "success", user_id, {})
        self.session.commit()
        return reading

    def remove(self, user_id: uuid.UUID, reading_id: uuid.UUID) -> None:
        reading = self.session.scalar(
            select(VitalReading).where(
                VitalReading.id == reading_id, VitalReading.user_id == user_id, VitalReading.deleted_at.is_(None)
            )
        )
        if reading is None:
            raise ApiError(404)
        reading.deleted_at = datetime.now(UTC)
        self.audit.record("vitals.removed", "success", user_id, {})
        self.session.commit()
