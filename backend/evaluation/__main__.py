"""Accuracy evaluation.

  uv run python -m evaluation generate              write the test documents (no AI calls)
  uv run python -m evaluation run --quick           read a 10-document subset (uses Groq)
  uv run python -m evaluation run                   read all documents; --repeat 3 adds consistency runs
  uv run python -m evaluation report                score the saved readings and write the HTML report

Readings are saved one file each, so an interrupted run continues where it stopped.
"""

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
DOCS = OUT / "docs"
RESULTS = OUT / "results"
REPORTS = HERE.parent.parent / "project_reports"

QUICK = [
    ("lab01", "digital"),
    ("lab01", "scan_medium"),
    ("lab02", "digital"),
    ("lab02", "scan_clean"),
    ("lab02", "scan_hard"),
    ("lab04", "digital"),
    ("rx01", "digital"),
    ("rx01", "scan_medium"),
    ("dis01", "digital"),
    ("img01", "scan_medium"),
]
REPEATED = [
    ("lab01", "digital"),
    ("lab01", "scan_medium"),
    ("rx01", "digital"),
    ("rx01", "scan_medium"),
    ("dis01", "digital"),
]


def generate() -> None:
    from evaluation.cases import build_cases
    from evaluation.render import SCAN_LEVELS, digital_pdf, scanned_pdf

    DOCS.mkdir(parents=True, exist_ok=True)
    for number, case in enumerate(build_cases()):
        data, text = digital_pdf(case)
        (DOCS / f"{case.id}__digital.pdf").write_bytes(data)
        (DOCS / f"{case.id}.txt").write_text(text, encoding="utf-8")
        for name, level in SCAN_LEVELS.items():
            (DOCS / f"{case.id}__{name}.pdf").write_bytes(scanned_pdf(data, level, seed=number))
    print(f"wrote {len(list(DOCS.glob('*.pdf')))} documents to {DOCS}")


def run(args: argparse.Namespace) -> None:
    from app.ai.extractor import GroqExtractor, make_client
    from app.ai.reading import make_ocr
    from app.core.config import get_settings
    from evaluation.cases import build_cases
    from evaluation.pipeline import run_document
    from evaluation.render import VARIANTS

    settings = get_settings()
    if settings.groq_api_key is None:
        sys.exit("GROQ_API_KEY is not set in backend/.env")
    ocr = make_ocr(settings.tesseract_cmd)
    if ocr is None:
        print("warning: Tesseract not found; scanned pages will be read from images")
    extractor = GroqExtractor(make_client(settings), settings)
    cases = {case.id: case for case in build_cases()}

    jobs = QUICK if args.quick else [(cid, v) for cid in cases for v in VARIANTS]
    if args.only:
        jobs = [(cid, v) for cid, v in jobs if cid in args.only]
    runs = [(cid, v, 1) for cid, v in jobs]
    if args.repeat > 1:
        runs += [(cid, v, r) for cid, v in REPEATED for r in range(2, args.repeat + 1)]

    folder = RESULTS / args.tag
    folder.mkdir(parents=True, exist_ok=True)
    todo = [(c, v, r) for c, v, r in runs if not (folder / f"{c}__{v}__r{r}.json").exists()]
    print(f"{len(runs) - len(todo)} already done, {len(todo)} to read")
    for number, (cid, variant, repeat) in enumerate(todo, start=1):
        case = cases[cid]
        content = (DOCS / f"{cid}__{variant}.pdf").read_bytes()
        copy_type = "digital" if variant == "digital" else "scanned"
        result = run_document(content, case.kind, copy_type, settings=settings, extractor=extractor, ocr=ocr)
        result.update(case=cid, variant=variant, repeat=repeat)
        (folder / f"{cid}__{variant}__r{repeat}.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
        status = result.get("error") or f"{result.get('method')} ok"
        print(f"[{number}/{len(todo)}] {cid} {variant} r{repeat}: {status}", flush=True)
        time.sleep(args.pause)


def report(args: argparse.Namespace) -> None:
    from evaluation.report import write_report

    path = REPORTS / f"accuracy_evaluation_{date.today().isoformat()}.html"
    write_report(RESULTS / args.tag, DOCS, path, RESULTS / args.baseline if args.baseline else None)
    print(f"report: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m evaluation", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("generate")
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--quick", action="store_true", help="10 documents across types and scan levels")
    run_parser.add_argument("--repeat", type=int, default=1, help="read 5 chosen documents this many times")
    run_parser.add_argument("--only", nargs="*", help="case ids, e.g. lab01 rx02")
    run_parser.add_argument("--pause", type=float, default=8, help="seconds between documents (provider limit)")
    run_parser.add_argument("--tag", default="current", help="results folder name, e.g. a prompt version")
    report_parser = sub.add_parser("report")
    report_parser.add_argument("--tag", default="current")
    report_parser.add_argument("--baseline", help="an earlier results folder to compare with, e.g. current")
    args = parser.parse_args()
    if args.command == "generate":
        generate()
    elif args.command == "run":
        run(args)
    else:
        report(args)


if __name__ == "__main__":
    main()
