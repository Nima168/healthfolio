"""Digital vs scanned reading: PyMuPDF text, Tesseract OCR, and the vision fallback (no network)."""

from datetime import date

import pytest
from PIL import Image

from app.ai.extractor import SYSTEM_PROMPT, build_requests
from app.ai.reading import OcrError, OcrResult, PageText, _ocr_result, make_ocr, prepare
from app.ai.schema import ExtractionPayload
from app.ai.validation import validate_payload
from app.core.config import get_settings
from tests.ai_fakes import (
    SYNTHETIC_REPORT_LINES,
    payload,
    photo,
    printed_scan,
    result,
    scanned_pdf,
    text_pdf,
)

PDF = "application/pdf"
CLEAR = OcrResult("Haemoglobin    13.8    g/dL    12.0 - 15.5", 92.0)
POOR = OcrResult("H@em0gl  l3.B", 40.0)


class FakeOcr:
    """Replies in order; each reply is an OcrResult or an exception to raise."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = 0

    def read(self, image: Image.Image) -> OcrResult:
        assert image.mode == "L"  # OCR always gets a grayscale page
        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture
def settings():
    get_settings.cache_clear()
    return get_settings()


# ---------- choosing the route ----------


def test_digital_pdf_text_is_copied_by_pymupdf_without_ocr():
    ocr = FakeOcr()
    document = prepare(text_pdf(SYNTHETIC_REPORT_LINES), PDF, "digital", ocr=ocr)

    assert (document.method, document.mode, ocr.calls) == ("digital", "text", 0)
    assert document.texts[0].source == "digital"
    # Sorted reading keeps a table row on one line.
    assert any(line.split()[:2] == ["Haemoglobin", "13.8"] for line in document.pages[0].splitlines())


def test_scanned_choice_reads_with_ocr_even_if_the_pdf_has_text():
    document = prepare(text_pdf(SYNTHETIC_REPORT_LINES), PDF, "scanned", ocr=FakeOcr(CLEAR))

    assert document.method == "ocr"
    assert document.texts == [PageText(1, CLEAR.text, "ocr", 92)]
    assert document.ocr_confidence == 92


def test_digital_choice_without_text_inside_switches_to_ocr():
    document = prepare(scanned_pdf(1), PDF, "digital", ocr=FakeOcr(CLEAR))

    assert (document.method, document.switched_to_ocr) == ("ocr", True)


def test_unknown_copy_type_is_detected_from_the_file():
    assert prepare(text_pdf(SYNTHETIC_REPORT_LINES), PDF, None, ocr=FakeOcr()).method == "digital"
    assert prepare(scanned_pdf(1), PDF, None, ocr=FakeOcr(CLEAR)).method == "ocr"


def test_photos_are_always_read_with_ocr():
    document = prepare(photo(800, 600), "image/png", "digital", ocr=FakeOcr(CLEAR))

    assert (document.method, document.page_count) == ("ocr", 1)


# ---------- vision fallback ----------


def test_a_poor_page_is_retried_with_a_cleaned_image_then_sent_as_an_image():
    ocr = FakeOcr(POOR, POOR)  # first read, then the median-filtered read
    document = prepare(scanned_pdf(1), PDF, "scanned", ocr=ocr)

    assert ocr.calls == 2
    assert (document.method, document.texts, [i.page_number for i in document.images]) == ("vision", [], [1])
    assert document.ocr_confidence is None


def test_the_cleaned_read_is_kept_when_it_is_better():
    better = OcrResult("Triglycerides    182 H    mg/dL", 88.0)
    document = prepare(scanned_pdf(1), PDF, "scanned", ocr=FakeOcr(POOR, better))

    assert document.texts == [PageText(1, better.text, "ocr", 88)]


def test_the_confidence_limit_is_configurable():
    fair = OcrResult("Haemoglobin 13.8 g/dL 12.0 - 15.5", 80.0)
    strict = prepare(scanned_pdf(1), PDF, "scanned", ocr=FakeOcr(fair, fair), min_confidence=85)
    relaxed = prepare(scanned_pdf(1), PDF, "scanned", ocr=FakeOcr(fair), min_confidence=75)

    assert (strict.method, relaxed.method) == ("vision", "ocr")


def test_ocr_failure_falls_back_to_the_page_image():
    document = prepare(scanned_pdf(1), PDF, "scanned", ocr=FakeOcr(OcrError("TesseractError")))

    assert document.method == "vision"


def test_without_an_ocr_engine_scans_are_read_from_images():
    assert prepare(scanned_pdf(2), PDF, "scanned").method == "vision"


def test_mixed_document_sends_text_pages_then_unreadable_pages_as_images(settings):
    ocr = FakeOcr(CLEAR, POOR, POOR, CLEAR)  # page 2 fails twice
    document = prepare(scanned_pdf(3), PDF, "scanned", ocr=ocr)

    assert document.method == "ocr+vision"
    text_request, image_request = build_requests(document, settings)
    text = text_request["messages"][1]["content"]
    assert '<page number="1" source="ocr">' in text and '<page number="3" source="ocr">' in text
    assert '<page number="2"' not in text
    labels = [part["text"] for part in image_request["messages"][1]["content"] if part["type"] == "text"]
    assert labels[0] == "Page 2 of 3:"


def test_digital_pages_are_not_marked_as_ocr(settings):
    [request] = build_requests(prepare(text_pdf(SYNTHETIC_REPORT_LINES), PDF, "digital"), settings)

    assert '<page number="1">' in request["messages"][1]["content"]


def test_prompts_warn_about_ocr_mistakes_and_forbid_corrections():
    assert 'source="ocr"' in SYSTEM_PROMPT
    assert "never correct or guess" in SYSTEM_PROMPT


def test_values_with_unreadable_characters_need_review():
    garbled = result(test_name="LDL / HDL Ratio", value_text="3.8", value_numeric=3.8, reference_range_text="�35")
    [item] = validate_payload(ExtractionPayload.model_validate(payload([garbled])), 1, date(2026, 10, 14))

    assert "unreadable_characters" in item.findings
    assert item.needs_review


# ---------- OCR text layout ----------


def test_ocr_lines_keep_table_columns_apart():
    data = {
        "text": ["Haemoglobin", "13.8", "g/dL", "Next"],
        "conf": ["95", "90", "85", "-1"],
        "block_num": [1, 1, 1, 1],
        "par_num": [1, 1, 1, 1],
        "line_num": [1, 1, 1, 2],
        "left": [10, 400, 470, 10],
        "width": [200, 50, 40, 60],
        "height": [20, 20, 20, 20],
    }
    result = _ocr_result(data)

    assert result.text == "Haemoglobin    13.8 g/dL"  # wide gap kept; "Next" had no confidence (not a word)
    assert result.confidence == 90


# ---------- real Tesseract (skipped when it is not installed) ----------


def test_real_tesseract_reads_aprinted_scan():
    ocr = make_ocr(get_settings().tesseract_cmd)
    if ocr is None:
        pytest.skip("Tesseract OCR is not installed")

    document = prepare(printed_scan(), PDF, "scanned", ocr=ocr)

    assert document.method == "ocr", "a clear printed page should be read by OCR, not sent as an image"
    text = document.pages[0]
    assert "Haemoglobin" in text and "13.8" in text and "250" in text
    assert document.ocr_confidence >= 85
