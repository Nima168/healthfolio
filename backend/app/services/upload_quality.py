"""Upload check: is a photo or scanned page clear enough for the AI to read? (and how many pages it has)

Typed PDFs carry their own text, so they are always clear. Photos and scanned pages are measured the way
the reader will see them. Limits were set against the sample reports: every real scan scored at least
386 for sharpness, while the same scans blurred slightly scored 57 or less.
"""

import io
import logging
from dataclasses import dataclass

import pypdfium2 as pdfium
from PIL import Image, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError
from pypdf import PdfReader

from app.ai.reading import MIN_TEXT_CHARS_PER_PAGE, RENDER_DPI

logger = logging.getLogger(__name__)

MIN_SHORT_SIDE = 600  # pixels: smaller photos cannot show printed text clearly
MIN_SHARPNESS = 100  # variance of the Laplacian (edge detail) at MEASURE_EDGE
MIN_CONTRAST = 8  # standard deviation of brightness: below this the page is blank or washed out
MIN_BRIGHTNESS = 50  # mean brightness (0-255): below this the photo is too dark
MEASURE_EDGE = 1600  # measured at a fixed size, so large and small photos are judged alike
MAX_PAGES_CHECKED = 10  # keeps uploads quick; later pages are read as they are

_LAPLACIAN = ImageFilter.Kernel((3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], scale=1, offset=128)

DISCHARGE_ONE_PAGE = (
    "Discharge summaries can be one page only, because of AI reading limits. Please upload just the page "
    "with the diagnosis and discharge medicines."
)

MESSAGES = {
    "too_small": "is too small to read. Please upload a larger photo or the original PDF.",
    "blurry": "looks blurry. Please take a clearer photo in good light, or upload the original PDF.",
    "too_dark": "is too dark to read. Please take the photo in better light.",
    "blank": "looks blank or washed out. Please check the file and upload a clearer copy.",
}


@dataclass(frozen=True)
class QualityReport:
    page_count: int | None  # None when the file cannot be opened here (the reader reports that later)
    problem: str | None = None  # a key of MESSAGES
    page: int | None = None  # 1-based page with the problem, for PDFs

    def message(self) -> str | None:
        if self.problem is None:
            return None
        where = f"Page {self.page}" if self.page else "This image"
        return f"{where} {MESSAGES[self.problem]}"


def measure(image: Image.Image) -> str | None:
    """The first problem found with one photo or page, or None when it looks clear."""
    if min(image.size) < MIN_SHORT_SIDE:
        return "too_small"
    gray = ImageOps.exif_transpose(image).convert("L")
    gray.thumbnail((MEASURE_EDGE, MEASURE_EDGE))
    stats = ImageStat.Stat(gray)
    if stats.mean[0] < MIN_BRIGHTNESS:
        return "too_dark"
    if stats.stddev[0] < MIN_CONTRAST:
        return "blank"
    if ImageStat.Stat(gray.filter(_LAPLACIAN)).var[0] < MIN_SHARPNESS:
        return "blurry"
    return None


def check(content: bytes, media_type: str) -> QualityReport:
    try:
        if media_type == "application/pdf":
            return _check_pdf(content)
        with Image.open(io.BytesIO(content)) as image:
            return QualityReport(page_count=1, problem=measure(image))
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
        return QualityReport(page_count=1)
    except Exception as exc:  # a file this check cannot open is still accepted; reading reports the problem
        logger.info("upload quality check skipped", extra={"error_type": type(exc).__name__})
        return QualityReport(page_count=None)


def _check_pdf(content: bytes) -> QualityReport:
    reader = PdfReader(io.BytesIO(content))
    if reader.is_encrypted and not reader.decrypt(""):
        return QualityReport(page_count=None)
    page_count = len(reader.pages)
    if page_count == 0:
        return QualityReport(page_count=0)
    texts = [(page.extract_text() or "").strip() for page in reader.pages]
    if sum(len(text) for text in texts) / page_count >= MIN_TEXT_CHARS_PER_PAGE:
        return QualityReport(page_count=page_count)  # typed: the text is read directly

    # Only pages without any text layer are measured: typed text is sharp however little of it there is.
    image_pages = [index for index, text in enumerate(texts) if not text][:MAX_PAGES_CHECKED]
    if not image_pages:
        return QualityReport(page_count=page_count)
    pdf = pdfium.PdfDocument(content)
    try:
        for index in image_pages:
            page = pdf[index]
            try:
                problem = measure(page.render(scale=RENDER_DPI / 72).to_pil())
            finally:
                page.close()
            if problem:
                return QualityReport(page_count=page_count, problem=problem, page=index + 1)
    finally:
        pdf.close()
    return QualityReport(page_count=page_count)
