"""Record search: free text over the user's records, combined with type, date, condition, and provider filters.

Real test database, fake Groq client (no network, no cost).
"""

import logging

import pytest

from app.core.config import get_settings
from tests.ai_fakes import prescription, response
from tests.test_alerts import LAB
from tests.test_discharge import discharge, upload_discharge
from tests.test_extraction_flow import make_user, run_worker, upload_report
from tests.test_prescription_flow import upload_prescription
from tests.test_reports import imaging, upload

pytestmark = pytest.mark.integration

URL = "/api/v1/search"


@pytest.fixture
def asha(client, db, storage_dir):
    return make_user(client, "asha@example.com")


@pytest.fixture
def records(client, asha):
    settings = get_settings()
    upload_report(client, asha, "lab")
    run_worker(settings, response(LAB))
    upload_prescription(client, asha)
    run_worker(settings, response(prescription()))
    upload_discharge(client, asha)
    run_worker(settings, response(discharge()))
    upload(client, asha, "imaging_report", "mri")
    run_worker(settings, response(imaging()))
    client.post("/api/v1/profile/allergies", headers=asha, json={"name": "Penicillin", "reaction": "Hives"})
    client.post(
        "/api/v1/profile/records", headers=asha, json={"kind": "family", "name": "Stroke", "relation": "Mother"}
    )
    return asha


def search(client, headers, **body):
    found = client.post(URL, headers=headers, json=body)
    assert found.status_code == 200, found.text
    return found.json()


def types(body):
    return sorted({item["record_type"] for item in body["items"]})


def test_free_text_finds_records_of_every_kind(client, records):
    lab = search(client, records, query="hba1c")
    assert types(lab) == ["lab_result"]
    [hit] = lab["items"]
    assert (hit["title"], hit["matched_field"], hit["snippet"]) == ("HbA1c 6.1 %", "Test", "HbA1c")
    assert hit["source_document_title"] == "Synthetic report lab"

    assert "medication" in types(search(client, records, query="atorva"))  # partial words match
    assert "diagnosis" in types(search(client, records, query="gastroenteritis"))
    assert types(search(client, records, query="penicillin hives")) == ["allergy"]  # every word must match
    assert types(search(client, records, query="stroke")) == ["family_history"]


def test_text_of_read_reports_names_the_matched_field(client, records):
    [hit] = search(client, records, query="degenerative disc")["items"]

    assert (hit["record_type"], hit["matched_field"]) == ("report_text", "Impression")
    assert "degenerative disc" in hit["snippet"].casefold()


def test_filters_combine_with_the_query(client, records):
    by_type = search(client, records, query="hemoglobin", document_type="discharge_summary")
    assert by_type["total"] > 0
    assert {i["source_document_title"] for i in by_type["items"]} == {"Synthetic report d"}

    assert search(client, records, query="hemoglobin", document_type="prescription")["total"] == 0

    by_date = search(client, records, query="creatinine", date_from="2026-08-12", date_to="2026-08-12")
    assert [i["date"] for i in by_date["items"]] == ["2026-08-12"]


def test_condition_filter_finds_records_from_documents_with_that_diagnosis(client, records):
    body = search(client, records, condition="kidney injury")

    assert body["total"] > 0
    assert {i["source_document_title"] for i in body["items"]} == {"Synthetic report d"}


def test_pages(client, records):
    first = search(client, records, query="mg", limit=2)
    second = search(client, records, query="mg", limit=2, cursor=first["next_cursor"])

    assert first["total"] > 2 and len(first["items"]) == 2
    assert {i["id"] for i in first["items"]}.isdisjoint({i["id"] for i in second["items"]})


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({}, "query"),
        ({"query": "   "}, "query"),
        ({"query": "x", "date_from": "2026-10-02", "date_to": "2026-10-01"}, "date_to"),
    ],
)
def test_invalid_requests(client, asha, body, field):
    rejected = client.post(URL, headers=asha, json=body)
    assert rejected.status_code == 422
    assert rejected.json()["error"]["details"][0]["field"] == field


def test_only_the_users_own_records_and_the_query_is_not_logged(client, records, caplog):
    ravi = make_user(client, "ravi@example.com")

    with caplog.at_level(logging.DEBUG):
        assert search(client, ravi, query="penicillin")["items"] == []
    assert "penicillin" not in caplog.text.casefold()
    assert client.post(URL, json={"query": "x"}).status_code == 401
