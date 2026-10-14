"""Dates read from a document: shown exactly as printed, never converted from a guessed format.

The model returns each date twice: as printed ("02/09/26") and as YYYY-MM-DD. The calendar date is
kept only for sorting, the timeline, and due-date calculations, and only when the printed form has
one meaning. "02/09/26" could be 2 September or 9 February, so no calendar date is kept for it
(decision 2026-10-14: "show the date as it is, don't assume the format"). "25/09/26", "02-Sep-2026"
and "2026-09-02" have one meaning and are kept.
"""

import re
from datetime import date

# Two small numbers separated by "/", "-", or "." with an optional year: 02/09, 2.9.26, 02-09-2026.
_NUMERIC_DATE = re.compile(r"(?<![\d./-])(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2}|\d{4}))?(?![\d/-]|\.\d)")


def ambiguous(printed: str | None) -> bool:
    """True when day and month could be swapped (both 1–12 and different)."""
    for match in _NUMERIC_DATE.finditer(printed or ""):
        first, second = int(match.group(1)), int(match.group(2))
        if 1 <= first <= 12 and 1 <= second <= 12 and first != second:
            return True
    return False


def iso_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError:
        return None


def document_date(value: str | None, printed: str | None) -> date | None:
    """The calendar date for a printed date, or None when there is none or its format is ambiguous."""
    parsed = iso_date(value)
    return None if parsed is None or ambiguous(printed) else parsed
