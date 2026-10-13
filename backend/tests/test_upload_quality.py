"""Upload checks: unclear photos and scans are sent back, and discharge summaries are one page (synthetic files)."""

import io

import pytest
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.core.config import get_settings
from app.services import upload_quality
from tests.ai_fakes import response, text_pdf
from tests.test_extraction_flow import all_jobs, extraction, make_user, run_worker


def page(width: int = 1240, height: int = 1754, *, blur: float = 0, background: int = 255, ink: int = 0) -> Image.Image:
    """A synthetic printed page: lines of text, like a lab report."""
    image = Image.new("L", (width, height), background)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=26)
    for row, y in enumerate(range(80, height - 80, 44)):
        draw.text((70, y), f"Synthetic test {row:02d}     13.{row % 10} g/dL     12.0 - 15.5", fill=ink, font=font)
    return image.filter(ImageFilter.GaussianBlur(blur)) if blur else image


def encode(image: Image.Image, fmt: str = "PNG") -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def scanned(*images: Image.Image) -> bytes:
    """A PDF made only of page images, like a scan."""
    buffer = io.BytesIO()
    first, *rest = [image.convert("RGB") for image in images]
    first.save(buffer, format="PDF", save_all=True, append_images=rest, resolution=150)
    return buffer.getvalue()


# ---------- measuring ----------


def test_a_clear_page_passes():
    assert upload_quality.measure(page()) is None


@pytest.mark.parametrize(
    ("image", "problem"),
    [
        (page(blur=2), "blurry"),
        (page(500, 700), "too_small"),
        (page(background=30, ink=60), "too_dark"),
        (Image.new("L", (1240, 1754), 250), "blank"),
    ],
)
def test_unclear_pages_are_named(image, problem):
    assert upload_quality.measure(image) == problem


def test_typed_pdfs_are_not_measured():
    typed = text_pdf(["Haemoglobin 13.8 g/dL 12.0 - 15.5"] * 5, ["Page two"] * 5)
    report = upload_quality.check(typed, "application/pdf")
    assert (report.page_count, report.problem) == (2, None)
    # Typed text is sharp however little there is: a page with one short line is not "blank".
    short = upload_quality.check(text_pdf(["Synthetic"]), "application/pdf")
    assert (short.page_count, short.problem) == (1, None)


def test_the_unclear_page_of_a_scan_is_named():
    report = upload_quality.check(scanned(page(), page(blur=2)), "application/pdf")
    assert (report.page_count, report.problem, report.page) == (2, "blurry", 2)
    assert report.message().startswith("Page 2 looks blurry.")


def test_files_that_cannot_be_opened_are_left_to_the_reader():
    assert upload_quality.check(b"\x89PNG\r\n\x1a\nnot an image", "image/png").problem is None
    assert upload_quality.check(b"%PDF-1.4\nnot a pdf", "application/pdf").problem is None


# ---------- upload ----------


@pytest.fixture
def asha(client, db, storage_dir):
    return make_user(client, "asha@example.com")


def upload(client, headers, content, filename="scan.png", category=None):
    data = {"title": "Synthetic"} | ({"category": category} if category else {})
    return client.post(
        "/api/v1/documents", headers=headers, files={"file": (filename, content, "image/png")}, data=data
    )


@pytest.mark.integration
def test_a_blurry_photo_is_sent_back(client, asha, db):
    rejected = upload(client, asha, encode(page(blur=2)))

    assert rejected.status_code == 422
    [detail] = rejected.json()["error"]["details"]
    assert detail == {
        "field": "file",
        "issue": "This image looks blurry. Please take a clearer photo in good light, or upload the original PDF.",
    }
    assert all_jobs(db) == []  # nothing stored or queued
    assert upload(client, asha, encode(page(), "JPEG"), "photo.jpg").status_code == 201


@pytest.mark.integration
def test_discharge_summaries_are_one_page(client, asha, db):
    two_pages = text_pdf(["DISCHARGE SUMMARY", "Synthetic"] * 10, ["Page two"] * 20)

    rejected = upload(client, asha, two_pages, "discharge.pdf", category="discharge_summary")
    assert rejected.status_code == 422
    assert "one page only" in rejected.json()["error"]["details"][0]["issue"]

    one_page = text_pdf(["DISCHARGE SUMMARY", "Synthetic"] * 10)
    assert upload(client, asha, one_page, "discharge.pdf", category="discharge_summary").status_code == 201
    # Other types may have several pages.
    assert upload(client, asha, two_pages, "report.pdf", category="lab_report").status_code == 201


@pytest.mark.integration
def test_a_long_document_found_to_be_a_discharge_summary_is_not_read(client, asha, db):
    document = upload(client, asha, text_pdf(["Synthetic"] * 20, ["Page two"] * 20), "notes.pdf").json()

    _, fake = run_worker(get_settings(), response({"document_type": "discharge_summary"}))

    assert len(fake.requests) == 1  # classified only: the summary was never requested
    job = extraction(client, asha, document["id"])["job"]
    assert (job["status"], job["error_category"]) == ("failed", "discharge_too_many_pages")
