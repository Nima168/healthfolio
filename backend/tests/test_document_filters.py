"""Filtering the documents list by type, report date, and hospital or clinic; the hospital list for the filter."""

import pytest

from tests.ai_fakes import text_pdf
from tests.test_extraction_flow import make_user

pytestmark = pytest.mark.integration

URL = "/api/v1/documents"


@pytest.fixture
def asha(client, db, storage_dir):
    return make_user(client, "asha@example.com")


def upload(client, headers, title, category=None, document_date=None, precision="day", provider=None):
    data = {"title": title}
    if category:
        data["category"] = category
    if document_date:
        data |= {"document_date": document_date, "document_date_precision": precision}
    if provider is not None:
        data["provider_name"] = provider
    response = client.post(
        URL,
        headers=headers,
        files={"file": ("report.pdf", text_pdf([f"SYNTHETIC TEST DATA {title}"]), "application/pdf")},
        data=data,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture
def library(client, asha):
    upload(client, asha, "CBC", "lab_report", "2026-10-07", provider="Apollo Hospitals")
    upload(client, asha, "Lipids", "lab_report", "2026-08-15", provider="apollo  hospitals ")
    upload(client, asha, "Prescription", "prescription", "2026-10-01", provider="SampleCare Clinic")
    upload(client, asha, "Discharge", "discharge_summary", "2025-12-20", provider="Apollo")
    upload(client, asha, "Old scan", "imaging_report", "2024-01-01", precision="year")
    upload(client, asha, "Undated note")
    return asha


def titles(client, headers, **params):
    response = client.get(URL, headers=headers, params=params)
    assert response.status_code == 200, response.text
    return sorted(item["title"] for item in response.json()["items"])


def test_no_filters_lists_everything(client, library):
    assert len(titles(client, library)) == 6


def test_filter_by_type(client, library):
    assert titles(client, library, category="lab_report") == ["CBC", "Lipids"]


def test_filter_by_report_date_range_leaves_out_undated(client, library):
    assert titles(client, library, date_from="2026-08-01", date_to="2026-10-05") == ["Lipids", "Prescription"]
    assert titles(client, library, date_from="2026-01-01") == ["CBC", "Lipids", "Prescription"]
    assert titles(client, library, date_to="2024-12-31") == ["Old scan"]


def test_end_date_before_start_date_is_rejected(client, library):
    response = client.get(URL, headers=library, params={"date_from": "2026-10-01", "date_to": "2026-09-01"})
    assert response.status_code == 422


def test_filter_by_hospital_ignores_case_and_spacing_but_not_spelling(client, library):
    assert titles(client, library, provider="APOLLO HOSPITALS") == ["CBC", "Lipids"]
    assert titles(client, library, provider="Apollo") == ["Discharge"]  # a different name is not merged


def test_filter_documents_without_a_hospital(client, library):
    assert titles(client, library, provider_missing="true") == ["Old scan", "Undated note"]


def test_filters_combine(client, library):
    assert titles(client, library, category="lab_report", provider="Apollo Hospitals", date_from="2026-09-01") == [
        "CBC"
    ]


def test_filtered_pages_continue_with_the_same_filters(client, library):
    first = client.get(URL, headers=library, params={"category": "lab_report", "limit": 1}).json()
    cursor = first["pagination"]["next_cursor"]
    second = client.get(URL, headers=library, params={"category": "lab_report", "limit": 1, "cursor": cursor}).json()
    assert {first["items"][0]["title"], second["items"][0]["title"]} == {"CBC", "Lipids"}
    assert second["pagination"]["next_cursor"] is None


def test_hospital_list_counts_spelling_variants_together(client, library):
    body = client.get(f"{URL}/providers", headers=library).json()

    assert body["items"] == [
        {"name": "Apollo", "document_count": 1},
        {"name": "Apollo Hospitals", "document_count": 2},
        {"name": "SampleCare Clinic", "document_count": 1},
    ]
    assert body["without_provider"] == 2


def test_hospital_list_is_only_the_users_own(client, library):
    ravi = make_user(client, "ravi@example.com")
    upload(client, ravi, "Ravi report", provider="Ravi Clinic")

    assert [p["name"] for p in client.get(f"{URL}/providers", headers=library).json()["items"]] == [
        "Apollo",
        "Apollo Hospitals",
        "SampleCare Clinic",
    ]
    assert titles(client, library, provider="Ravi Clinic") == []
    assert client.get(f"{URL}/providers").status_code == 401


def test_deleted_documents_leave_the_hospital_list(client, asha):
    document_id = upload(client, asha, "Only one", provider="Gone Clinic")
    assert client.delete(f"{URL}/{document_id}", headers=asha).status_code == 204

    assert client.get(f"{URL}/providers", headers=asha).json() == {"items": [], "without_provider": 0}
