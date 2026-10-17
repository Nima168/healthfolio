"""Medication records: list, add, edit, status, history, removal, and how document changes treat them.

Real test database, fake Groq client (no network, no cost).
"""

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models.prescription import Medication, MedicationHistory
from tests.ai_fakes import prescription, response
from tests.test_extraction_flow import make_user, run_worker
from tests.test_prescription_flow import upload_prescription

pytestmark = pytest.mark.integration

URL = "/api/v1/medications"


@pytest.fixture
def asha(client, db, storage_dir):
    return make_user(client, "asha@example.com")


@pytest.fixture
def settings():
    return get_settings()


def medicines(client, headers):
    return client.get(URL, headers=headers).json()["items"]


def history(client, headers, medication_id):
    return client.get(f"{URL}/{medication_id}/history", headers=headers).json()["items"]


def read_prescription(client, headers, settings):
    document_id = upload_prescription(client, headers)
    run_worker(settings, response(prescription()))
    return document_id


# ---------- from documents ----------


def test_medicines_from_a_prescription_are_listed_but_not_confirmed(client, asha, settings):
    document_id = read_prescription(client, asha, settings)

    items = medicines(client, asha)

    assert items, "the prescription's medicines are listed"
    first = items[0]
    assert (first["name"], first["strength"], first["dosage_text"]) == ("Atorvastatin", "10 mg", "once daily at night")
    assert first["status"] == "unknown"  # never inferred as being taken
    assert (first["origin"], first["status_confirmed"], first["edited"]) == ("document_extracted", False, False)
    assert first["source_document_id"] == document_id
    assert first["source_document_title"] == "Synthetic report 1"
    assert first["source_document_deleted"] is False


def test_marking_as_taking_confirms_and_keeps_history(client, asha, settings):
    read_prescription(client, asha, settings)
    medication_id = medicines(client, asha)[0]["id"]

    taking = client.patch(f"{URL}/{medication_id}", headers=asha, json={"status": "active"})

    assert taking.status_code == 200
    assert (taking.json()["status"], taking.json()["status_confirmed"], taking.json()["edited"]) == (
        "active",
        True,
        False,
    )
    [entry] = history(client, asha, medication_id)
    assert entry["change"] == "status_changed"
    assert entry["changes"] == {"status": ["unknown", "active"]}
    assert entry["snapshot"]["status"] == "unknown"

    unsure = client.patch(f"{URL}/{medication_id}", headers=asha, json={"status": "unknown"}).json()
    assert unsure["status_confirmed"] is False


def test_editing_details_records_before_and_after(client, asha, settings):
    read_prescription(client, asha, settings)
    medication_id = medicines(client, asha)[0]["id"]

    edited = client.patch(
        f"{URL}/{medication_id}",
        headers=asha,
        json={"strength": " 20  mg ", "start_date": "2026-10-07", "notes": "Changed by Dr. Sample"},
    ).json()

    assert (edited["strength"], edited["start_date"], edited["edited"]) == ("20 mg", "2026-10-07", True)
    assert edited["review_reason"] is None
    [entry] = history(client, asha, medication_id)
    assert entry["change"] == "edited"
    assert entry["changes"] == {
        "strength": ["10 mg", "20 mg"],
        "start_date": [None, "2026-10-07"],
        "notes": [None, "Changed by Dr. Sample"],
    }


def test_an_unchanged_edit_adds_no_history(client, asha, settings):
    read_prescription(client, asha, settings)
    item = medicines(client, asha)[0]

    client.patch(f"{URL}/{item['id']}", headers=asha, json={"name": item["name"], "strength": item["strength"]})

    assert history(client, asha, item["id"]) == []


# ---------- added by the user ----------


def test_add_a_medicine(client, asha, db):
    created = client.post(
        URL, headers=asha, json={"name": "  Vitamin D3 ", "strength": "1000 IU", "dosage_text": "once daily"}
    )

    assert created.status_code == 201
    body = created.json()
    assert (body["name"], body["status"], body["origin"], body["status_confirmed"]) == (
        "Vitamin D3",
        "active",
        "user_entered",
        True,
    )
    assert body["source_document_id"] is None
    [entry] = history(client, asha, body["id"])
    assert entry["change"] == "added"
    assert entry["changes"]["name"] == [None, "Vitamin D3"]


@pytest.mark.parametrize(
    "body",
    [
        {"name": "   "},
        {"name": "A", "start_date": "2026-10-10", "end_date": "2026-10-01"},
        {"name": "A", "status": "taking"},
        {"name": "A", "reminder": True},
        {"name": "x" * 201},
    ],
)
def test_invalid_medicines_are_rejected(client, asha, body):
    assert client.post(URL, headers=asha, json=body).status_code == 422


def test_end_date_before_existing_start_date_is_rejected(client, asha):
    medication_id = client.post(URL, headers=asha, json={"name": "A", "start_date": "2026-10-10"}).json()["id"]

    rejected = client.patch(f"{URL}/{medication_id}", headers=asha, json={"end_date": "2026-10-01"})

    assert rejected.status_code == 422
    assert history(client, asha, medication_id)[0]["change"] == "added"  # nothing else recorded


def test_list_order_taking_then_not_confirmed_then_stopped(client, asha):
    for name, status in [("Stopped one", "stopped"), ("Unsure one", "unknown"), ("Taking one", "active")]:
        client.post(URL, headers=asha, json={"name": name, "status": status})

    assert [m["name"] for m in medicines(client, asha)] == ["Taking one", "Unsure one", "Stopped one"]


# ---------- removal ----------


def test_remove_keeps_the_record_and_history(client, asha, db):
    medication_id = client.post(URL, headers=asha, json={"name": "Vitamin D3"}).json()["id"]

    assert client.delete(f"{URL}/{medication_id}", headers=asha).status_code == 204

    assert medicines(client, asha) == []
    assert client.get(f"{URL}/{medication_id}/history", headers=asha).status_code == 404
    row = db.scalar(select(Medication))
    assert row.deleted_at is not None
    assert [h.change_origin for h in db.scalars(select(MedicationHistory).order_by(MedicationHistory.changed_at))] == [
        "added",
        "removed",
    ]


# ---------- other users ----------


def test_other_users_cannot_see_or_change_medicines(client, asha, db):
    medication_id = client.post(URL, headers=asha, json={"name": "Vitamin D3"}).json()["id"]
    ravi = make_user(client, "ravi@example.com")

    assert medicines(client, ravi) == []
    assert client.patch(f"{URL}/{medication_id}", headers=ravi, json={"status": "stopped"}).status_code == 404
    assert client.get(f"{URL}/{medication_id}/history", headers=ravi).status_code == 404
    assert client.delete(f"{URL}/{medication_id}", headers=ravi).status_code == 404
    assert medicines(client, asha)[0]["status"] == "active"


def test_requires_sign_in(client, db):
    assert client.get(URL).status_code == 401


# ---------- document changes ----------


def test_read_again_keeps_changed_medicines_without_doubling_them(client, asha, settings):
    document_id = read_prescription(client, asha, settings)
    before = medicines(client, asha)
    changed = before[0]
    client.patch(f"{URL}/{changed['id']}", headers=asha, json={"status": "active", "notes": "Taking since October"})

    assert client.post(f"/api/v1/documents/{document_id}/extract", headers=asha).status_code == 202
    run_worker(settings, response(prescription()))

    after = medicines(client, asha)
    assert len(after) == len(before)  # the same medicine is not listed twice
    kept = next(m for m in after if m["id"] == changed["id"])
    assert (kept["status"], kept["notes"]) == ("active", "Taking since October")
    others = [m for m in after if m["id"] != changed["id"]]
    assert all(m["id"] not in {b["id"] for b in before} for m in others)  # unchanged ones were read afresh
    # The document's summary still lists the kept medicine.
    summary = client.get(f"/api/v1/documents/{document_id}/observations", headers=asha).json()["prescription"]
    assert changed["name"] in [line["name"] for line in summary["medications"]]


def test_deleting_the_document_deletes_its_medicines_even_changed_ones(client, asha, settings):
    document_id = read_prescription(client, asha, settings)
    items = medicines(client, asha)
    client.patch(f"{URL}/{items[0]['id']}", headers=asha, json={"status": "stopped"})
    own = client.post(URL, headers=asha, json={"name": "Vitamin C"}).json()

    assert client.delete(f"/api/v1/documents/{document_id}", headers=asha).status_code == 204

    assert [m["id"] for m in medicines(client, asha)] == [own["id"]]  # medicines added by hand stay
