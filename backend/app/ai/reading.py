"""Pipeline stages 2–3: get the document's content ready for extraction (backend_spec.md Section 6.4).

Typed PDFs: use their embedded text (fast, exact, cheaper). Scanned PDFs and photos:
turn them into page images for the model's vision. The original file is never modified.
"""

import io
import logging
from dataclasses import dataclass, field
from typing import Literal

import pypdfium2 as pdfium
from PIL import Image, ImageOps, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError

logger = logging.getLogger(__name__)

# Below this many extracted characters per page on average, treat the PDF as a scan.
MIN_TEXT_CHARS_PER_PAGE = 80
# Scans are read as page images: 3 per request (provider limit), at most this many pages.
MAX_SCANNED_PAGES = 30
# Roughly 100K tokens of text: leaves room in a 131K-token context for instructions and output.
MAX_TEXT_CHARS = 300_000
RENDER_DPI = 150
MAX_IMAGE_EDGE = 2048  # longer side in pixels; finer detail adds no accuracy and costs the same tokens
JPEG_QUALITY = 85


class ReadingError(Exception):
    """The document cannot be prepared for extraction. Permanent: retrying will not help."""

    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category


@dataclass(frozen=True)
class PageImage:
    page_number: int  # 1-based page in the original document
    data: bytes  # JPEG
    media_type: str = "image/jpeg"


@dataclass(frozen=True)
class PreparedDocument:
    mode: Literal["text", "images"]
    page_count: int
    pages: list[str] = field(default_factory=list)  # text mode: one entry per page
    images: list[PageImage] = field(default_factory=list)  # images mode: one entry per page


def _to_jpeg(image: Image.Image) -> bytes:
    image = ImageOps.exif_transpose(image)  # phone photos: respect the camera's rotation
    if image.mode != "RGB":
        image = image.convert("RGB")
    image.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE))  # only ever shrinks, keeps the aspect ratio
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return buffer.getvalue()


def _prepare_photo(content: bytes) -> PreparedDocument:
    try:
        with Image.open(io.BytesIO(content)) as image:
            data = _to_jpeg(image)
    except Image.DecompressionBombError as exc:
        raise ReadingError("image_too_large") from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ReadingError("unreadable_image") from exc
    return PreparedDocument(mode="images", page_count=1, images=[PageImage(page_number=1, data=data)])


def _render_scan(content: bytes, page_count: int) -> PreparedDocument:
    if page_count > MAX_SCANNED_PAGES:
        raise ReadingError("too_many_pages")
    images = []
    try:
        pdf = pdfium.PdfDocument(content)
        try:
            for index in range(len(pdf)):
                page = pdf[index]
                try:
                    bitmap = page.render(scale=RENDER_DPI / 72)
                    images.append(PageImage(page_number=index + 1, data=_to_jpeg(bitmap.to_pil())))
                finally:
                    page.close()
        finally:
            pdf.close()
    except pdfium.PdfiumError as exc:
        raise ReadingError("unreadable_pdf") from exc
    return PreparedDocument(mode="images", page_count=page_count, images=images)


def prepare(content: bytes, media_type: str) -> PreparedDocument:
    if media_type in ("image/jpeg", "image/png"):
        return _prepare_photo(content)
    if media_type != "application/pdf":
        raise ReadingError("unsupported_media_type")

    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ReadingError("pdf_password_protected")
        page_count = len(reader.pages)
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
    except ReadingError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        logger.warning("pdf could not be read", extra={"error_type": type(exc).__name__})
        raise ReadingError("unreadable_pdf") from exc

    if page_count == 0:
        raise ReadingError("unreadable_pdf")

    total_chars = sum(len(text) for text in pages)
    if total_chars / page_count >= MIN_TEXT_CHARS_PER_PAGE:
        if total_chars > MAX_TEXT_CHARS:
            raise ReadingError("document_too_long")
        return PreparedDocument(mode="text", page_count=page_count, pages=pages)
    # Little or no embedded text: a scan. The model reads rendered page images.
    return _render_scan(content, page_count)
