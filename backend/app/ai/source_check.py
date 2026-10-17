"""Check each extracted value against the line it was printed on (AI_spec.md Section 4.5).

Deterministic code only. Digital PDFs and OCR give the page text line by line, with a table row on
one line. A value the AI returns for a test must be on that test's line; one found only on another
test's line was taken from the wrong row (e.g. AST and Ferritin swapped), so it is not shown as the
test's value. Results read from a page image have no text to check against and are never compared
with a range.

Outcomes, per result:
- None: the value is on the test's own line (or nothing to check).
- "read_from_image": the page was read from its image; nothing to check against.
- "name_not_matched": the test's name is not on any line.
- "value_in_other_row": the value is only on another test's line (a swapped row).
- "value_not_matched": the value is on no line with the test's name.
"""

import difflib
import re
import unicodedata
from dataclasses import dataclass

from app.ai.reading import PreparedDocument

_WORD = re.compile(r"[a-z0-9]+")
_PIECE = re.compile(r"\w+|[^\w\s]")


@dataclass(frozen=True)
class SourceText:
    pages: dict[int, list[str]]  # the text of each text page, line by line
    image_pages: frozenset[int]  # pages read from their image

    @classmethod
    def of(cls, document: PreparedDocument) -> "SourceText":
        return cls(
            {page.page_number: [line for line in page.text.splitlines() if line.strip()] for page in document.texts},
            frozenset(image.page_number for image in document.images),
        )

    def lines(self, page: int | None) -> list[str] | None:
        """The lines a result may come from; None when it was read from an image."""
        if page in self.pages:
            return self.pages[page]
        if page in self.image_pages or not self.pages:
            return None
        return [line for lines in self.pages.values() for line in lines]  # page unknown: any text page


def _words(text: str) -> set[str]:
    return set(_WORD.findall(text.casefold()))


def _same_word(word: str, words: set[str]) -> bool:
    """Exact, or nearly so for longer words (OCR may misread a letter: "Ferritim")."""
    if word in words:
        return True
    return len(word) >= 4 and any(
        len(other) >= 4 and difflib.SequenceMatcher(None, word, other).ratio() >= 0.8 for other in words
    )


def names(name: str, line: str) -> bool:
    """The line names this test: at least half of the name's words are on it."""
    wanted = [word for word in _WORD.findall(name.casefold()) if len(word) >= 2 or word.isdigit()]
    if not wanted:
        return False
    words = _words(line)
    found = sum(_same_word(word, words) for word in wanted)
    return found >= 1 and found * 2 >= len(wanted)


def contains(line: str, text: str) -> bool:
    """The text is on the line as written, ignoring spacing around symbols ("0 - 40" = "0-40").

    A number must stand alone: "5" is not found in "15" or "5.4".
    """
    pattern = _pattern(text)
    return pattern is None or re.search(pattern, line.casefold()) is not None


def _pattern(text: str) -> str | None:
    pieces = _PIECE.findall(text.casefold())
    if not pieces:
        return None
    pattern = r"\s*".join(re.escape(piece) for piece in pieces)
    if pieces[0][0].isdigit():
        pattern = r"(?<![\d.])" + pattern
    if pieces[-1][-1].isdigit():
        pattern += r"(?!\.?\d)"
    return pattern


def _stray(char: str) -> bool:
    """A character OCR produces for a symbol it misread: unrecognised (U+FFFD), or a currency or other
    symbol never part of a value or range ("£35" for "≤ 3.5"). Comparison and flag marks (< ≤ = ± *) are not."""
    return char == "�" or (char != "°" and unicodedata.category(char) in ("Sc", "Sk", "So"))


def beside_unreadable(source: SourceText, name: str, text: str, page: int | None) -> bool:
    """On the test's line, the text touches a stray symbol ("£35" returned as "35").

    The model may drop the character the OCR misread; what is left is then not what was printed.
    """
    pattern = _pattern(text)
    lines = source.lines(page)
    if pattern is None or not lines:
        return False
    # Directly touching; one space is allowed before ("£ 3.5"), none after: a character after a gap
    # belongs to the next column.
    touching = re.compile(rf"(?P<before>\S) ?{pattern}|{pattern}(?P<after>\S)")
    rows = [index for index, line in enumerate(lines) if names(name, line)]
    return any(
        _stray(match.group("before") or match.group("after"))
        for index in rows
        for match in touching.finditer(" ".join(lines[index : index + 2]).casefold())
    )


def check(source: SourceText, name: str, value: str, page: int | None, other_names: list[str]) -> str | None:
    lines = source.lines(page)
    if lines is None:
        return "read_from_image"
    own = [index for index, line in enumerate(lines) if names(name, line)]
    if not own:
        # Page unknown and some pages were images: the result probably came from one of those.
        return "read_from_image" if page is None and source.image_pages else "name_not_matched"
    if any(contains(lines[index], value) for index in own):
        return None
    others = [other for other in other_names if other.casefold() != name.casefold()]
    swapped = any(
        contains(line, value) and any(names(other, line) for other in others)
        for index, line in enumerate(lines)
        if index not in own
    )
    return "value_in_other_row" if swapped else "value_not_matched"


def near(source: SourceText, name: str, text: str, page: int | None) -> bool:
    """The text (a unit or range) is on the test's line or the next one (ranges may wrap)."""
    lines = source.lines(page)
    if lines is None:
        return True  # nothing to check against
    rows = [index for index, line in enumerate(lines) if names(name, line)]
    return not rows or any(contains(" ".join(lines[index : index + 2]), text) for index in rows)


def _has_values(source: SourceText, name: str, page: int | None) -> bool:
    """Some line naming the test also holds a number that is not part of the name ("Vitamin B12")."""
    own_words = set(_WORD.findall(name.casefold()))
    return any(
        any(any(ch.isdigit() for ch in word) for word in _words(line) - own_words)
        for line in source.lines(page) or []
        if names(name, line)
    )


def check_all(source: SourceText, items: list[tuple[str, str, int | None]]) -> list[str | None]:
    """check() for every (name, value, page).

    Some PDFs give the text column by column (all names, then all values), so a test's line holds no
    values at all. There "value_not_matched" says nothing about the value and is dropped.
    """
    all_names = [name for name, _, _ in items]
    outcomes = [check(source, name, value, page, all_names) for name, value, page in items]
    named = [(name, page) for (name, _, page), o in zip(items, outcomes, strict=True) if o != "name_not_matched"]
    named = [(name, page) for name, page in named if source.lines(page) is not None]
    if named and sum(_has_values(source, name, page) for name, page in named) * 2 < len(named):
        outcomes = [None if o == "value_not_matched" else o for o in outcomes]
    return outcomes
