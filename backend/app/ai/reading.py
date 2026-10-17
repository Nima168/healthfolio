"""Pipeline stages 2–3: get the document's text ready for the AI (backend_spec.md Section 6.4).

Digital PDFs: PyMuPDF copies the text stored in the file (exact, fast). Scanned PDFs and photos:
Tesseract OCR reads each page image. A page OCR cannot read confidently is passed to the AI as an
image instead (vision fallback), so a poor scan is not silently misread. The original file is never modified.
"""

import io
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

import pymupdf
import pytesseract
from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError

logger = logging.getLogger(__name__)

COPY_TYPES = ("digital", "scanned")
# Below this many characters of embedded text per page on average, a PDF has no usable text layer.
MIN_TEXT_CHARS_PER_PAGE = 80
# Scanned pages are read one by one (OCR, or images 3 per request): at most this many pages.
MAX_SCANNED_PAGES = 30
# Roughly 100K tokens of text: leaves room in a 131K-token context for instructions and output.
MAX_TEXT_CHARS = 300_000
OCR_DPI = 300  # Tesseract reads best at about 300 DPI
OCR_MAX_EDGE = 5000  # very large photos are shrunk first: more pixels only slow OCR down
MIN_OCR_CHARS = 20  # an OCR page with less text than this is treated as unread
MAX_IMAGE_EDGE = 2048  # images for the AI: finer detail adds no accuracy and costs the same tokens
JPEG_QUALITY = 85
WINDOWS_TESSERACT = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")


class ReadingError(Exception):
    """The document cannot be prepared for extraction. Permanent: retrying will not help."""

    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category


@dataclass(frozen=True)
class PageText:
    page_number: int  # 1-based page in the original document
    text: str
    source: Literal["digital", "ocr"]
    confidence: int | None = None  # OCR only: Tesseract's average word confidence, 0–100


@dataclass(frozen=True)
class PageImage:
    page_number: int  # 1-based page in the original document
    data: bytes  # JPEG
    media_type: str = "image/jpeg"


@dataclass(frozen=True)
class PreparedDocument:
    page_count: int
    texts: list[PageText] = field(default_factory=list)  # pages read as text
    images: list[PageImage] = field(default_factory=list)  # pages the AI reads from the image
    switched_to_ocr: bool = False  # chosen as digital, but the PDF had no text inside

    @property
    def mode(self) -> Literal["text", "images", "mixed"]:
        if not self.images:
            return "text"
        return "mixed" if self.texts else "images"

    @property
    def pages(self) -> list[str]:
        return [page.text for page in self.texts]

    @property
    def method(self) -> str:
        """How the document was read: digital, ocr, ocr+vision, or vision."""
        if any(page.source == "digital" for page in self.texts):
            return "digital"
        if self.texts:
            return "ocr+vision" if self.images else "ocr"
        return "vision"

    @property
    def ocr_confidence(self) -> int | None:
        scores = [page.confidence for page in self.texts if page.confidence is not None]
        return round(sum(scores) / len(scores)) if scores else None


# ---------- OCR ----------


@dataclass(frozen=True)
class OcrResult:
    text: str
    confidence: float  # 0–100; 0 when no words were found


class OcrError(Exception):
    """OCR could not run on a page (engine missing or failed)."""


class Ocr(Protocol):
    def read(self, image: Image.Image) -> OcrResult: ...


class TesseractOcr:
    # psm 4: one column of text with lines of varying size, which keeps each table row on one line.
    CONFIG = "--oem 1 --psm 4"

    def __init__(self, command: str) -> None:
        self.command = command

    def read(self, image: Image.Image) -> OcrResult:
        pytesseract.pytesseract.tesseract_cmd = self.command
        try:
            data = pytesseract.image_to_data(image, lang="eng", config=self.CONFIG, output_type=pytesseract.Output.DICT)
        except (pytesseract.TesseractError, pytesseract.TesseractNotFoundError, OSError, RuntimeError) as exc:
            raise OcrError(type(exc).__name__) from exc
        return _ocr_result(data)


def _ocr_result(data: dict) -> OcrResult:
    """Rebuild the lines from Tesseract's words, keeping wide gaps (table columns) visible."""
    lines: dict[tuple[int, int, int], list[tuple[int, int, int, str]]] = {}
    scores = []
    for index, word in enumerate(data["text"]):
        word = word.strip()
        confidence = float(data["conf"][index])
        if not word or confidence < 0:
            continue
        scores.append(confidence)
        key = (data["block_num"][index], data["par_num"][index], data["line_num"][index])
        lines.setdefault(key, []).append((data["left"][index], data["width"][index], data["height"][index], word))
    text_lines = []
    for words in lines.values():
        parts, previous_right = [], None
        for left, width, height, word in words:
            if previous_right is not None:
                parts.append("    " if left - previous_right > height else " ")
            parts.append(word)
            previous_right = left + width
        text_lines.append("".join(parts))
    return OcrResult("\n".join(text_lines), sum(scores) / len(scores) if scores else 0.0)


def make_ocr(command: str | None) -> TesseractOcr | None:
    """Tesseract from the setting, the PATH, or its usual Windows folder; None when it is not installed."""
    found = command or shutil.which("tesseract") or (str(WINDOWS_TESSERACT) if WINDOWS_TESSERACT.exists() else None)
    if not found:
        return None
    pytesseract.pytesseract.tesseract_cmd = found
    try:
        pytesseract.get_tesseract_version()
    except (pytesseract.TesseractNotFoundError, OSError, RuntimeError):
        return None
    return TesseractOcr(found)


def _ocr_page(image: Image.Image, page_number: int, ocr: Ocr, min_confidence: int) -> PageText | PageImage:
    """OCR one page; if it cannot be read confidently, keep it as an image for the AI to read instead."""
    gray = image.convert("L")
    if max(gray.size) > OCR_MAX_EDGE:
        gray.thumbnail((OCR_MAX_EDGE, OCR_MAX_EDGE))
    try:
        best = ocr.read(ImageOps.autocontrast(gray))
        if best.confidence < min_confidence:
            # Specks and scanner noise lower OCR accuracy; a light median filter often helps.
            cleaned = ocr.read(ImageOps.autocontrast(gray.filter(ImageFilter.MedianFilter(3))))
            best = cleaned if cleaned.confidence > best.confidence else best
    except OcrError:
        logger.warning("ocr failed on a page; using the page image", extra={"page": page_number})
        return PageImage(page_number, _to_jpeg(image))
    if best.confidence >= min_confidence and len(best.text.strip()) >= MIN_OCR_CHARS:
        return PageText(page_number, best.text.strip(), "ocr", round(best.confidence))
    return PageImage(page_number, _to_jpeg(image))


# ---------- images ----------


def _to_jpeg(image: Image.Image) -> bytes:
    if image.mode != "RGB":
        image = image.convert("RGB")
    image = image.copy()
    image.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE))  # only ever shrinks, keeps the aspect ratio
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return buffer.getvalue()


def _read_pages(pages: list[tuple[int, Image.Image]], ocr: Ocr | None, min_confidence: int):
    texts, images = [], []
    for number, image in pages:
        page = _ocr_page(image, number, ocr, min_confidence) if ocr else PageImage(number, _to_jpeg(image))
        (texts if isinstance(page, PageText) else images).append(page)
    return texts, images


def _prepare_photo(content: bytes, ocr: Ocr | None, min_confidence: int) -> PreparedDocument:
    try:
        with Image.open(io.BytesIO(content)) as opened:
            image = ImageOps.exif_transpose(opened)  # phone photos: respect the camera's rotation
            image.load()
    except Image.DecompressionBombError as exc:
        raise ReadingError("image_too_large") from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ReadingError("unreadable_image") from exc
    texts, images = _read_pages([(1, image)], ocr, min_confidence)
    return PreparedDocument(page_count=1, texts=texts, images=images)


def _scan_pages(pdf: pymupdf.Document) -> list[tuple[int, Image.Image]]:
    pages = []
    for index, page in enumerate(pdf):
        pixmap = page.get_pixmap(dpi=OCR_DPI)
        pages.append((index + 1, Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)))
    return pages


def _horizontal(line: dict) -> bool:
    dx, dy = line["dir"]
    return dx > 0 and abs(dy) < 0.01


def page_text(page: pymupdf.Page) -> str:
    """A digital page's text, top to bottom, with each table row on one line.

    Rotated text is left out: a diagonal watermark ("SYNTHETIC TEST DATA", "SAMPLE") crosses the table, and
    reading it with the page would glue its letters onto values ("DATA1.50 – 4.10"). Pages without rotated
    text are read exactly as before (decision 2026-10-17).
    """
    lines = [line for block in page.get_text("dict")["blocks"] for line in block.get("lines", [])]
    if all(_horizontal(line) for line in lines):
        # sort=True follows the page from top to bottom, so a table row stays on one line.
        return page.get_text("text", sort=True).strip()

    spans = [span for line in lines if _horizontal(line) for span in line["spans"] if span["text"].strip()]
    # Spans whose baselines are within half a line of each other form one row, as on the printed page.
    rows: list[list[dict]] = []
    for span in sorted(spans, key=lambda s: (s["origin"][1], s["origin"][0])):
        if rows and abs(span["origin"][1] - rows[-1][0]["origin"][1]) <= span["size"] * 0.5:
            rows[-1].append(span)
        else:
            rows.append([span])
    text_rows = []
    for row in rows:
        row.sort(key=lambda s: s["bbox"][0])
        text, right = "", None
        for span in row:
            if right is not None:
                gap = span["bbox"][0] - right
                text += " " * max(1, round(gap / max(span["size"] * 0.5, 1)))  # column gaps kept as spaces
            text += span["text"]
            right = span["bbox"][2]
        text_rows.append(text.rstrip())
    return "\n".join(text_rows).strip()


def prepare(
    content: bytes,
    media_type: str,
    copy_type: str | None = None,
    *,
    ocr: Ocr | None = None,
    min_confidence: int = 85,
) -> PreparedDocument:
    """Text for the AI. copy_type is the user's choice ("digital" or "scanned"); None detects it.

    Without an OCR engine, scanned pages go to the AI as images (the vision reading).
    """
    if media_type in ("image/jpeg", "image/png"):
        return _prepare_photo(content, ocr, min_confidence)  # a photo is always a scanned copy
    if media_type != "application/pdf":
        raise ReadingError("unsupported_media_type")

    try:
        pdf = pymupdf.open(stream=content, filetype="pdf")
    except (pymupdf.FileDataError, RuntimeError, ValueError) as exc:
        logger.warning("pdf could not be read", extra={"error_type": type(exc).__name__})
        raise ReadingError("unreadable_pdf") from exc
    try:
        if pdf.needs_pass and not pdf.authenticate(""):
            raise ReadingError("pdf_password_protected")
        page_count = pdf.page_count
        if page_count == 0:
            raise ReadingError("unreadable_pdf")

        if copy_type != "scanned":
            stored = [page_text(page) for page in pdf]
            total_chars = sum(len(text) for text in stored)
            if total_chars / page_count >= MIN_TEXT_CHARS_PER_PAGE:
                if total_chars > MAX_TEXT_CHARS:
                    raise ReadingError("document_too_long")
                texts = [PageText(n, text, "digital") for n, text in enumerate(stored, start=1)]
                return PreparedDocument(page_count=page_count, texts=texts)

        # Scanned (chosen, or no text inside): read the page images.
        if page_count > MAX_SCANNED_PAGES:
            raise ReadingError("too_many_pages")
        texts, images = _read_pages(_scan_pages(pdf), ocr, min_confidence)
    except (pymupdf.FileDataError, RuntimeError) as exc:
        raise ReadingError("unreadable_pdf") from exc
    finally:
        pdf.close()
    return PreparedDocument(page_count=page_count, texts=texts, images=images, switched_to_ocr=copy_type == "digital")
