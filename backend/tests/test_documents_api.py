"""Document API against the real test database and a temporary storage folder (synthetic files only)."""

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.main import create_app
from app.models.auth import AuditEvent
from app.models.document import Document

pytestmark = pytest.mark.integration

URL = "/api/v1/documents"


def synthetic_pdf(label: str = "a") -> bytes:
    return f"%PDF-1.4\n% synthetic test document {label}\n%%EOF\n".encode()


def synthetic_png(label: str = "a") -> bytes:
    return b"\x89PNG\r\n\x1a\n" + label.encode() * 8


def synthetic_jpeg(label: str = "a") -> bytes:
    return b"\xff\xd8\xff\xe0" + label.encode() * 8


def make_user(client, email: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/register", json={"email": email, "password": "a long enough passphrase"})
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def asha(client, db):
    return make_user(client, "asha@example.com")


@pytest.fixture
def ravi(client, db):
    return make_user(client, "ravi@example.com")


def upload(client, headers, content=None, filename="report.pdf", content_type="application/pdf", **fields):
    content = synthetic_pdf() if content is None else content
    fields.setdefault("title", "Blood test March")
    if fields["title"] is None:  # title=None means "leave the field out"
        del fields["title"]
    return client.post(URL, headers=headers, files={"file": (filename, content, content_type)}, data=fields)


def error_code(response):
    return response.json()["error"]["code"]


# ---------- upload ----------


@pytest.mark.parametrize(
    ("content", "filename", "media_type"),
    [
        (synthetic_pdf(), "report.pdf", "application/pdf"),
        (synthetic_png(), "scan.png", "image/png"),
        (synthetic_jpeg(), "photo.jpg", "image/jpeg"),
    ],
)
def test_upload_supported_types(client, asha, storage_dir, content, filename, media_type):
    response = upload(client, asha, content, filename, "application/octet-stream")

    assert response.status_code == 201
    body = response.json()
    assert body["media_type"] == media_type  # from content, not the declared type
    assert body["original_filename"] == filename
    assert body["title"] == "Blood test March"
    assert body["size_bytes"] == len(content)
    assert body["category"] == "unknown"
    assert body["processing_status"] == "pending"
    assert "storage_key" not in body and str(storage_dir) not in response.text
    assert (storage_dir / f"{_user_id(client, asha)}" / body["id"]).read_bytes() == content


def _user_id(client, headers):
    return client.get("/api/v1/users/me", headers=headers).json()["id"]


def test_upload_with_metadata(client, asha):
    response = upload(
        client,
        asha,
        category="lab_report",
        document_date="2026-03-14",
        document_date_precision="month",
        provider_name="  City Diagnostics ",
    )

    body = response.json()
    assert response.status_code == 201
    assert body["category"] == "lab_report"
    assert body["document_date"] == "2026-03-01"  # month precision → first day of the month
    assert body["document_date_precision"] == "month"
    assert body["provider_name"] == "City Diagnostics"


@pytest.mark.parametrize(
    ("title", "issue"),
    [
        (None, "Enter a name for this document."),
        ("", "Enter a name for this document."),
        ("   ", "Enter a name for this document."),
        ("x" * 201, "Name must be at most 200 characters."),
    ],
)
def test_name_is_required(client, asha, storage_dir, title, issue):
    response = upload(client, asha, title=title)

    assert response.status_code == 422
    assert {"field": "title", "issue": issue} in response.json()["error"]["details"]
    assert not any(path.is_file() for path in storage_dir.rglob("*"))


def test_name_is_trimmed(client, asha):
    assert upload(client, asha, title="  HbA1c follow-up  ").json()["title"] == "HbA1c follow-up"


def test_blank_optional_fields_are_ignored(client, asha):
    response = upload(client, asha, category="", document_date="", document_date_precision="", provider_name="")

    assert response.status_code == 201
    assert response.json()["document_date"] is None


def test_disguised_file_is_rejected(client, asha, storage_dir):
    response = upload(client, asha, b"<html><script>alert(1)</script></html>", "report.pdf", "application/pdf")

    assert response.status_code == 415
    assert error_code(response) == "UNSUPPORTED_MEDIA_TYPE"
    assert not any(path.is_file() for path in storage_dir.rglob("*"))


def test_empty_file_is_rejected(client, asha):
    response = upload(client, asha, b"")

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "file"


def test_invalid_metadata_is_rejected(client, asha):
    response = upload(client, asha, category="horoscope", document_date="not-a-date")

    assert response.status_code == 422
    assert {d["field"] for d in response.json()["error"]["details"]} == {"category", "document_date"}


def test_traversal_style_filename_is_sanitised(client, asha):
    response = upload(client, asha, filename="../../etc/passwd.pdf")

    assert response.json()["original_filename"] == "passwd.pdf"


def test_duplicate_upload_points_to_existing_document(client, asha):
    first = upload(client, asha, synthetic_pdf("same"), "one.pdf")
    second = upload(client, asha, synthetic_pdf("same"), "renamed-copy.pdf")

    assert second.status_code == 409
    assert error_code(second) == "DUPLICATE_DOCUMENT"
    assert {"field": "existing_document_id", "issue": first.json()["id"]} in second.json()["error"]["details"]


def test_same_file_for_another_user_is_not_a_duplicate(client, asha, ravi):
    assert upload(client, asha, synthetic_pdf("shared")).status_code == 201
    assert upload(client, ravi, synthetic_pdf("shared")).status_code == 201


def test_upload_requires_login(client, db):
    response = client.post(URL, files={"file": ("a.pdf", synthetic_pdf(), "application/pdf")})

    assert response.status_code == 401


def test_upload_rate_limit(client, asha, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_rate_limit_per_hour", 2)
    assert upload(client, asha, synthetic_pdf("1")).status_code == 201
    assert upload(client, asha, synthetic_pdf("2")).status_code == 201

    limited = upload(client, asha, synthetic_pdf("3"))
    assert limited.status_code == 429


# ---------- size limit (rejected before the body is read) ----------


@pytest.fixture
def small_limit_client(db, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    get_settings.cache_clear()
    with TestClient(create_app(), base_url="https://testserver", raise_server_exceptions=False) as test_client:
        yield test_client
    get_settings.cache_clear()


def test_oversized_upload_rejected_by_content_length(small_limit_client, storage_dir):
    headers = make_user(small_limit_client, "big@example.com")
    too_big = synthetic_pdf() + b"0" * (2 * 1024 * 1024)

    response = upload(small_limit_client, headers, too_big)

    assert response.status_code == 413
    assert error_code(response) == "CONTENT_TOO_LARGE"
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
    assert not any(path.is_file() for path in storage_dir.rglob("*"))


def test_oversized_upload_rejected_without_content_length(small_limit_client):
    headers = make_user(small_limit_client, "chunked@example.com")
    boundary = "testboundary"
    head = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="big.pdf"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
    ).encode()

    def chunked_body():  # a generator body is sent without Content-Length
        yield head + synthetic_pdf()
        for _ in range(40):
            yield b"0" * (64 * 1024)
        yield f"\r\n--{boundary}--\r\n".encode()

    response = small_limit_client.post(
        URL, headers={**headers, "Content-Type": f"multipart/form-data; boundary={boundary}"}, content=chunked_body()
    )
    assert response.status_code == 413


# ---------- list, get, isolation ----------


def test_list_newest_first_with_pagination_and_filter(client, asha):
    ids = [
        upload(client, asha, synthetic_pdf(str(i)), category="lab_report" if i % 2 else "prescription").json()["id"]
        for i in range(5)
    ]

    first = client.get(URL, headers=asha, params={"limit": 2}).json()
    assert [d["id"] for d in first["items"]] == ids[::-1][:2]
    cursor = first["pagination"]["next_cursor"]
    rest = client.get(URL, headers=asha, params={"limit": 10, "cursor": cursor}).json()
    assert [d["id"] for d in rest["items"]] == ids[::-1][2:]
    assert rest["pagination"]["next_cursor"] is None

    labs = client.get(URL, headers=asha, params={"category": "lab_report"}).json()["items"]
    assert {d["category"] for d in labs} == {"lab_report"} and len(labs) == 2


def test_invalid_cursor_is_rejected(client, asha):
    response = client.get(URL, headers=asha, params={"cursor": "not-a-cursor"})

    assert response.status_code == 422


def test_other_users_documents_are_invisible(client, asha, ravi):
    document_id = upload(client, asha).json()["id"]

    assert client.get(URL, headers=ravi).json()["items"] == []
    for method, path, kwargs in [
        ("GET", f"{URL}/{document_id}", {}),
        ("GET", f"{URL}/{document_id}/file", {}),
        ("PATCH", f"{URL}/{document_id}", {"json": {"category": "other"}}),
        ("DELETE", f"{URL}/{document_id}", {}),
    ]:
        response = client.request(method, path, headers=ravi, **kwargs)
        assert response.status_code == 404, f"{method} {path}"

    # Still intact for its owner.
    assert client.get(f"{URL}/{document_id}", headers=asha).json()["category"] == "unknown"


def test_unknown_document_is_404(client, asha):
    assert client.get(f"{URL}/{uuid.uuid4()}", headers=asha).status_code == 404


# ---------- download ----------


def test_download_returns_original_bytes_with_safe_headers(client, asha):
    content = synthetic_png("download")
    document_id = upload(client, asha, content, "Scan – März.png", "image/png").json()["id"]

    inline = client.get(f"{URL}/{document_id}/file", headers=asha)
    attachment = client.get(f"{URL}/{document_id}/file", headers=asha, params={"download": "true"})

    assert inline.content == content
    assert inline.headers["content-type"] == "image/png"
    assert inline.headers["x-content-type-options"] == "nosniff"
    assert inline.headers["cache-control"] == "private, no-store"
    assert inline.headers["content-disposition"].startswith("inline;")
    assert "filename*=UTF-8''Scan%20%E2%80%93%20M%C3%A4rz.png" in inline.headers["content-disposition"]
    assert attachment.headers["content-disposition"].startswith("attachment;")


# ---------- update ----------


def test_patch_metadata(client, asha):
    document_id = upload(client, asha, provider_name="Old Clinic").json()["id"]

    response = client.patch(
        f"{URL}/{document_id}",
        headers=asha,
        json={"category": "discharge_summary", "document_date": "2025-07-20", "document_date_precision": "year"},
    )
    body = response.json()
    assert response.status_code == 200
    assert body["category"] == "discharge_summary"
    assert body["document_date"] == "2025-01-01"
    assert body["provider_name"] == "Old Clinic"  # untouched field kept

    renamed = client.patch(f"{URL}/{document_id}", headers=asha, json={"title": " Discharge, July 2025 "})
    assert renamed.json()["title"] == "Discharge, July 2025"

    cleared = client.patch(f"{URL}/{document_id}", headers=asha, json={"provider_name": None, "document_date": None})
    assert cleared.json()["provider_name"] is None
    assert cleared.json()["document_date_precision"] is None


@pytest.mark.parametrize(
    "body",
    [
        {"category": "horoscope"},
        {"document_date_precision": "month"},  # precision without a date
        {"storage_key": "x"},  # unknown fields are rejected
        {"provider_name": "x" * 201},
        {"title": None},  # the name can be changed but not removed
        {"title": "   "},
    ],
)
def test_patch_validation(client, asha, body):
    document_id = upload(client, asha).json()["id"]

    assert client.patch(f"{URL}/{document_id}", headers=asha, json=body).status_code == 422


# ---------- delete ----------


def test_delete_removes_file_keeps_tombstone_and_allows_reupload(client, asha, db, storage_dir):
    content = synthetic_pdf("delete-me")
    document_id = upload(client, asha, content, "private-name.pdf", provider_name="Clinic").json()["id"]
    stored = next(path for path in storage_dir.rglob(document_id))

    assert client.delete(f"{URL}/{document_id}", headers=asha).status_code == 204

    assert not stored.exists()
    assert client.get(f"{URL}/{document_id}", headers=asha).status_code == 404
    assert client.get(URL, headers=asha).json()["items"] == []

    tombstone = db.scalar(select(Document).where(Document.id == uuid.UUID(document_id)))
    assert tombstone.deleted_at is not None
    for field in ("storage_key", "title", "original_filename", "sha256", "provider_name", "document_date"):
        assert getattr(tombstone, field) is None, field

    assert upload(client, asha, content).status_code == 201  # same file can be uploaded again


# ---------- audit ----------


def test_audit_events_without_file_names(client, asha, db):
    document_id = upload(client, asha, filename="hiv-test-result.pdf", title="HIV test result").json()["id"]
    client.get(f"{URL}/{document_id}/file", headers=asha)
    client.patch(f"{URL}/{document_id}", headers=asha, json={"category": "lab_report"})
    client.delete(f"{URL}/{document_id}", headers=asha)

    events = db.scalars(select(AuditEvent).where(AuditEvent.event_type.like("document.%"))).all()
    assert [e.event_type for e in sorted(events, key=lambda e: e.occurred_at)] == [
        "document.uploaded",
        "document.accessed",
        "document.updated",
        "document.deleted",
    ]
    stored = " ".join(str(e.metadata_json) for e in events)
    assert "hiv-test-result" not in stored and "HIV test result" not in stored


def test_storage_dir_is_isolated_for_tests(storage_dir):
    assert storage_dir.name.startswith("test_documents_")
    assert os.environ["DOCUMENT_STORAGE_DIR"] == str(storage_dir)
