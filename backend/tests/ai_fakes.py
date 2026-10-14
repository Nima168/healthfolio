"""Test doubles for the AI pipeline: synthetic PDFs/photos and a scripted fake Groq client (no network, no cost)."""

import io
import json
from types import SimpleNamespace
from typing import Any

import groq
import httpx

# ---------- synthetic PDFs ----------


def _pdf(page_streams: list[bytes]) -> bytes:
    """A minimal valid PDF. Each stream is a page content stream (empty for a 'scanned', text-less page)."""
    objects: list[bytes] = []
    page_ids = [3 + 2 * i for i in range(len(page_streams))]
    font_id = 3 + 2 * len(page_streams)
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{pid} 0 R" for pid in page_ids).encode()
    objects.append(b"<< /Type /Pages /Kids [" + kids + b"] /Count " + str(len(page_ids)).encode() + b" >>")
    for index, stream in enumerate(page_streams):
        content_id = page_ids[index] + 1
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents "
            + f"{content_id} 0 R".encode()
            + b" /Resources << /Font << /F1 "
            + f"{font_id} 0 R".encode()
            + b" >> >> >>"
        )
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def text_pdf(*pages: list[str]) -> bytes:
    """A typed PDF: each page is a list of text lines."""
    streams = []
    for lines in pages:
        ops = [b"BT /F1 11 Tf 50 750 Td 14 TL"]
        for line in lines:
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            ops.append(f"({escaped}) Tj T*".encode())
        ops.append(b"ET")
        streams.append(b"\n".join(ops))
    return _pdf(streams)


def scanned_pdf(page_count: int = 1) -> bytes:
    """A PDF with no text layer, like a scan."""
    return _pdf([b"" for _ in range(page_count)])


def printed_scan() -> bytes:
    """A synthetic scanned page: printed text drawn on an image, inside a PDF with no text layer."""
    import pymupdf
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (1700, 600), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=44)
    for row, line in enumerate(["Synthetic Lab Report", "Haemoglobin    13.8    g/dL", "Platelets    250    10^3/uL"]):
        draw.text((80, 80 + row * 150), line, fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    pdf = pymupdf.open()
    page = pdf.new_page(width=850, height=300)
    page.insert_image(page.rect, stream=buffer.getvalue())
    return pdf.tobytes()


SYNTHETIC_REPORT_LINES = [
    "City Diagnostics - Synthetic Test Report (not real patient data)",
    "Collected: 2026-03-14",
    "Test                Result     Unit      Reference",
    "Haemoglobin         13.8       g/dL      12.0 - 15.5",
    "HbA1c               6.1        %         4.0 - 5.6",
    "Fasting glucose     102        mg/dL     70 - 99",
    "Vitamin B12         <150       pg/mL     200 - 900",
    "Interpretation notes appear below the table and are not results.",
]


def printed_lines(reading: dict[str, Any]) -> list[str]:
    """A lab report printing exactly what a fake reading reports: one line per result, as a typed PDF gives it."""
    rows = [[r["test_name"], r["value_text"], r["unit"], r["reference_range_text"]] for r in reading["lab_results"]]
    return ["Synthetic Lab Report (not real patient data)"] + [" ".join(part for part in row if part) for row in rows]


SYNTHETIC_PRESCRIPTION_LINES = [
    "Sample Clinic - Synthetic Prescription (not real patient data)",
    "Dr. Sample Physician          Date: 07-Oct-2026",
    "1. Atorvastatin 10 mg - once daily at night - 90 days",
    "2. Metformin 500 mg - once daily after dinner - 90 days",
    "3. Ferrous ascorbate + folic acid - once daily after lunch - 60 days",
    "4. Vitamin D3 60,000 IU - once weekly - 8 weeks",
    "Review with Kidney function test after 4 weeks.",
    "CBC on 07-Dec-2026. HbA1c and lipid profile after 3 months.",
]


def photo(width: int = 64, height: int = 48, *, fmt: str = "PNG", exif_rotate: bool = False) -> bytes:
    """A synthetic photo (solid colour)."""
    from PIL import Image

    image = Image.new("RGB", (width, height), (240, 240, 240))
    buffer = io.BytesIO()
    if exif_rotate:
        exif = Image.Exif()
        exif[0x0112] = 6  # orientation: rotate 90° clockwise when displayed
        image.save(buffer, format="JPEG", exif=exif)
    else:
        image.save(buffer, format=fmt)
    return buffer.getvalue()


# ---------- fake Groq client ----------


def result(**overrides: Any) -> dict[str, Any]:
    base = {
        "test_name": "Haemoglobin",
        "value_text": "13.8",
        "value_numeric": 13.8,
        "unit": "g/dL",
        "reference_range_text": "12.0 - 15.5",
        "reference_low": 12.0,
        "reference_high": 15.5,
        "result_date": None,
        "result_date_precision": None,
        "page": 1,
        "source_text": "Haemoglobin 13.8 g/dL 12.0 - 15.5",
        "confidence": "high",
        "notes": None,
    }
    return base | overrides


def payload(results: list[dict] | None = None, **overrides: Any) -> dict[str, Any]:
    base = {
        "report_date_text": "14/03/2026",
        "report_date": "2026-03-14",
        "report_date_precision": "day",
        "lab_results": [result()] if results is None else results,
        "warnings": [],
    }
    return base | overrides


def medication(**overrides: Any) -> dict[str, Any]:
    base = {
        "name": "Atorvastatin",
        "strength": "10 mg",
        "instructions": "once daily at night",
        "duration_text": "90 days",
        "page": 1,
        "source_text": "1. Atorvastatin 10 mg - once daily at night - 90 days",
        "confidence": "high",
        "notes": None,
    }
    return base | overrides


def follow_up(**overrides: Any) -> dict[str, Any]:
    base = {
        "description": "Kidney function test",
        "kind": "investigation",
        "date": None,
        "date_text": "after 4 weeks",
        "relative_amount": 4,
        "relative_unit": "weeks",
        "page": 1,
        "source_text": "Review with Kidney function test after 4 weeks.",
        "confidence": "high",
        "notes": None,
    }
    return base | overrides


def prescription(
    medications: list[dict] | None = None, follow_ups: list[dict] | None = None, **overrides: Any
) -> dict[str, Any]:
    """The synthetic prescription above, as the model would return it."""
    base = {
        "prescription_date_text": "07-Oct-2026",
        "prescription_date": "2026-10-07",
        "prescriber_name": "Dr. Sample Physician",
        "medications": [
            medication(),
            medication(name="Metformin", strength="500 mg", instructions="once daily after dinner"),
            medication(
                name="Ferrous ascorbate + folic acid",
                strength=None,
                instructions="once daily after lunch",
                duration_text="60 days",
            ),
            medication(name="Vitamin D3", strength="60,000 IU", instructions="once weekly", duration_text="8 weeks"),
        ]
        if medications is None
        else medications,
        "follow_ups": [
            follow_up(),
            follow_up(description="doctor visit", kind="appointment"),
            follow_up(
                description="CBC", date="2026-12-07", date_text="07-Dec-2026", relative_amount=None, relative_unit=None
            ),
            follow_up(description="HbA1c", date_text="after 3 months", relative_amount=3, relative_unit="months"),
            follow_up(
                description="lipid profile", date_text="after 3 months", relative_amount=3, relative_unit="months"
            ),
        ]
        if follow_ups is None
        else follow_ups,
        "warnings": [],
    }
    return base | overrides


def classification(document_type: str) -> dict[str, Any]:
    return {"document_type": document_type}


def response(
    body: dict | str, *, finish_reason: str = "stop", model: str = "qwen/qwen3.8-27b", prompt_tokens: int = 1200
) -> SimpleNamespace:
    """A Groq chat-completion response."""
    text = body if isinstance(body, str) else json.dumps(body)
    return SimpleNamespace(
        choices=[SimpleNamespace(finish_reason=finish_reason, message=SimpleNamespace(role="assistant", content=text))],
        model=model,
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=340),
    )


_REQUEST = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")


def api_error(cls: type[groq.APIStatusError], status: int) -> groq.APIStatusError:
    return cls("simulated", response=httpx.Response(status, request=_REQUEST), body=None)


def connection_error() -> groq.APIConnectionError:
    return groq.APIConnectionError(request=_REQUEST)


class FakeGroq:
    """Mimics `client.chat.completions.create`. Each call takes the next scripted reply (a response or an exception)."""

    def __init__(self, *replies: Any) -> None:
        self.replies = list(replies)
        self.requests: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **request: Any) -> Any:
        self.requests.append(request)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, BaseException):
            raise reply
        return reply
