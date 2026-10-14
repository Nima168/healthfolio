"""Printed but unreadable: such a part is shown as "Not identified", never as a guess (AI_spec.md Section 4.5).

"Not mentioned" means the document does not print the part; "Not identified" means it is printed but could
not be read reliably. A part is not identified when the model says it cannot read it with certainty, or when
fixed rules find the text garbled. The doubtful text is replaced, so it cannot appear anywhere as a value.
"""

import re

NOT_IDENTIFIED = "Not identified"
REPLACEMENT_CHARACTER = "�"  # what OCR and decoders put in place of a character they could not recognise

# Words that are real results on their own (qualitative tests), so letters without digits are expected.
_QUALITATIVE = re.compile(
    r"^(?:non[- ]?)?(?:positive|negative|nil|trace|reactive|normal|abnormal|absent|present|detected|"
    r"not detected|seen|not seen|clear|turbid|pale yellow|yellow|straw|amber|occasional|few|many|plenty|"
    r"no growth|sterile|within normal limits|wnl|equivocal|indeterminate|borderline)\b",
    re.IGNORECASE,
)
# A word that mixes letters and digits ("O38", "l3.B", "13.8H"), excluding units and common forms.
_MIXED_TOKEN = re.compile(r"(?<![\w^*/.])(?=[A-Za-z0-9.,]*\d)(?=[A-Za-z0-9.,]*[A-Za-z])[A-Za-z0-9.,]{2,}(?![\w^*/])")
_ALLOWED_MIXED = re.compile(r"^(?:\d+(?:st|nd|rd|th|x|mg|g|ml|mcg|iu|u|l|dl|mm|cm|kg|hrs?|min|s|d)|x\d+)$", re.I)
_TWO_DOTS = re.compile(r"\d\.\d*\.")  # "5.7." or "1.2.3": a misread number
_DIGITS_SPACE_DIGITS = re.compile(r"\d\s+\d")  # "0.3 1.2": a range with its separator lost
_DIGIT_COLON_DIGIT = re.compile(r"\d\s*:\s*\d")  # "55:2" in a range
_UNIT_STRAY = re.compile(r"[:;\"'|_~\\{}\[\]]")


def _mixed_tokens(text: str) -> bool:
    return any(not _ALLOWED_MIXED.match(token) for token in _MIXED_TOKEN.findall(text))


def garbled_value(value: str | None, *, numeric_expected: bool) -> bool:
    """A result that cannot be a correct reading of what is printed."""
    if not value:
        return False
    if REPLACEMENT_CHARACTER in value or _TWO_DOTS.search(value) or _mixed_tokens(value):
        return True
    has_digit = any(char.isdigit() for char in value)
    has_letter = any(char.isalpha() for char in value)
    # Letters only where a number belongs (e.g. "TENS" for MCV with a range of 83.0 - 101.0).
    return numeric_expected and has_letter and not has_digit and not _QUALITATIVE.match(value.strip())


def garbled_range(text: str | None) -> bool:
    if not text:
        return False
    return bool(
        REPLACEMENT_CHARACTER in text
        or _mixed_tokens(text)
        or _DIGITS_SPACE_DIGITS.search(text)
        or _DIGIT_COLON_DIGIT.search(text)
    )


def garbled_unit(text: str | None) -> bool:
    if not text:
        return False
    return REPLACEMENT_CHARACTER in text or bool(_UNIT_STRAY.search(text))


def garbled_text(text: str | None) -> bool:
    """Free text (medicine strength, instructions, duration): only unrecognised characters are certain."""
    return bool(text) and REPLACEMENT_CHARACTER in text


def check_result(
    value: str | None, unit: str | None, reference: str | None, declared: list[str]
) -> tuple[str | None, str | None, str | None, list[str]]:
    """(value, unit, reference range, the parts not identified) for one test result."""
    numeric_expected = bool(reference and any(char.isdigit() for char in reference))
    parts = []
    if "value" in declared or garbled_value(value, numeric_expected=numeric_expected):
        parts.append("value")
    if "unit" in declared or garbled_unit(unit):
        parts.append("unit")
    if "range" in declared or garbled_range(reference):
        parts.append("range")
    return (
        NOT_IDENTIFIED if "value" in parts else value,
        NOT_IDENTIFIED if "unit" in parts else unit,
        NOT_IDENTIFIED if "range" in parts else reference,
        parts,
    )


# Header fields a model may wrongly list as a test result.
_NOT_A_TEST = re.compile(
    r"^(?:report(?:ed)?(?: date| on)?|date(?: of [a-z ]+)?|collected(?: on)?|collection(?: date)?|received(?: on)?|"
    r"sample(?: type| collected| received)?|specimen|patient(?: name| id)?|name|age|sex|gender|age ?/ ?sex|"
    r"ref(?:\.|erred)? ?by|referred by|doctor|lab no\.?|report id|uhid|page|signature)\s*:?$",
    re.IGNORECASE,
)
_DATE_LIKE = re.compile(
    r"^\d{1,2}[-/. ](?:\d{1,2}|[A-Za-z]{3,9})[-/. ]\d{2,4}(?:\s+\d{1,2}:\d{2})?$|^\d{4}-\d{2}-\d{2}$|"
    r"^[A-Za-z]{3,9} \d{1,2},? \d{4}$"
)


def not_a_result(name: str, value: str | None, unit: str | None, reference: str | None) -> bool:
    """A header line (a date, the patient's details) read as if it were a test result."""
    if _NOT_A_TEST.match(name.strip()):
        return True
    return bool(value and _DATE_LIKE.match(value.strip()) and not unit and not reference)
