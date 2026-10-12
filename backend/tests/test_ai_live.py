"""Real extractions through Groq (qwen/qwen3.8-27b) on synthetic reports. Uses your Groq quota.

Skipped unless you opt in:  RUN_LIVE_AI=1 uv run pytest -m live -s
(GROQ_API_KEY must be set in backend/.env or the environment.)
"""

import io
import os
from datetime import date
from decimal import Decimal

import pytest
from PIL import Image, ImageDraw, ImageFont
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.ai.extractor import GroqExtractor, make_client
from app.ai.prescription_validation import validate_prescription
from app.ai.reading import prepare
from app.ai.validation import validate_payload
from app.core.config import get_settings
from tests.ai_fakes import SYNTHETIC_PRESCRIPTION_LINES, SYNTHETIC_REPORT_LINES, text_pdf

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("RUN_LIVE_AI") != "1", reason="live AI test: set RUN_LIVE_AI=1 to run"),
]


class _KeyFromDotenv(BaseSettings):
    # conftest overrides most settings for tests; read only the real key from backend/.env.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    groq_api_key: SecretStr | None = None


@pytest.fixture
def extractor():
    key = _KeyFromDotenv().groq_api_key
    if key is None:
        pytest.skip("GROQ_API_KEY is not set")
    settings = get_settings().model_copy(update={"groq_api_key": key})
    return GroqExtractor(make_client(settings), settings)


def _check_known_values(outcome, page_count):
    results = {r.name: r for r in validate_payload(outcome.payload, page_count, date.today())}
    print(f"\n  model={outcome.model} input={outcome.input_tokens} output={outcome.output_tokens}")
    for item in results.values():
        print(f"  {item.name:<16} {item.value_text:<6} {item.unit or '':<6} {item.confidence:<6} {item.findings}")

    assert results["Haemoglobin"].value_numeric == Decimal("13.8") and results["Haemoglobin"].unit == "g/dL"
    assert results["HbA1c"].value_text == "6.1" and results["HbA1c"].unit == "%"
    assert results["Fasting glucose"].value_numeric == Decimal("102")
    assert results["Vitamin B12"].value_text == "<150" and results["Vitamin B12"].value_numeric is None
    assert all(r.observed_at is not None and r.observed_at.isoformat() == "2026-03-14" for r in results.values())
    assert outcome.payload.report_date_text == "2026-03-14"  # as printed ("Collected: 2026-03-14")


def test_typed_report(extractor):
    document = prepare(text_pdf(SYNTHETIC_REPORT_LINES), "application/pdf")
    _check_known_values(extractor.extract(document), document.page_count)


def test_photographed_report(extractor):
    """The same synthetic report rendered as a photo, read through vision."""
    image = Image.new("RGB", (1400, 700), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=28)
    for index, line in enumerate(SYNTHETIC_REPORT_LINES):
        draw.text((40, 40 + index * 70), line, fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    document = prepare(buffer.getvalue(), "image/png")
    _check_known_values(extractor.extract(document), document.page_count)


def test_typed_prescription(extractor):
    """The synthetic prescription: medicines copied as written, relative follow-ups dated by code."""
    document = prepare(text_pdf(SYNTHETIC_PRESCRIPTION_LINES), "application/pdf")
    assert extractor.classify(document).document_type == "prescription"

    outcome = extractor.extract_prescription(document)
    header, medications, follow_ups = validate_prescription(outcome.payload, document.page_count)
    print(f"\n  model={outcome.model} input={outcome.input_tokens} output={outcome.output_tokens}")
    print(f"  header: {header}")
    for m in medications:
        print(f"  med: {m.name} | {m.strength} | {m.instructions} | {m.duration_text} | {m.review_reason}")
    for f in follow_ups:
        print(f"  follow-up: {f.description} | {f.date_text} | {f.due_date} ({f.due_date_basis}) | {f.review_reason}")

    assert header.prescribed_on is not None and header.prescribed_on.isoformat() == "2026-10-07"
    assert header.prescriber_name == "Dr. Sample Physician"
    by_name = {m.name: m for m in medications}
    assert by_name["Atorvastatin"].strength == "10 mg"
    assert by_name["Vitamin D3"].strength == "60,000 IU"
    dated = [(f.description.casefold(), f.due_date.isoformat()) for f in follow_ups if f.due_date]
    kidney = [d for name, d in dated if "kidney function" in name]
    assert kidney == ["2026-11-04"]  # once, with its own timing (never borrowed from another sentence)
    assert [d for name, d in dated if name == "cbc"] == ["2026-12-07"]
    assert sorted(d for name, d in dated if name in ("hba1c", "lipid profile")) == ["2027-01-07", "2027-01-07"]
