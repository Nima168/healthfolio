"""The health timeline: records in date order, never merged across dates, with where each came from.

Real test database, fake Groq client (no network, no cost).
"""

import pytest

from app.core.config import get_settings
from tests.ai_fakes import payload, prescription, response, result
from tests.test_discharge import discharge, upload_discharge
from tests.test_extraction_flow import make_user, run_worker, upload_report
from tests.test_prescription_flow import upload_prescription

pytestmark = pytest.mark.integration

URL = "/api/v1/timeline"

LAB = payload(
    results=[
        result(),
        result(
            test_name="HbA1c",
            value_text="6.1",
            value_numeric=6.1,
            unit="%",
            reference_range_text="4.0 - 5.6",
            reference_low=4.0,
            reference_high=5.6,
        ),
        result(test_name="Vitamin B12", value_text="<150", value_numeric=None, unit="pg/mL"),
    ]
)


@pytest.fixture
def asha(client, db, storage_dir):
    return make_user(client, "asha@example.com")


def timeline(client, headers, **params):
    response_ = client.get(URL, headers=headers, params=params)
    assert response_.status_code == 200, response_.text
    return response_.json()


def items(client, headers, **params):
    return timeline(client, headers, **params)["items"]


def read_lab(client, headers):
    document_id = upload_report(client, headers, "lab")
    run_worker(get_settings(), response(LAB))
    return document_id


def read_prescription(client, headers):
    document_id = upload_prescription(client, headers)
    run_worker(get_settings(), response(prescription()))
    return document_id


def test_lab_results_are_one_entry_per_report_date_with_outside_range_first(client, asha):
    document_id = read_lab(client, asha)

    [entry] = items(client, asha)

    assert (entry["category"], entry["date"], entry["title"]) == ("lab_results", "2026-03-14", "Lab results: 3 tests")
    assert entry["lines"] == [
        "HbA1c 6.1 % (high; range 4.0 - 5.6)",
        "1 within range",
        "1 not compared (no clear value or range)",
    ]
    assert (entry["tag"], entry["trust"]) == ("1 outside range", "from_document")
    assert (entry["source_document_id"], entry["link"]) == (document_id, f"/documents/{document_id}")


def test_discharge_results_from_different_dates_are_never_merged(client, asha):
    upload_discharge(client, asha)
    run_worker(get_settings(), response(discharge()))

    entries = items(client, asha)

    stay = next(e for e in entries if e["category"] == "hospital_stays")
    assert stay["date"] == "2026-08-13"
    assert stay["title"] == "Hospital stay at SAMPLEVILLE GENERAL HOSPITAL (FICTIONAL)"
    assert stay["lines"][0] == "Admitted 10-Aug-2026 → Discharged 13-Aug-2026"
    assert "Diagnosis (as written): Acute gastroenteritis with moderate dehydration" in stay["lines"]
    lab_dates = [e["date"] for e in entries if e["category"] == "lab_results"]
    assert lab_dates == ["2026-08-13", "2026-08-12", "2026-08-11", "2026-08-10"]  # one entry per date, newest first


def test_prescription_lists_its_medicines_and_the_users_confirmation(client, asha):
    read_prescription(client, asha)
    medicines = client.get("/api/v1/medications", headers=asha).json()["items"]
    client.patch(f"/api/v1/medications/{medicines[0]['id']}", headers=asha, json={"status": "active"})

    entry = next(e for e in items(client, asha) if e["category"] == "prescriptions")

    assert (entry["date"], entry["title"]) == ("2026-10-07", "Prescription (Dr. Sample Physician)")
    assert entry["lines"][0] == "Atorvastatin 10 mg — once daily at night (taking, confirmed by you)"
    assert entry["lines"][1] == "Metformin 500 mg — once daily after dinner"


def test_medicines_with_dates_and_medicines_added_by_the_user(client, asha):
    client.post(
        "/api/v1/medications",
        headers=asha,
        json={"name": "Vitamin D3", "start_date": "2026-09-01", "end_date": "2026-10-01"},
    )
    client.post("/api/v1/medications", headers=asha, json={"name": "Calcium"})

    entries = items(client, asha, category="medications")

    assert [(e["date"], e["title"], e["trust"]) for e in entries] == [
        ("2026-10-01", "Stopped Vitamin D3", "added_by_you"),
        ("2026-09-01", "Started Vitamin D3", "added_by_you"),
        (None, "Added Calcium", "added_by_you"),  # no date is never guessed; listed last
    ]
    assert entries[0]["link"] == "/medications"


def test_follow_ups_show_their_status(client, asha):
    document_id = read_prescription(client, asha)
    client.post(f"/api/v1/documents/{document_id}/follow-ups", headers=asha)

    entries = items(client, asha, category="follow_ups")

    assert entries and all(e["trust"] == "added_by_you" and e["link"] == "/follow-ups" for e in entries)
    assert {e["tag"] for e in entries} <= {"Upcoming", "Overdue"}
    assert {"Kidney function test (due)", "doctor visit (due)"} <= {e["title"] for e in entries}


def test_a_document_not_read_yet_is_listed_as_a_document(client, asha):
    upload_report(client, asha, "waiting")

    [entry] = items(client, asha)

    assert (entry["category"], entry["title"], entry["tag"], entry["date"]) == (
        "documents",
        "Document: Synthetic report waiting",
        "Being read",
        None,
    )


def test_filters_by_category_and_date(client, asha):
    read_lab(client, asha)
    read_prescription(client, asha)
    client.post("/api/v1/medications", headers=asha, json={"name": "Calcium"})

    assert [e["category"] for e in items(client, asha, category=["lab_results", "prescriptions"])] == [
        "prescriptions",
        "lab_results",
    ]
    dated = items(client, asha, date_from="2026-10-01", date_to="2026-10-31")
    assert [e["category"] for e in dated] == ["prescriptions"]  # undated entries are left out of a date range
    rejected = client.get(URL, headers=asha, params={"date_from": "2026-10-02", "date_to": "2026-10-01"})
    assert rejected.status_code == 422
    assert client.get(URL, headers=asha, params={"category": "weather"}).status_code == 422


def test_pages(client, asha):
    for name in ("A", "B", "C"):
        client.post("/api/v1/medications", headers=asha, json={"name": name})

    first = timeline(client, asha, limit=2)
    second = timeline(client, asha, limit=2, cursor=first["next_cursor"])

    assert [e["title"] for e in first["items"] + second["items"]] == ["Added A", "Added B", "Added C"]
    assert second["next_cursor"] is None
    assert client.get(URL, headers=asha, params={"cursor": "abc"}).status_code == 422


def test_only_the_users_own_live_records(client, asha):
    document_id = read_lab(client, asha)
    ravi = make_user(client, "ravi@example.com")

    assert items(client, ravi) == []
    assert client.get(URL).status_code == 401

    client.delete(f"/api/v1/documents/{document_id}", headers=asha)
    assert items(client, asha) == []
