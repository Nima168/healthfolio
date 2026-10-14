"""Score every saved reading and write a self-contained HTML report."""

import html
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from evaluation.cases import build_cases
from evaluation.render import VARIANTS
from evaluation.score import Counts, cer, score, signature

KIND_LABELS = {
    "lab_report": "Lab reports",
    "prescription": "Prescriptions",
    "discharge_summary": "Discharge summaries",
    "consultation_note": "Consultation notes",
    "imaging_report": "Imaging reports",
}
VARIANT_LABELS = {
    "digital": "Digital PDF",
    "scan_clean": "Scan: clean",
    "scan_medium": "Scan: medium",
    "scan_hard": "Scan: hard",
}
TARGETS = {"digital": 0.98, "scan_clean": 0.95}


def _pct(part: int | float, whole: int | float) -> str:
    return "–" if not whole else f"{100 * part / whole:.1f}%"


def _ratio(part, whole) -> float | None:
    return None if not whole else part / whole


def _bar(value: float | None, *, good_high: bool = True) -> str:
    if value is None:
        return "–"
    tone = value if good_high else 1 - value
    colour = "#5A6848" if tone >= 0.95 else "#B8860B" if tone >= 0.8 else "#A0522D"
    return (
        f'<span class="bar"><span style="width:{max(2, value * 100):.0f}%;background:{colour}"></span></span>'
        f'<span class="num">{100 * value:.1f}%</span>'
    )


def _metrics_row(label: str, c: Counts, docs: int) -> str:
    extra_share = _ratio(c.items_extra, c.items_found + c.items_extra)
    fully_right = _ratio(c.items_found - c.wrong_items, c.items_expected)
    return (
        f"<tr><td>{html.escape(label)}</td><td class=c>{docs}</td>"
        f"<td>{_bar(_ratio(c.items_found, c.items_expected))}</td>"
        f"<td>{_bar(_ratio(c.fields_correct, c.fields_checked))}</td>"
        f"<td>{_bar(_ratio(c.fields_misleading, c.fields_checked), good_high=False)}</td>"
        f"<td>{_bar(_ratio(c.fields_not_identified, c.fields_checked), good_high=False)}</td>"
        f"<td>{_bar(fully_right)}</td>"
        f"<td>{_bar(extra_share, good_high=False)}</td>"
        f"<td>{_bar(_ratio(c.wrong_items_flagged, c.wrong_items))}</td>"
        f"<td>{_bar(_ratio(c.groups_correct, c.groups_checked))}</td>"
        f"<td>{_bar(_ratio(c.dates_correct, c.dates_checked))}</td>"
        f"<td>{_bar(_ratio(c.printed_dates_correct, c.printed_dates_checked))}</td>"
        f"<td>{_bar(_ratio(c.blanks_honest, c.blanks_expected))}</td></tr>"
    )


HEAD = """<tr><th>Group</th><th>Docs</th><th>Items found</th><th>Fields right</th><th>Misleading fields</th><th>Not identified</th><th>Items fully right</th>
<th>Extra (invented) items</th><th>Wrong items flagged</th><th>Grouping right</th><th>Dates right</th><th>Dates as printed</th>
<th>Blanks left blank</th></tr>"""


def _totals(results_dir: Path, cases: dict) -> tuple[Counts, int]:
    total = Counts()
    readings = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(results_dir.glob("*__r1.json"))]
    for r in readings:
        total.add(score(cases[r["case"]], r))
    return total, len(readings)


def _comparison(baseline_dir: Path, results_dir: Path, cases: dict) -> str:
    before, n_before = _totals(baseline_dir, cases)
    after, n_after = _totals(results_dir, cases)
    rows = [
        ("Fields right", lambda c: _ratio(c.fields_correct, c.fields_checked), True),
        ("Misleading fields", lambda c: _ratio(c.fields_misleading, c.fields_checked), False),
        ("Not identified", lambda c: _ratio(c.fields_not_identified, c.fields_checked), False),
        ("Grouping right", lambda c: _ratio(c.groups_correct, c.groups_checked), True),
        ("Misleading groups", lambda c: _ratio(c.groups_misleading, c.groups_checked), False),
        ("Extra (invented) items", lambda c: _ratio(c.items_extra, c.items_found + c.items_extra), False),
        ("Wrong items flagged", lambda c: _ratio(c.wrong_items_flagged, c.wrong_items), True),
    ]
    body = "".join(
        f"<tr><td>{label}</td><td>{_bar(fn(before), good_high=high)}</td><td>{_bar(fn(after), good_high=high)}</td></tr>"
        for label, fn, high in rows
    )
    return (
        f"<section><h2>Before and after</h2><p class=meta>Before: {html.escape(baseline_dir.name)} ({n_before} readings) · "
        f"after: {html.escape(results_dir.name)} ({n_after} readings), same documents.</p>"
        f"<table><tr><th>Measure</th><th>Before</th><th>After</th></tr>{body}</table></section>"
    )


def write_report(results_dir: Path, docs_dir: Path, path: Path, baseline_dir: Path | None = None) -> None:
    cases = {case.id: case for case in build_cases()}
    readings = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(results_dir.glob("*.json"))]
    first = [r for r in readings if r["repeat"] == 1]
    if not first:
        raise SystemExit(f"no readings in {results_dir}; run `python -m evaluation run` first")

    by_variant: dict[str, Counts] = defaultdict(Counts)
    by_kind: dict[str, Counts] = defaultdict(Counts)
    by_cell: dict[tuple[str, str], Counts] = defaultdict(Counts)
    docs_variant: Counter = Counter()
    docs_kind: Counter = Counter()
    docs_cell: Counter = Counter()
    total = Counts()
    methods: dict[str, Counter] = defaultdict(Counter)
    cers: dict[str, list[float]] = defaultdict(list)
    rejected: Counter = Counter()
    failures: list[str] = []
    examples: dict[str, list[str]] = defaultdict(list)
    seconds, tokens_in, tokens_out = [], [], []

    for r in first:
        case = cases[r["case"]]
        counts = score(case, r)
        variant = r["variant"]
        total.add(counts)
        by_variant[variant].add(counts)
        by_kind[case.kind].add(counts)
        by_cell[(case.kind, variant)].add(counts)
        docs_variant[variant] += 1
        docs_kind[case.kind] += 1
        docs_cell[(case.kind, variant)] += 1
        methods[variant][r.get("method") or r.get("error") or "failed"] += 1
        rejected[variant] += bool(r.get("upload_rejected"))
        if r.get("error"):
            failures.append(f"{case.id} ({VARIANT_LABELS[variant]}): {r['error']}")
        if r.get("method") == "ocr" and r.get("ocr_text"):
            truth = (docs_dir / f"{case.id}.txt").read_text(encoding="utf-8")
            cers[variant].append(cer(r["ocr_text"], truth))
        for message in counts.errors:
            examples[variant].append(f"{case.id}: {message}")
        if "seconds_ai" in r:
            seconds.append(r["seconds_reading"] + r["seconds_ai"])
            tokens_in.append(r["tokens"]["input"])
            tokens_out.append(r["tokens"]["output"])

    # Run-to-run consistency on documents read more than once.
    groups = defaultdict(list)
    for r in readings:
        groups[(r["case"], r["variant"])].append(signature(r))
    repeated = {k: v for k, v in groups.items() if len(v) > 1}
    consistency_rows = "".join(
        f"<tr><td>{c} · {VARIANT_LABELS[v]}</td><td class=c>{len(s)}</td><td class=c>{len(set(s))}</td>"
        f"<td>{'identical every time' if len(set(s)) == 1 else 'differed between runs'}</td></tr>"
        for (c, v), s in sorted(repeated.items())
    )

    # Headline numbers.
    field_acc = {v: _ratio(by_variant[v].fields_correct, by_variant[v].fields_checked) for v in VARIANTS}
    extra = _ratio(total.items_extra, total.items_found + total.items_extra) or 0
    flagged = _ratio(total.wrong_items_flagged, total.wrong_items)
    target_rows = "".join(
        f"<tr><td>{VARIANT_LABELS[v]}: fields right ≥ {t:.0%}</td><td>{_bar(field_acc[v])}</td>"
        f"<td>{'met' if field_acc[v] is not None and field_acc[v] >= t else 'not met' if field_acc[v] is not None else 'not run'}</td></tr>"
        for v, t in TARGETS.items()
    )
    misleading = _ratio(total.fields_misleading, total.fields_checked) or 0
    target_rows += (
        f"<tr><td>Misleading values shown = 0 (wrong but presented as real)</td><td>{_bar(misleading, good_high=False)}</td>"
        f"<td>{'met' if total.fields_misleading == 0 else f'not met ({total.fields_misleading})'}</td></tr>"
        f"<tr><td>Misleading groups = 0 (shown as above/below/normal, but wrong)</td>"
        f"<td>{_bar(_ratio(total.groups_misleading, total.groups_checked), good_high=False)}</td>"
        f"<td>{'met' if total.groups_misleading == 0 else f'not met ({total.groups_misleading})'}</td></tr>"
    )
    overall = _ratio(total.fields_correct, total.fields_checked)
    target_rows += (
        f"<tr><td>All copies: fields right ≥ 98% (spec release gate, DL_AI_spec §11)</td><td>{_bar(overall)}</td>"
        f"<td>{'met' if overall is not None and overall >= 0.98 else 'not met'}</td></tr>"
    )
    target_rows += (
        f"<tr><td>Invented items = 0%</td><td>{_bar(extra, good_high=False)}</td>"
        f"<td>{'met' if total.items_extra == 0 else 'not met'}</td></tr>"
        f"<tr><td>Wrong items flagged for review ≥ 80%</td><td>{_bar(flagged)}</td>"
        f"<td>{'met' if flagged is not None and flagged >= 0.8 else 'not met' if flagged is not None else 'no wrong items'}</td></tr>"
    )

    variant_rows = "".join(
        _metrics_row(VARIANT_LABELS[v], by_variant[v], docs_variant[v]) for v in VARIANTS if docs_variant[v]
    )
    kind_rows = "".join(_metrics_row(KIND_LABELS[k], by_kind[k], docs_kind[k]) for k in KIND_LABELS if docs_kind[k])
    cell_rows = "".join(
        _metrics_row(f"{KIND_LABELS[k]} · {VARIANT_LABELS[v]}", by_cell[(k, v)], docs_cell[(k, v)])
        for k in KIND_LABELS
        for v in VARIANTS
        if docs_cell[(k, v)]
    )
    route_rows = "".join(
        f"<tr><td>{VARIANT_LABELS[v]}</td><td>{', '.join(f'{m}: {n}' for m, n in methods[v].most_common())}</td>"
        f"<td class=c>{rejected[v]} of {docs_variant[v]}</td>"
        f"<td>{_bar(sum(cers[v]) / len(cers[v]), good_high=False) if cers[v] else '–'}</td></tr>"
        for v in VARIANTS
        if docs_variant[v]
    )
    example_blocks = "".join(
        f"<h3>{VARIANT_LABELS[v]} ({len(examples[v])})</h3><ul>"
        + "".join(f"<li>{html.escape(e)}</li>" for e in examples[v][:25])
        + ("<li>…</li>" if len(examples[v]) > 25 else "")
        + "</ul>"
        for v in VARIANTS
        if examples[v]
    )
    speed = (
        f"{sum(seconds) / len(seconds):.1f} s per document on average (reading + AI); "
        f"{sum(tokens_in) // len(tokens_in):,} input and {sum(tokens_out) // len(tokens_out):,} output tokens on average."
        if seconds
        else "No completed readings."
    )
    prompt_versions = sorted({r["prompt_version"] for r in first})

    page = TEMPLATE.format(
        generated=datetime.now().strftime("%d %b %Y, %H:%M"),
        docs=len(first),
        cases=len({r["case"] for r in first}),
        repeats=len(readings) - len(first),
        versions=html.escape(", ".join(prompt_versions)),
        target_rows=target_rows,
        head=HEAD,
        variant_rows=variant_rows,
        kind_rows=kind_rows,
        cell_rows=cell_rows,
        route_rows=route_rows,
        consistency=(
            f"<table><tr><th>Document</th><th>Runs</th><th>Different readings</th><th>Result</th></tr>{consistency_rows}</table>"
            if repeated
            else "<p>Not measured in this run (use <code>run --repeat 3</code>).</p>"
        ),
        failures="".join(f"<li>{html.escape(f)}</li>" for f in failures) or "<li>None</li>",
        examples=example_blocks or "<p>No errors.</p>",
        speed=speed,
        comparison=_comparison(baseline_dir, results_dir, cases) if baseline_dir else "",
    )
    path.write_text(page, encoding="utf-8")


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Accuracy Evaluation</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=JetBrains+Mono:wght@400;600&family=Neuton:wght@300;400;700&display=swap" rel="stylesheet">
<style>
:root {{ --bg:#FAF7F2; --surface:#FFFDF9; --text:#2F3128; --muted:#6A675C; --border:#E6DFD4; --accent:#5A6848; --mint:#E9ECDF; --lilac:#F4EBDC; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--text); font:400 17px/1.55 Neuton, Georgia, serif; }}
main {{ max-width:1180px; margin:0 auto; padding:36px 16px 80px; }}
h1, h2, h3 {{ font-family:"DM Serif Display", Georgia, serif; font-weight:400; }}
h1 {{ font-size:2.3rem; margin:0 0 4px; }} h2 {{ color:var(--accent); margin:0 0 10px; }} h3 {{ margin:14px 0 4px; }}
.meta, code, .num {{ font-family:"JetBrains Mono", Menlo, monospace; }} .meta {{ color:var(--muted); font-size:.8rem; }}
section {{ background:var(--surface); border:1px solid var(--border); border-radius:14px; padding:20px 22px; margin:16px 0; overflow-x:auto; }}
table {{ width:100%; border-collapse:collapse; font-size:.9rem; }} th, td {{ text-align:left; padding:6px 8px; border-bottom:1px solid var(--border); vertical-align:middle; }}
th {{ color:var(--muted); font-weight:700; }} td.c {{ text-align:center; }}
.bar {{ display:inline-block; width:70px; height:8px; background:var(--mint); border-radius:4px; overflow:hidden; vertical-align:middle; margin-right:6px; }}
.bar span {{ display:block; height:100%; }} .num {{ font-size:.78rem; }}
.callout {{ background:var(--lilac); border-radius:10px; padding:10px 14px; }} li {{ margin:3px 0; font-size:.92rem; }}
</style></head><body><main>
<h1>Accuracy Evaluation</h1>
<p class="meta">Generated {generated} · {docs} readings of {cases} fictional documents · {repeats} repeat readings · prompts: {versions}</p>

<section><h2>How this was measured</h2>
<p>Fictional reports were generated from known data, so every correct answer is known exactly. Each report exists as a digital PDF and as scanned copies at three damage levels (clean, medium, hard: blur, tilt, noise, shadow). Every copy went through the app's real reading pipeline: upload quality check, PyMuPDF or Tesseract OCR (with the vision fallback), Groq, and the validation rules. Results were then compared with the known answers.</p>
<ul>
<li><b>Items found</b>: expected results, medicines, follow-ups, diagnoses or findings that were read.</li>
<li><b>Fields right</b>: value, unit and range (or strength, instructions and duration) exactly as printed, on found items.</li>
<li><b>Misleading fields</b>: a wrong value, unit or range shown as if it were correct. The most important number: it should be 0.</li>
<li><b>Not identified</b>: a part printed but not readable, shown as “Not identified” instead of a guess: an honest gap.</li>
<li><b>Extra items</b>: items read that do not exist in the document (invented).</li>
<li><b>Wrong items flagged</b>: of items read with a wrong field, the share marked “needs review”.</li>
<li><b>Grouping right</b>: above / below / normal / not compared, versus the correct group.</li>
<li><b>Blanks left blank</b>: a unit or range not printed stays empty (“Not mentioned”) instead of being guessed.</li>
</ul></section>

{comparison}
<section><h2>Targets</h2><table><tr><th>Target</th><th>Result</th><th>Status</th></tr>{target_rows}</table></section>

<section><h2>By copy type</h2><table>{head}{variant_rows}</table></section>
<section><h2>By document type</h2><table>{head}{kind_rows}</table></section>
<section><h2>By document type and copy type</h2><table>{head}{cell_rows}</table></section>

<section><h2>Reading route and OCR quality</h2>
<table><tr><th>Copy type</th><th>How pages were read</th><th>Would be refused at upload</th><th>OCR character error rate (OCR-only documents)</th></tr>{route_rows}</table>
<p class="meta">digital = PDF text · ocr = Tesseract · ocr+vision = some pages read from the image · vision = all pages read from images. The upload check runs before reading in the app; here every copy was read anyway, to measure it.</p></section>

<section><h2>Run-to-run consistency</h2>{consistency}</section>

<section><h2>Failed readings</h2><ul>{failures}</ul></section>
<section><h2>Errors found (examples)</h2>{examples}</section>
<section><h2>Speed and size</h2><p>{speed}</p></section>

<section class="callout"><b>Limits.</b> The documents are synthetic: clean layouts and computer fonts, damaged on purpose. The numbers show how the pipeline behaves and where it starts to fail, not proof of accuracy on real hospital reports. Handwriting is not covered. A small set gives wide uncertainty: one error in a few dozen fields moves a percentage by several points.</section>
</main></body></html>
"""
