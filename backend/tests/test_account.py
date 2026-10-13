"""Account and privacy: exports, change password, and account deletion (synthetic data, temporary storage)."""

import csv
import io
import json
import zipfile

import pytest
from pypdf import PdfReader
from sqlalchemy import func, select

from app.core.config import get_settings
from app.models.auth import AuditEvent, User
from app.services.account_service import owned_models
from tests.ai_fakes import payload, response, result
from tests.test_extraction_flow import run_worker, upload_report

pytestmark = pytest.mark.integration

CSRF = {"X-CSRF-Protection": "1", "Origin": "http://localhost:5173"}
PASSWORD = "a long enough passphrase"
HBA1C = result(
    test_name="HbA1c",
    value_text="6.1",
    value_numeric=6.1,
    unit="%",
    reference_range_text="4.0 - 5.6",
    reference_low=4.0,
    reference_high=5.6,
    source_text="HbA1c 6.1 % 4.0 - 5.6",
)


def register(client, email):
    """Returns the access-token header; the refresh cookie stays in the client's cookie jar."""
    body = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD}).json()
    return {"Authorization": f"Bearer {body['access_token']}"}


@pytest.fixture
def asha(client, db, storage_dir):
    return register(client, "asha@example.com")


def fill_records(client, headers, label="1"):
    """A read lab report (with an out-of-range result, so an alert), a medicine, an allergy, a vital, a surgery."""
    document_id = upload_report(client, headers, label)
    run_worker(get_settings(), response(payload([result(), HBA1C])))
    client.post("/api/v1/medications", headers=headers, json={"name": "Vitamin D3", "strength": "1000 IU"})
    client.post("/api/v1/profile/allergies", headers=headers, json={"name": "Penicillin", "category": "drug"})
    client.patch("/api/v1/profile/values", headers=headers, json={"height": "162", "weight": "60"})
    client.post("/api/v1/vitals", headers=headers, json={"measured_on": "2026-10-10", "systolic": 128, "diastolic": 82})
    client.post("/api/v1/profile/records", headers=headers, json={"kind": "surgery", "name": "Appendectomy"})
    return document_id


# ---------- exports ----------


def test_json_export_has_every_kind_of_record_and_nothing_internal(client, asha):
    fill_records(client, asha)
    ravi = register(client, "ravi@example.com")
    client.post("/api/v1/medications", headers=ravi, json={"name": "Someone else's medicine"})

    exported = client.get("/api/v1/account/export/json", headers=asha)

    assert exported.status_code == 200
    assert exported.headers["content-type"] == "application/json"
    assert exported.headers["cache-control"] == "private, no-store"
    assert exported.headers["content-disposition"].startswith('attachment; filename="health-data-')
    data = exported.json()
    assert data["account"]["email"] == "asha@example.com"
    records = data["records"]
    assert [r["title"] for r in records["documents"]] == ["Synthetic report 1"]
    assert {r["name"] for r in records["lab_results"]} == {"Haemoglobin", "HbA1c"}
    assert [r["name"] for r in records["medications"]] == ["Vitamin D3"]  # not Ravi's
    assert records["alerts"] and records["alert_events"]
    assert {r["field"] for r in records["profile_values"]} >= {"allergy", "height", "weight"}
    assert records["vital_readings"][0]["systolic"] == 128
    assert records["medical_records"][0]["name"] == "Appendectomy"
    text = exported.text
    for internal in ("password_hash", "storage_key", "user_id", "idempotency_key"):
        assert internal not in text


def test_deleted_documents_and_their_results_are_not_exported(client, asha):
    document_id = fill_records(client, asha)
    client.delete(f"/api/v1/documents/{document_id}", headers=asha)

    records = client.get("/api/v1/account/export/json", headers=asha).json()["records"]

    assert records["documents"] == [] and records["lab_results"] == []


def test_csv_export_is_a_zip_of_one_file_per_record_type(client, asha):
    fill_records(client, asha)

    exported = client.get("/api/v1/account/export/csv", headers=asha)

    assert exported.headers["content-type"] == "application/zip"
    archive = zipfile.ZipFile(io.BytesIO(exported.content))
    assert {"documents.csv", "lab_results.csv", "medications.csv", "alerts.csv"} <= set(archive.namelist())
    rows = list(csv.DictReader(io.StringIO(archive.read("lab_results.csv").decode("utf-8-sig"))))
    assert {row["name"] for row in rows} == {"Haemoglobin", "HbA1c"}
    # Nested values are written as JSON text, so they survive a spreadsheet round trip.
    alert = next(csv.DictReader(io.StringIO(archive.read("alerts.csv").decode("utf-8-sig"))))
    assert isinstance(json.loads(alert["input_refs"]), dict)


def test_documents_export_contains_the_original_files(client, asha):
    fill_records(client, asha, "1")
    upload_report(client, asha, "2")
    originals = {d["title"]: d for d in client.get("/api/v1/documents", headers=asha).json()["items"]}

    exported = client.get("/api/v1/account/export/documents", headers=asha)

    archive = zipfile.ZipFile(io.BytesIO(exported.content))
    names = sorted(archive.namelist())
    assert names == ["undated Synthetic report 1.pdf", "undated Synthetic report 2.pdf"]
    original = client.get(f"/api/v1/documents/{originals['Synthetic report 1']['id']}/file", headers=asha).content
    assert archive.read("undated Synthetic report 1.pdf") == original


def test_pdf_health_summary(client, asha):
    fill_records(client, asha)

    exported = client.get("/api/v1/account/export/pdf", headers=asha)

    assert exported.headers["content-type"] == "application/pdf"
    pages = PdfReader(io.BytesIO(exported.content)).pages
    text = " ".join(" ".join(page.extract_text().split()) for page in pages)  # line breaks do not matter
    for expected in ("Health Summary", "Penicillin (drug)", "Height: 162 cm", "HbA1c 6.1 % (high; range 4.0 - 5.6)",
                     "Appendectomy", "BP 128/82 mmHg", "Synthetic report 1", "Not medical advice"):  # fmt: skip
        assert expected in text, expected
    assert "Date of birth: Not mentioned" in text  # missing values are not filled in


def test_exports_need_sign_in_and_are_audited(client, asha, db):
    assert client.get("/api/v1/account/export/json").status_code == 401
    client.get("/api/v1/account/export/pdf", headers=asha)
    event = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "account.exported")).one()
    assert event.metadata_json == {"format": "pdf"}


# ---------- change password ----------


def test_change_password_keeps_this_session_and_signs_out_others(client, asha):
    this_cookie = client.cookies.get("refresh_token")  # from registering: this device
    other_device = client.post("/api/v1/auth/login", json={"email": "asha@example.com", "password": PASSWORD})
    other_cookie = other_device.cookies["refresh_token"]
    assert other_cookie != this_cookie

    def change(current, new):
        return client.post(
            "/api/v1/auth/password/change",
            headers={**asha, **CSRF, "Cookie": f"refresh_token={this_cookie}"},
            json={"current_password": current, "new_password": new},
        )

    wrong = change("not my password", "a brand new passphrase")
    assert wrong.status_code == 422
    assert wrong.json()["error"]["details"] == [{"field": "current_password", "issue": "This password is not correct."}]
    assert change(PASSWORD, "short").json()["error"]["details"][0]["field"] == "new_password"
    assert change(PASSWORD, "a brand new passphrase").status_code == 204

    refresh = lambda cookie: client.post(  # noqa: E731
        "/api/v1/auth/refresh", headers={**CSRF, "Cookie": f"refresh_token={cookie}"}
    )
    client.cookies.clear()
    assert refresh(other_cookie).status_code == 401  # the other device is signed out
    assert refresh(this_cookie).status_code == 200  # this one is not
    login = client.post("/api/v1/auth/login", json={"email": "asha@example.com", "password": "a brand new passphrase"})
    assert login.status_code == 200
    assert (
        client.post("/api/v1/auth/login", json={"email": "asha@example.com", "password": PASSWORD}).status_code == 401
    )


def test_change_password_needs_the_csrf_header(client, asha):
    body = {"current_password": PASSWORD, "new_password": "a brand new passphrase"}
    assert client.post("/api/v1/auth/password/change", headers=asha, json=body).status_code == 403


# ---------- delete account ----------


def delete(client, headers, password=PASSWORD, confirmation="DELETE"):
    return client.post(
        "/api/v1/auth/account/delete",
        headers={**headers, **CSRF},
        json={"password": password, "confirmation": confirmation},
    )


def count_rows(db, user_id):
    db.expire_all()
    return {
        model.__tablename__: db.scalar(select(func.count()).select_from(model).where(model.user_id == user_id))
        for model in owned_models()
    }


def test_account_deletion_needs_the_password_and_the_word_delete(client, asha, db, storage_dir):
    fill_records(client, asha)

    assert delete(client, asha, confirmation="delete please").json()["error"]["details"][0]["field"] == "confirmation"
    assert delete(client, asha, password="wrong password").json()["error"]["details"][0]["field"] == "current_password"

    assert db.scalar(select(func.count()).select_from(User)) == 1  # nothing was deleted
    assert any(storage_dir.rglob("*"))


def test_account_deletion_removes_every_record_and_file(client, asha, db, storage_dir):
    fill_records(client, asha)
    ravi = register(client, "ravi@example.com")
    client.post("/api/v1/medications", headers=ravi, json={"name": "Ravi's medicine"})
    user_id = db.scalars(select(User.id).where(User.email == "asha@example.com")).one()
    assert sum(count_rows(db, user_id).values()) > 10

    deleted = delete(client, asha)

    assert deleted.status_code == 204
    assert "refresh_token=" in deleted.headers["set-cookie"]  # the cookie is cleared
    assert count_rows(db, user_id) == {name: 0 for name in count_rows(db, user_id)}
    assert db.get(User, user_id) is None
    assert [p for p in storage_dir.rglob("*") if p.is_file()] == []  # every file removed
    # The audit trail stays for its retention period, detached and without personal content.
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.user_id == user_id)) == 0
    event = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "account.deleted")).one()
    assert event.user_id is None and "asha" not in json.dumps(event.metadata_json)
    # Signed out everywhere, other users untouched, and the email can be used again.
    assert client.get("/api/v1/users/me", headers=asha).status_code == 401
    assert [m["name"] for m in client.get("/api/v1/medications", headers=ravi).json()["items"]] == ["Ravi's medicine"]
    assert (
        client.post("/api/v1/auth/register", json={"email": "asha@example.com", "password": PASSWORD}).status_code
        == 201
    )
