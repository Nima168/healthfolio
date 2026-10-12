"""Dashboard: a short overview built only from the user's own records.

Real test database, fake Groq client (no network, no cost).
"""

from datetime import date, timedelta

import pytest

from app.core.config import get_settings
from tests.ai_fakes import prescription, response
from tests.test_alerts import LAB
from tests.test_discharge import discharge, upload_discharge
from tests.test_extraction_flow import make_user, run_worker, upload_report
from tests.test_prescription_flow import upload_prescription

pytestmark = pytest.mark.integration

URL = "/api/v1/dashboard"


@pytest.fixture
def asha(client, db, storage_dir):
    return make_user(client, "asha@example.com")


def dashboard(client, headers):
    response_ = client.get(URL, headers=headers)
    assert response_.status_code == 200, response_.text
    return response_.json()


def test_new_account_is_empty_not_healthy(client, asha):
    body = dashboard(client, asha)

    assert (body["documents_total"], body["recent_documents"], body["alerts_open"]) == (0, [], 0)
    assert (body["profile_filled"], body["profile_total"]) == (0, 5)
    assert body["profile_missing"] == ["date_of_birth", "sex", "blood_group", "height", "weight"]
    assert (body["bmi"], body["latest_blood_pressure"], body["recent_activity"]) == (None, None, [])


def test_overview_of_documents_alerts_and_items_to_review(client, asha):
    upload_report(client, asha, "lab")
    run_worker(get_settings(), response(LAB))
    prescription_id = upload_prescription(client, asha)
    run_worker(get_settings(), response(prescription()))
    upload_discharge(client, asha)
    run_worker(get_settings(), response(discharge()))
    upload_report(client, asha, "waiting")  # not read yet

    body = dashboard(client, asha)

    assert body["documents_total"] == 4
    assert body["documents_reading"] == 1
    assert [d["reading_status"] for d in body["recent_documents"]][0] == "pending"  # newest first
    assert body["alerts_open"] > 0 and len(body["top_alerts"]) == 3
    assert body["profile_suggestions"] == 3  # the discharge summary's diagnoses
    assert body["unconfirmed_medicines"] > 0  # medicines read from documents are not confirmed
    [to_add] = [d for d in body["follow_ups_to_add"] if d["id"] == prescription_id]
    assert to_add["count"] > 0
    assert body["failed_documents"] == []
    assert body["recent_activity"]  # lab results and the hospital stay, all dated up to today


def test_follow_ups_overdue_and_upcoming(client, asha):
    document_id = upload_prescription(client, asha)
    run_worker(get_settings(), response(prescription()))
    client.post(f"/api/v1/documents/{document_id}/follow-ups", headers=asha)

    body = dashboard(client, asha)
    added = client.get("/api/v1/follow-ups", headers=asha).json()["items"]

    # The follow-ups list is in due-date order; the dashboard shows at most five of each.
    assert [f["id"] for f in body["overdue_follow_ups"]] == [f["id"] for f in added if f["overdue"]][:5]
    soon = date.today() + timedelta(days=30)
    expected = [f["id"] for f in added if not f["overdue"] and date.fromisoformat(f["due_date"]) <= soon]
    assert [f["id"] for f in body["upcoming_follow_ups"]] == expected[:5]


def test_profile_card(client, asha):
    client.patch("/api/v1/profile/values", headers=asha, json={"height": "160", "weight": "64", "sex": "female"})
    client.post("/api/v1/profile/allergies", headers=asha, json={"name": "Penicillin", "category": "drug"})
    client.post("/api/v1/vitals", headers=asha, json={"measured_on": "2026-10-10", "systolic": 120, "diastolic": 80})

    body = dashboard(client, asha)

    assert (body["profile_filled"], body["profile_missing"]) == (3, ["date_of_birth", "blood_group"])
    assert (body["allergies"], body["bmi"], body["bmi_category"]) == (["Penicillin"], 25.0, "overweight")
    assert body["latest_blood_pressure"]["value"] == "120/80"
    assert body["latest_heart_rate"] is None


def test_only_the_users_own_records(client, asha):
    upload_report(client, asha, "lab")
    run_worker(get_settings(), response(LAB))
    ravi = make_user(client, "ravi@example.com")

    body = dashboard(client, ravi)
    assert (body["documents_total"], body["alerts_open"], body["recent_activity"]) == (0, 0, [])
    assert client.get(URL).status_code == 401
