"""Compare what was read with the known answers, and count what was right, missed, invented, or flagged."""

import re
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher

from app.ai.dates import ambiguous
from app.ai.readability import NOT_IDENTIFIED
from evaluation.cases import Case

NAME_MATCH = 0.8  # similarity needed to pair an extracted item with an expected one
TEXT_MATCH = 0.85  # similarity for free text (instructions, findings) to count as the same


def norm(text: str | None) -> str:
    text = (text or "").lower().replace("–", "-").replace("—", "-").replace("µ", "u")
    return re.sub(r"\s+", " ", text).strip(" .;:")


def compact(text: str | None) -> str:
    """For values, units, and ranges: no spaces or thousands commas ("< 7" = "<7", "7,800" = "7800")."""
    return re.sub(r"[\s,]", "", norm(text))


def similar(a: str | None, b: str | None) -> float:
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def pair(expected: list[str], found: list[str], threshold: float = NAME_MATCH) -> list[tuple[int, int]]:
    """Best one-to-one pairs (expected index, found index), most similar first."""
    scored = sorted(
        ((similar(e, f), i, j) for i, e in enumerate(expected) for j, f in enumerate(found)),
        reverse=True,
    )
    used_e, used_f, pairs = set(), set(), []
    for score, i, j in scored:
        if score < threshold:
            break
        if i not in used_e and j not in used_f:
            used_e.add(i)
            used_f.add(j)
            pairs.append((i, j))
    return pairs


def cer(read: str, truth: str) -> float:
    """Character error rate: edits needed to turn the OCR text into the true text, per true character."""
    a, b = norm(read), norm(truth)
    if not b:
        return 0.0
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i] + [0] * len(b)
        for j, char_b in enumerate(b, start=1):
            current[j] = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (char_a != char_b))
        previous = current
    return previous[-1] / len(b)


@dataclass
class Counts:
    items_expected: int = 0
    items_found: int = 0
    items_extra: int = 0
    fields_checked: int = 0
    fields_correct: int = 0
    wrong_items: int = 0
    wrong_items_flagged: int = 0
    groups_checked: int = 0
    groups_correct: int = 0
    dates_checked: int = 0
    dates_correct: int = 0
    printed_dates_checked: int = 0
    printed_dates_correct: int = 0  # the document's date shown exactly as printed
    blanks_expected: int = 0
    blanks_honest: int = 0
    fields_not_identified: int = 0  # printed but shown as "Not identified": an honest gap
    fields_misleading: int = 0  # wrong but shown as if it were the value
    groups_misleading: int = 0  # shown as above / below / normal, but that is not the correct group
    errors: list[str] = field(default_factory=list)

    def add(self, other: "Counts") -> None:
        for name, value in vars(other).items():
            if name == "errors":
                self.errors.extend(value)
            else:
                setattr(self, name, getattr(self, name) + value)


def _honesty(counts: Counts, checks: dict[str, bool], shown: dict) -> None:
    """A wrong field is either an honest gap ("Not identified") or misleading (a wrong value shown as real)."""
    for key, ok in checks.items():
        if ok:
            continue
        if shown[key] == NOT_IDENTIFIED:
            counts.fields_not_identified += 1
        else:
            counts.fields_misleading += 1


def _date_check(counts: Counts, label: str, expected: date | None, found: str | None, printed: str = "") -> None:
    """The calendar date kept for sorting. A printed date whose day and month could be swapped ("03/04/2026")
    must keep none: the right answer there is no date, never a guess (app/ai/dates.py)."""
    if expected is None:
        return
    counts.dates_checked += 1
    wanted = None if ambiguous(printed) else expected.isoformat()
    if found == wanted:
        counts.dates_correct += 1
    else:
        counts.errors.append(f"{label}: expected {wanted!r}, read {found!r}")


def _printed_date_check(counts: Counts, case: Case, got: dict) -> None:
    """The document's date exactly as printed (readings saved before this check have no date_text)."""
    if "date_text" not in got or not case.date_text:
        return
    counts.printed_dates_checked += 1
    found = " ".join((got["date_text"] or "").split())
    if found == " ".join(case.date_text.split()):
        counts.printed_dates_correct += 1
    else:
        counts.errors.append(f"date as printed: expected {case.date_text!r}, shown {got['date_text']!r}")


def _labs(counts: Counts, case: Case, found: list[dict], *, groups: bool) -> None:
    expected = case.labs
    pairs = pair([e.name for e in expected], [f["name"] for f in found])
    counts.items_expected += len(expected)
    counts.items_found += len(pairs)
    counts.items_extra += len(found) - len(pairs)
    matched = {j for _, j in pairs}
    for j, item in enumerate(found):
        if j not in matched:
            counts.errors.append(f"extra result {item['name']!r} = {item['value']!r}")
    paired_expected = {i for i, _ in pairs}
    for i, e in enumerate(expected):
        if i not in paired_expected:
            counts.errors.append(f"missed result {e.name!r} = {e.value!r}")
    for i, j in pairs:
        e, f = expected[i], found[j]
        checks = {
            "value": compact(e.value) == compact(f["value"]),
            "unit": compact(e.unit) == compact(f["unit"]),
            "range": compact(e.range_text) == compact(f["range"]),
        }
        counts.fields_checked += len(checks)
        counts.fields_correct += sum(checks.values())
        _honesty(counts, checks, {"value": f["value"], "unit": f["unit"], "range": f["range"]})
        if e.unit is None:
            counts.blanks_expected += 1
            counts.blanks_honest += f["unit"] in (None, "")
        if e.range_text is None:
            counts.blanks_expected += 1
            counts.blanks_honest += f["range"] in (None, "")
        if any(not ok and f[k] != NOT_IDENTIFIED for k, ok in checks.items()):
            counts.wrong_items += 1
            counts.wrong_items_flagged += bool(f["needs_review"])
        if not all(checks.values()):
            wrong = ", ".join(
                f"{k}: expected {getattr(e, 'range_text' if k == 'range' else k)!r}, read {f[k]!r}"
                for k, ok in checks.items()
                if not ok
            )
            flagged = "flagged for review" if f["needs_review"] else "NOT flagged"
            counts.errors.append(f"{e.name}: {wrong} ({flagged})")
        if groups:
            counts.groups_checked += 1
            if f["group"] == e.group:
                counts.groups_correct += 1
            else:
                counts.groups_misleading += f["group"] != "invalid"  # "not compared" is cautious, not misleading
                counts.errors.append(f"{e.name}: group expected {e.group}, shown as {f['group']}")


def _medicines(counts: Counts, case: Case, found: list[dict]) -> None:
    expected = case.medicines
    pairs = pair([e.name for e in expected], [f["name"] for f in found])
    counts.items_expected += len(expected)
    counts.items_found += len(pairs)
    counts.items_extra += len(found) - len(pairs)
    for i, j in pairs:
        e, f = expected[i], found[j]
        checks = {
            "strength": compact(e.strength) == compact(f["strength"]),
            "instructions": similar(e.instructions, f["instructions"]) >= TEXT_MATCH
            or norm(e.instructions) in norm(f["instructions"]),
            "duration": compact(e.duration) == compact(f["duration"]),
        }
        counts.fields_checked += len(checks)
        counts.fields_correct += sum(checks.values())
        _honesty(counts, checks, f)
        if any(not ok and f[k] != NOT_IDENTIFIED for k, ok in checks.items()):
            counts.wrong_items += 1
            counts.wrong_items_flagged += bool(f["needs_review"])
        if not all(checks.values()):
            counts.errors.append(
                f"{e.name}: " + ", ".join(f"{k} read as {f[k]!r}" for k, ok in checks.items() if not ok)
            )


def _follow_ups(counts: Counts, case: Case, found: list[dict]) -> None:
    """A follow-up counts as found when one with the same due date was read (the wording may differ)."""
    due_dates = [f["due"] for f in found]
    counts.items_expected += len(case.follow_ups)
    for e in case.follow_ups:
        counts.dates_checked += 1
        # Counted from an ambiguous document date: the honest answer is no due date.
        relative = e.timing.startswith("after")
        wanted = None if relative and ambiguous(case.date_text) else e.due.isoformat() if e.due else None
        if (e.due or wanted is None) and wanted in due_dates:
            counts.items_found += 1
            counts.dates_correct += 1
            due_dates.remove(wanted)
        else:
            counts.errors.append(f"follow-up {e.description!r} {e.timing}: expected due {e.due}, read {due_dates}")
    counts.items_extra += len(due_dates)


def _texts(counts: Counts, label: str, expected: list[str], found: list[str]) -> None:
    pairs = pair(expected, found, TEXT_MATCH)
    counts.items_expected += len(expected)
    counts.items_found += len(pairs)
    counts.items_extra += len(found) - len(pairs)
    paired = {i for i, _ in pairs}
    for i, text in enumerate(expected):
        if i not in paired:
            counts.errors.append(f"{label}: missed {text!r}")


def score(case: Case, result: dict) -> Counts:
    """Counts for one reading of one document. A failed reading counts every expected item as missed."""
    counts = Counts()
    got = result.get("extracted")
    if got is None:
        expected = len(case.labs) + len(case.medicines) + len(case.follow_ups) + len(case.diagnoses)
        expected += sum(len(v) for v in case.lists.values())
        counts.items_expected = expected
        counts.errors.append(f"reading failed: {result.get('error')}")
        return counts
    if case.kind == "lab_report":
        _labs(counts, case, got["labs"], groups=True)
        _date_check(counts, "report date", case.doc_date, got.get("date"), case.date_text)
    elif case.kind == "prescription":
        _medicines(counts, case, got["medicines"])
        _follow_ups(counts, case, got["follow_ups"])
        _date_check(counts, "prescription date", case.doc_date, got.get("date"), case.date_text)
    elif case.kind == "discharge_summary":
        _texts(counts, "diagnosis", case.diagnoses, got["diagnoses"])
        _labs(counts, case, got["labs"], groups=False)
        _medicines(counts, case, got["medicines"])
        _follow_ups(counts, case, got["follow_ups"])
        _date_check(counts, "discharge date", case.doc_date, got.get("date"), case.date_text)
        _date_check(counts, "admission date", case.admitted, got.get("admitted"))
    else:
        for key, expected in case.lists.items():
            _texts(counts, key, expected, got["lists"].get(key, []))
        _date_check(counts, "document date", case.doc_date, got.get("date"), case.date_text)
    _printed_date_check(counts, case, got)
    return counts


def signature(result: dict) -> tuple:
    """What a reading says, in a comparable form, for run-to-run consistency."""
    got = result.get("extracted")
    if got is None:
        return ("failed", result.get("error"))
    rows = []
    for item in got.get("labs", []):
        rows.append(("lab", norm(item["name"]), compact(item["value"]), compact(item["unit"]), compact(item["range"])))
    for item in got.get("medicines", []):
        rows.append(("med", norm(item["name"]), compact(item["strength"]), compact(item["duration"])))
    for item in got.get("follow_ups", []):
        rows.append(("fu", item["due"]))
    for text in got.get("diagnoses", []):
        rows.append(("dx", norm(text)))
    for key, texts in got.get("lists", {}).items():
        rows.extend((key, norm(t)) for t in texts)
    return tuple(sorted(rows))
