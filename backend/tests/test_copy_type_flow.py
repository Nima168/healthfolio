"""Copy type (digital or scanned) from upload to reading, and "Refresh analysis" (real test database)."""

import pytest
from sqlalchemy import select

from app.ai.extractor import GroqExtractor
from app.ai.reading import OcrResult
from app.core.config import get_settings
from app.models.auth import AuditEvent
from app.worker import Worker
from tests.ai_fakes import SYNTHETIC_REPORT_LINES, FakeGroq, payload, printed_scan, response, text_pdf

pytestmark = pytest.mark.integration

PNG = b"\x89PNG\r\n\x1a\n" + b"synthetic" * 8  # not a real image: the quality check lets it pass


class ClearOcr:
    def read(self, image):
        return OcrResult("Haemoglobin    13.8    g/dL    12.0 - 15.5", 91.0)


@pytest.fixture
def asha(client, db, storage_dir):
    token = client.post(
        "/api/v1/auth/register", json={"email": "asha@example.com", "password": "a long enough passphrase"}
    )
    return {"Authorization": f"Bearer {token.json()['access_token']}"}


def upload(client, headers, content, filename="report.pdf", media_type="application/pdf", **fields):
    data = {"title": "Synthetic report", "category": "lab_report"} | fields
    reply = client.post(
        "/api/v1/documents", headers=headers, files={"file": (filename, content, media_type)}, data=data
    )
    assert reply.status_code == 201, reply.text
    return reply.json()


def run_worker(*replies, ocr=None):
    settings = get_settings()
    fake = FakeGroq(*replies)
    Worker(settings, GroqExtractor(fake, settings), ocr).run(once=True)
    return fake


def extraction(client, headers, document_id):
    return client.get(f"/api/v1/documents/{document_id}/observations", headers=headers).json()


def test_upload_records_the_copy_type(client, asha):
    digital = upload(client, asha, text_pdf(SYNTHETIC_REPORT_LINES), copy_type="digital")
    unanswered = upload(client, asha, text_pdf(["Another synthetic report", *SYNTHETIC_REPORT_LINES]))

    assert (digital["copy_type"], unanswered["copy_type"]) == ("digital", None)


def test_a_photo_is_always_a_scanned_copy(client, asha):
    document = upload(client, asha, PNG, "photo.png", "image/png", copy_type="digital")

    assert document["copy_type"] == "scanned"


def test_an_unknown_copy_type_is_refused(client, asha):
    reply = client.post(
        "/api/v1/documents",
        headers=asha,
        files={"file": ("report.pdf", text_pdf(SYNTHETIC_REPORT_LINES), "application/pdf")},
        data={"title": "Synthetic report", "copy_type": "photocopy"},
    )

    assert reply.status_code == 422


def test_scanned_copy_is_read_with_ocr_and_the_method_is_shown(client, asha):
    document = upload(client, asha, printed_scan(), copy_type="scanned")

    fake = run_worker(response(payload()), ocr=ClearOcr())

    body = extraction(client, asha, document["id"])
    assert (body["copy_type"], body["media_type"]) == ("scanned", "application/pdf")
    assert (body["job"]["reading_method"], body["job"]["ocr_confidence"]) == ("ocr", 91)
    sent = fake.requests[0]["messages"][1]["content"]
    assert isinstance(sent, str) and 'source="ocr"' in sent  # text, not an image


def test_refresh_analysis_can_switch_a_pdf_to_the_other_copy_type(client, asha, db):
    document = upload(client, asha, text_pdf(SYNTHETIC_REPORT_LINES), copy_type="digital")
    run_worker(response(payload()), ocr=ClearOcr())
    assert extraction(client, asha, document["id"])["job"]["reading_method"] == "digital"

    reply = client.post(f"/api/v1/documents/{document['id']}/extract", headers=asha, json={"copy_type": "scanned"})

    assert reply.status_code == 202
    assert reply.json()["copy_type"] == "scanned"
    run_worker(response(payload()), ocr=ClearOcr())
    assert extraction(client, asha, document["id"])["job"]["reading_method"] == "ocr"
    db.expire_all()
    audit = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "ai.extraction_requested")).all()
    assert max(audit, key=lambda e: e.occurred_at).metadata_json["copy_type"] == "scanned"


def test_refresh_analysis_without_a_body_keeps_the_copy_type(client, asha):
    document = upload(client, asha, text_pdf(SYNTHETIC_REPORT_LINES), copy_type="digital")
    run_worker(response(payload()))

    reply = client.post(f"/api/v1/documents/{document['id']}/extract", headers=asha)

    assert (reply.status_code, reply.json()["copy_type"]) == (202, "digital")


def test_a_photo_cannot_be_switched_to_digital(client, asha):
    document = upload(client, asha, PNG, "photo.png", "image/png")
    run_worker(response(payload()))

    reply = client.post(f"/api/v1/documents/{document['id']}/extract", headers=asha, json={"copy_type": "digital"})

    assert reply.json()["copy_type"] == "scanned"
