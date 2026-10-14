"""Turn a Case into files: a digital PDF (with a text layer) and scanned copies at three damage levels.

The exact printed text is kept beside each document, so OCR can be compared with it.
"""

import io
import random
from dataclasses import dataclass

import pymupdf
from fpdf import FPDF
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from evaluation.cases import Case

DISCLAIMER = "SYNTHETIC TEST DATA - FICTIONAL PATIENT - NOT A REAL MEDICAL RECORD"


@dataclass(frozen=True)
class ScanLevel:
    name: str
    dpi: int
    rotate: float
    blur: float
    noise: float
    contrast: float
    shadow: float
    jpeg_quality: int


SCAN_LEVELS = {
    "scan_clean": ScanLevel("scan_clean", 200, 0.0, 0.0, 4, 0.95, 0.0, 85),
    "scan_medium": ScanLevel("scan_medium", 170, 1.0, 0.7, 12, 0.85, 0.15, 65),
    "scan_hard": ScanLevel("scan_hard", 130, 2.2, 1.2, 22, 0.7, 0.35, 45),
}
VARIANTS = ("digital", *SCAN_LEVELS)


class _Doc(FPDF):
    def __init__(self) -> None:
        super().__init__(format="A4")
        self.set_margins(16, 16, 16)
        self.set_auto_page_break(auto=False)
        self.lines: list[str] = []  # the text as printed, in reading order

    def write_line(self, text: str, *, size: float = 10, bold: bool = False, gap: float = 5.4) -> None:
        self.set_font("Helvetica", "B" if bold else "", size)
        self.cell(0, gap, text, new_x="LMARGIN", new_y="NEXT")
        self.lines.append(text)

    def row(self, cells: list[str], widths: list[float], *, bold: bool = False) -> None:
        self.set_font("Helvetica", "B" if bold else "", 9.5)
        for text, width in zip(cells, widths, strict=True):
            self.cell(width, 6.2, text)
        self.ln(6.2)
        self.lines.append(" ".join(text for text in cells if text))


def _header(pdf: _Doc, case: Case, page: int, pages: int) -> None:
    pdf.add_page()
    pdf.write_line(case.facility.upper(), size=14, bold=True, gap=7)
    pdf.write_line(DISCLAIMER, size=8)
    pdf.ln(2)
    pdf.write_line(case.title, size=12, bold=True, gap=7)
    pdf.write_line("Patient: Test Person (Fictional)    Age/Sex: 52 Y / Female    ID: SYN-0042")
    if case.kind == "discharge_summary":
        pdf.write_line(f"Date of Admission: {case.admitted.strftime('%d-%b-%Y')}")
        pdf.write_line(f"Date of Discharge: {case.date_text}")
    elif case.kind == "imaging_report":
        pdf.write_line(f"Date of Examination: {case.date_text}")
    else:
        pdf.write_line(f"Date: {case.date_text}")
    if case.clinician:
        pdf.write_line(f"Doctor: {case.clinician}")
    if pages > 1:
        pdf.write_line(f"Page {page} of {pages}", size=8)
    pdf.ln(3)


def _labs(pdf: _Doc, case: Case, items) -> None:
    if case.layout == "table":
        widths = [70, 32, 12, 28, 36]
        pdf.row(["Test", "Result", "Flag", "Unit", "Reference Range"], widths, bold=True)
        for item in items:
            pdf.row([item.name, item.value, item.flag, item.unit or "", item.range_text or ""], widths)
    else:
        for item in items:
            unit = f" {item.unit}" if item.unit else ""
            ref = f" (Ref: {item.range_text})" if item.range_text else ""
            pdf.write_line(f"{item.name}: {item.value}{unit}{ref}")


def _bullets(pdf: _Doc, heading: str, items: list[str]) -> None:
    pdf.ln(1.5)
    pdf.write_line(f"{heading}:", bold=True)
    for item in items:
        pdf.write_line(f"- {item}")


def _medicines(pdf: _Doc, case: Case, heading: str) -> None:
    pdf.ln(1.5)
    pdf.write_line(heading, bold=True)
    for number, m in enumerate(case.medicines, start=1):
        pdf.write_line(f"{number}. {m.name} {m.strength} - {m.instructions} - {m.duration}")


def _follow_ups(pdf: _Doc, case: Case) -> None:
    pdf.ln(1.5)
    pdf.write_line("Follow-up:", bold=True)
    for f in case.follow_ups:
        pdf.write_line(f"{f.description} {f.timing}.")


def digital_pdf(case: Case) -> tuple[bytes, str]:
    """The document as a typed PDF, and its printed text."""
    pdf = _Doc()
    if case.kind == "lab_report":
        per_page = (len(case.labs) + case.pages - 1) // case.pages
        for page in range(case.pages):
            _header(pdf, case, page + 1, case.pages)
            _labs(pdf, case, case.labs[page * per_page : (page + 1) * per_page])
            if page == case.pages - 1 and case.trap:
                pdf.ln(2)
                pdf.write_line(case.trap, size=9)
    else:
        _header(pdf, case, 1, 1)
        if case.kind == "prescription":
            pdf.write_line("Rx", size=13, bold=True, gap=7)
            _medicines(pdf, case, "Medicines:")
            _follow_ups(pdf, case)
        elif case.kind == "discharge_summary":
            _bullets(pdf, "Final Diagnosis", case.diagnoses)
            pdf.ln(1.5)
            pdf.write_line(f"Investigations ({case.doc_date.strftime('%d-%b-%Y')}):", bold=True)
            _labs(pdf, case, case.labs)
            _medicines(pdf, case, "Discharge Medications:")
            _follow_ups(pdf, case)
            pdf.ln(1.5)
            pdf.write_line("Return to the emergency department if fever, vomiting or breathlessness worsens.")
        elif case.kind == "consultation_note":
            _bullets(pdf, "Symptoms", case.lists["symptoms"])
            _bullets(pdf, "Assessment", case.lists["assessment"])
            _bullets(pdf, "Plan", case.lists["plan"])
        elif case.kind == "imaging_report":
            _bullets(pdf, "Findings", case.lists["findings"])
            _bullets(pdf, "Impression", case.lists["impression"])
    return bytes(pdf.output()), "\n".join(pdf.lines)


def _degrade(image: Image.Image, level: ScanLevel, rng: random.Random) -> Image.Image:
    image = image.convert("L")
    if level.rotate:
        angle = level.rotate * rng.choice([-1, 1])
        image = image.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=255)
    if level.blur:
        image = image.filter(ImageFilter.GaussianBlur(level.blur))
    image = ImageEnhance.Contrast(image).enhance(level.contrast)
    if level.noise:
        noise = Image.effect_noise(image.size, level.noise)
        image = Image.blend(image, ImageOps.autocontrast(noise), 0.18)
    if level.shadow:
        # A soft shadow from one side, as in a phone photo of paper.
        width, height = image.size
        gradient = Image.linear_gradient("L").rotate(90).resize((width, height))
        shade = gradient.point(lambda p: 255 - int(p * level.shadow))
        image = Image.composite(image, Image.new("L", image.size, 0), shade)
    return image


def scanned_pdf(digital: bytes, level: ScanLevel, seed: int) -> bytes:
    """Each page rendered to an image, damaged, and saved as an image-only PDF (no text layer)."""
    rng = random.Random(seed)
    source = pymupdf.open(stream=digital, filetype="pdf")
    out = pymupdf.open()
    for page in source:
        pixmap = page.get_pixmap(dpi=level.dpi)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        damaged = _degrade(image, level, rng)
        buffer = io.BytesIO()
        damaged.save(buffer, format="JPEG", quality=level.jpeg_quality)
        new_page = out.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(new_page.rect, stream=buffer.getvalue())
    data = out.tobytes()
    out.close()
    source.close()
    return data
