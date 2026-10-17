"""The user's health profile (goal_spec.md F-1, frontend_spec.md Section 8).

- Personal values (date of birth, sex, blood group, height, weight) and allergies are entered by the user;
  every change is kept in `profile_value_history`.
- Conditions are the user's own (origin user_entered or suggestion_accepted).
- Diagnoses read from documents are suggestions: they change the profile only when the user accepts or
  corrects them, and never replace an existing value silently. A rejected one is not suggested again.
"""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.document import Document
from app.models.prescription import Condition, Medication
from app.models.profile import MedicalRecordItem, ProfileValue, ProfileValueHistory
from app.repositories.auth import AuditRepository
from app.services.jobs import shown_job

# Blood pressure and heart rate are not profile values: they change over time (decision 2026-10-13).
SINGLE_FIELDS = ("date_of_birth", "sex", "blood_group", "height", "weight")
UNITS = {"height": "cm", "weight": "kg"}
SEXES = ("female", "male", "other", "prefer_not_to_say")
BLOOD_GROUPS = ("A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-")
RANGES = {"height": (30, 272), "weight": (1, 500)}  # cm, kg: outside these is a typing mistake
# Adult BMI categories (decision 2026-10-13), compared on the BMI as shown (one decimal).
BMI_CATEGORIES = (
    (18.5, "underweight"),
    (25.0, "healthy"),
    (30.0, "overweight"),
    (35.0, "obesity_1"),
    (40.0, "obesity_2"),
    (float("inf"), "obesity_3"),
)
ADULT_AGE = 18
FAMILY_RELATIONS = (
    "Mother",
    "Father",
    "Sister",
    "Brother",
    "Grandmother",
    "Grandfather",
    "Aunt",
    "Uncle",
    "Child",
    "Other",
)


def _invalid(field: str, issue: str) -> ApiError:
    return ApiError(422, "VALIDATION_ERROR", issue, [{"field": field, "issue": issue}])


def _iso(value: object) -> date | None:
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _key(name: str) -> str:
    return " ".join(name.casefold().split())


def clean_value(field: str, raw: str) -> str:
    """The stored form of a value, or a 422 that explains what is wrong."""
    value = " ".join(raw.split())
    if field == "date_of_birth":
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            raise _invalid(field, "Enter the date as YYYY-MM-DD.") from None
        if parsed > datetime.now(UTC).date():
            raise _invalid(field, "The date of birth cannot be in the future.")
        if parsed.year < 1900:
            raise _invalid(field, "Enter a date of birth after 1900.")
        return parsed.isoformat()
    if field == "sex":
        if value not in SEXES:
            raise _invalid(field, "Choose one of the options.")
        return value
    if field == "blood_group":
        value = value.upper().replace(" ", "")
        if value not in BLOOD_GROUPS:
            raise _invalid(field, "Choose one of the blood groups.")
        return value
    if field in RANGES:
        try:
            number = float(value)
        except ValueError:
            raise _invalid(field, "Enter a number.") from None
        low, high = RANGES[field]
        if not low <= number <= high:
            raise _invalid(field, f"Enter a value between {low} and {high} {UNITS[field]}.")
        return f"{number:g}"
    if field == "allergy":
        if not value or len(value) > 200:
            raise _invalid(field, "Enter the allergy (up to 200 characters).")
        return value
    raise _invalid(field, "Unknown profile field.")


def bmi(height: ProfileValue | None, weight: ProfileValue | None) -> float | None:
    """Weight (kg) / height (m) squared, to one decimal; None without both values."""
    if height is None or weight is None:
        return None
    metres = float(height.value) / 100
    return round(float(weight.value) / (metres * metres), 1)


def bmi_category(value: float | None, date_of_birth: ProfileValue | None) -> str | None:
    """The adult category for a BMI; None without a BMI, or when the date of birth shows an age under 18
    (adult categories do not apply to children)."""
    if value is None:
        return None
    if date_of_birth is not None:
        born = date.fromisoformat(date_of_birth.value)
        today = datetime.now(UTC).date()
        age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        if age < ADULT_AGE:
            return None
    return next(name for upper, name in BMI_CATEGORIES if value < upper)


class ProfileService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.audit = AuditRepository(session)

    # ---------- read ----------

    def _values(self, user_id: uuid.UUID) -> list[ProfileValue]:
        return list(
            self.session.scalars(
                select(ProfileValue)
                .where(ProfileValue.user_id == user_id, ProfileValue.deleted_at.is_(None))
                .order_by(ProfileValue.created_at)
            )
        )

    def _conditions(self, user_id: uuid.UUID) -> list[Condition]:
        return list(
            self.session.scalars(
                select(Condition)
                .where(
                    Condition.user_id == user_id,
                    Condition.deleted_at.is_(None),
                    Condition.origin != "document_extracted",
                )
                .order_by(Condition.created_at)
            )
        )

    def suggestions(self, user_id: uuid.UUID) -> list[tuple[Condition, Document]]:
        """Diagnoses from the user's documents not yet reviewed, and not already in the profile."""
        confirmed = {_key(c.name) for c in self._conditions(user_id)}
        reviewed: set[tuple[uuid.UUID | None, str]] = {
            (c.source_document_id, _key(c.name))
            for c in self.session.scalars(
                select(Condition).where(Condition.user_id == user_id, Condition.review_status.is_not(None))
            )
        }  # including ones withdrawn by "Read again", so a rejected one is not suggested again
        rows = self.session.execute(
            select(Condition, Document)
            .join(Document, Document.id == Condition.source_document_id)
            .where(
                Condition.user_id == user_id,
                Condition.deleted_at.is_(None),
                Condition.origin == "document_extracted",
                Condition.review_status.is_(None),
                Document.deleted_at.is_(None),
            )
            .order_by(Document.document_date.desc().nulls_last(), Condition.position)
        )
        seen: set[str] = set()
        result = []
        for condition, document in rows:
            key = _key(condition.name)
            if key in confirmed or key in seen or (condition.source_document_id, key) in reviewed:
                continue
            seen.add(key)
            result.append((condition, document))
        return result

    def profile(self, user_id: uuid.UUID) -> dict:
        values = self._values(user_id)
        single = {v.field: v for v in values if v.field in SINGLE_FIELDS}
        records = self._records(user_id)
        return {
            "values": single,
            "bmi": (value := bmi(single.get("height"), single.get("weight"))),
            "bmi_category": bmi_category(value, single.get("date_of_birth")),
            "allergies": [v for v in values if v.field == "allergy"],
            "conditions": self._conditions(user_id),
            "suggestions": self.suggestions(user_id),
            "surgeries": [r for r in records if r.kind == "surgery"],
            "hospitalizations": [r for r in records if r.kind == "hospitalization"],
            "document_stays": self.document_stays(user_id),
            "family_history": [r for r in records if r.kind == "family"],
            "active_medications": self.active_medications(user_id),
        }

    def _records(self, user_id: uuid.UUID) -> list[MedicalRecordItem]:
        return list(
            self.session.scalars(
                select(MedicalRecordItem)
                .where(MedicalRecordItem.user_id == user_id, MedicalRecordItem.deleted_at.is_(None))
                .order_by(MedicalRecordItem.occurred_on.desc().nulls_last(), MedicalRecordItem.created_at)
            )
        )

    def document_stays(self, user_id: uuid.UUID) -> list[dict]:
        """Hospital stays read from discharge summaries (shown as read; not editable here)."""
        stays = []
        documents = self.session.scalars(
            select(Document).where(Document.user_id == user_id, Document.deleted_at.is_(None))
        )
        for document in documents:
            job = shown_job(self.session, document.id)
            if job is None or job.status not in ("completed", "completed_with_warnings"):
                continue
            if job.document_kind != "discharge_summary":
                continue
            details = job.details or {}
            diagnoses = [
                c.name
                for c in self.session.scalars(
                    select(Condition)
                    .where(
                        Condition.source_document_id == document.id,
                        Condition.processing_job_id == job.id,
                        Condition.deleted_at.is_(None),
                    )
                    .order_by(Condition.position)
                )
            ]
            stays.append(
                {
                    "document": document,
                    "facility_name": details.get("facility_name"),
                    "admitted_on": _iso(details.get("admitted_on")),
                    "discharged_on": _iso(details.get("discharged_on")),
                    "diagnoses": diagnoses,
                }
            )
        return sorted(stays, key=lambda s: s["discharged_on"] or date.min, reverse=True)

    def active_medications(self, user_id: uuid.UUID) -> list[Medication]:
        """Medicines the user marked as taking or added as taking (never inferred from a document)."""
        return list(
            self.session.scalars(
                select(Medication)
                .where(
                    Medication.user_id == user_id,
                    Medication.deleted_at.is_(None),
                    Medication.status == "active",
                )
                .order_by(Medication.kind, Medication.name)
            )
        )

    def history(self, user_id: uuid.UUID) -> list[ProfileValueHistory]:
        return list(
            self.session.scalars(
                select(ProfileValueHistory)
                .where(ProfileValueHistory.user_id == user_id)
                .order_by(ProfileValueHistory.changed_at.desc(), ProfileValueHistory.id)
            )
        )

    # ---------- personal values and allergies ----------

    def _record(self, value: ProfileValue, change: str, before: str | None, after: str | None) -> None:
        self.session.add(
            ProfileValueHistory(
                profile_value_id=value.id,
                user_id=value.user_id,
                field=value.field,
                previous_value=before,
                new_value=after,
                change_origin=change,
                changed_at=datetime.now(UTC),
            )
        )

    def set_value(self, user_id: uuid.UUID, field: str, raw: str | None) -> None:
        """Set, change, or clear (empty) one personal value; unchanged values write no history."""
        if field not in SINGLE_FIELDS:
            raise ApiError(404)
        current = next((v for v in self._values(user_id) if v.field == field), None)
        new = clean_value(field, raw) if raw is not None and raw.strip() else None
        if current is None and new is None:
            return
        if current is None:
            value = ProfileValue(user_id=user_id, field=field, value=new, unit=UNITS.get(field), origin="user_entered")
            self.session.add(value)
            self.session.flush()
            self._record(value, "added", None, new)
        elif new is None:
            current.deleted_at = datetime.now(UTC)
            self._record(current, "removed", current.value, None)
        elif new != current.value:
            self._record(current, "changed", current.value, new)
            current.value = new
        else:
            return
        self.audit.record("profile.updated", "success", user_id, {"field": field})
        self.session.commit()

    def add_allergy(
        self, user_id: uuid.UUID, raw: str, category: str | None = None, reaction: str | None = None
    ) -> ProfileValue:
        name = clean_value("allergy", raw)
        if any(_key(v.value) == _key(name) for v in self._values(user_id) if v.field == "allergy"):
            raise ApiError(409, "ALREADY_RECORDED", "This allergy is already in your profile.")
        value = ProfileValue(
            user_id=user_id,
            field="allergy",
            value=name,
            category=category,
            detail=" ".join(reaction.split()) or None if reaction else None,
            origin="user_entered",
        )
        self.session.add(value)
        self.session.flush()
        self._record(value, "added", None, name)
        self.audit.record("profile.updated", "success", user_id, {"field": "allergy"})
        self.session.commit()
        return value

    def remove_allergy(self, user_id: uuid.UUID, allergy_id: uuid.UUID) -> None:
        value = self.session.scalar(
            select(ProfileValue).where(
                ProfileValue.id == allergy_id,
                ProfileValue.user_id == user_id,
                ProfileValue.field == "allergy",
                ProfileValue.deleted_at.is_(None),
            )
        )
        if value is None:
            raise ApiError(404)
        value.deleted_at = datetime.now(UTC)
        self._record(value, "removed", value.value, None)
        self.audit.record("profile.updated", "success", user_id, {"field": "allergy"})
        self.session.commit()

    # ---------- surgeries, hospitalizations, family history ----------

    def add_record(
        self,
        user_id: uuid.UUID,
        kind: str,
        name: str,
        occurred_on: date | None,
        relation: str | None,
        notes: str | None,
    ) -> MedicalRecordItem:
        if occurred_on and occurred_on > datetime.now(UTC).date():
            raise _invalid("occurred_on", "The date cannot be in the future.")
        if kind == "family":
            if relation not in FAMILY_RELATIONS:
                raise _invalid("relation", "Choose who in your family.")
            occurred_on = None
        else:
            relation = None
        item = MedicalRecordItem(
            user_id=user_id, kind=kind, name=name, occurred_on=occurred_on, relation=relation, notes=notes
        )
        self.session.add(item)
        self.audit.record("profile.record_added", "success", user_id, {"kind": kind})
        self.session.commit()
        return item

    def remove_record(self, user_id: uuid.UUID, item_id: uuid.UUID) -> None:
        item = self.session.scalar(
            select(MedicalRecordItem).where(
                MedicalRecordItem.id == item_id,
                MedicalRecordItem.user_id == user_id,
                MedicalRecordItem.deleted_at.is_(None),
            )
        )
        if item is None:
            raise ApiError(404)
        item.deleted_at = datetime.now(UTC)
        self.audit.record("profile.record_removed", "success", user_id, {"kind": item.kind})
        self.session.commit()

    # ---------- conditions ----------

    def _condition(self, user_id: uuid.UUID, condition_id: uuid.UUID) -> Condition:
        condition = self.session.scalar(
            select(Condition).where(
                Condition.id == condition_id,
                Condition.user_id == user_id,
                Condition.deleted_at.is_(None),
                Condition.origin != "document_extracted",
            )
        )
        if condition is None:
            raise ApiError(404)
        return condition

    def _check_new_name(self, user_id: uuid.UUID, name: str, except_id: uuid.UUID | None = None) -> None:
        if any(_key(c.name) == _key(name) and c.id != except_id for c in self._conditions(user_id)):
            raise ApiError(409, "ALREADY_RECORDED", "This condition is already in your profile.")

    def add_condition(
        self, user_id: uuid.UUID, name: str, status: str, origin: str = "user_entered", source: Condition | None = None
    ) -> Condition:
        self._check_new_name(user_id, name)
        condition = Condition(
            user_id=user_id,
            name=name,
            status=status,
            origin=origin,
            source_document_id=source.source_document_id if source else None,
        )
        self.session.add(condition)
        self.session.flush()
        self.audit.record("profile.condition_added", "success", user_id, {"condition_id": str(condition.id)})
        return condition

    def update_condition(self, user_id: uuid.UUID, condition_id: uuid.UUID, name: str | None, status: str | None):
        condition = self._condition(user_id, condition_id)
        if name is not None:
            self._check_new_name(user_id, name, condition.id)
            condition.name = name
        if status is not None:
            condition.status = status
        self.audit.record("profile.condition_updated", "success", user_id, {"condition_id": str(condition.id)})
        self.session.commit()
        return condition

    def remove_condition(self, user_id: uuid.UUID, condition_id: uuid.UUID) -> None:
        condition = self._condition(user_id, condition_id)
        condition.deleted_at = datetime.now(UTC)
        self.audit.record("profile.condition_removed", "success", user_id, {"condition_id": str(condition.id)})
        self.session.commit()

    def review_suggestion(
        self, user_id: uuid.UUID, suggestion_id: uuid.UUID, action: str, name: str | None, status: str
    ) -> None:
        """accept / correct (with a new name) / reject a diagnosis suggested from a document."""
        suggestion = self.session.scalar(
            select(Condition).where(
                Condition.id == suggestion_id,
                Condition.user_id == user_id,
                Condition.deleted_at.is_(None),
                Condition.origin == "document_extracted",
            )
        )
        if suggestion is None:
            raise ApiError(404)
        if suggestion.review_status is not None:
            raise ApiError(409, "ALREADY_REVIEWED", "This suggestion has already been reviewed.")
        if action == "correct" and not name:
            raise _invalid("name", "Enter the corrected name.")

        if action in ("accept", "correct"):
            chosen = name if action == "correct" else suggestion.name
            existing = next((c for c in self._conditions(user_id) if _key(c.name) == _key(chosen)), None)
            profile_condition = existing or self.add_condition(
                user_id, chosen, status, origin="suggestion_accepted", source=suggestion
            )
            suggestion.profile_condition_id = profile_condition.id
        suggestion.review_status = {"accept": "accepted", "correct": "corrected", "reject": "rejected"}[action]
        suggestion.reviewed_at = datetime.now(UTC)
        self.audit.record(
            "profile.suggestion_reviewed", "success", user_id, {"condition_id": str(suggestion.id), "action": action}
        )
        self.session.commit()
