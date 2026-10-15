"""
Export specialist barrier labels from the coding sheets into one CSV that
run_barrier_experiment.py and score_barrier_results.py read as ground truth.

Only rows with a filled YOUR LABEL cell are exported, so this can be re-run
as more personas are annotated. WCAG metadata is joined from
reference/selected_pages.csv for analysis only; it is never shown to models.

Usage:
    python barrier_study/ground_truth/export_labels.py
    python barrier_study/ground_truth/export_labels.py --version v1 --out barrier_study/ground_truth/barrier_labels_v1.csv
"""

import argparse
import csv
from pathlib import Path

import openpyxl

STUDY = Path(__file__).resolve().parent.parent
PACKETS = STUDY / "specialist_packets"
SELECTED = STUDY / "reference" / "selected_pages.csv"

VALID_LABELS = {"Barrier", "No-Barrier", "Not-Encountered"}

# Column order on the Labels sheet (row 4 is the header, data starts row 5).
COLS = ["page_id", "persona", "person", "wcag", "page_source", "path",
        "label", "barrier_text", "source_category", "severity",
        "confidence", "notes"]

FIELDS = ["page_id", "persona", "specialist", "label", "severity",
          "confidence", "barrier_text", "source_category", "notes",
          "page_file", "wcag", "wcag_label", "page_source", "snippet_id",
          "label_version"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v0",
                    help="Label version tag written into every row (default v0)")
    ap.add_argument("--out", default=None,
                    help="Output CSV (default barrier_study/ground_truth/barrier_labels_<version>.csv)")
    args = ap.parse_args()
    out = Path(args.out) if args.out else Path(__file__).parent / f"barrier_labels_{args.version}.csv"

    selected = {r["page_id"]: r for r in csv.DictReader(open(SELECTED, encoding="utf-8"))}

    rows, skipped = [], []
    for sheet in sorted(PACKETS.glob("coding_sheet_specialist_*.xlsx")):
        specialist = sheet.stem.rsplit("_", 1)[-1]
        ws = openpyxl.load_workbook(sheet, data_only=True)["Labels"]
        for values in ws.iter_rows(min_row=5, values_only=True):
            r = dict(zip(COLS, values))
            if not r["page_id"]:
                continue
            label = (r["label"] or "").strip()
            if not label:
                continue
            if label not in VALID_LABELS:
                skipped.append((r["page_id"], label))
                continue
            sel = selected.get(r["page_id"], {})
            rows.append({
                "page_id": r["page_id"],
                "persona": r["persona"],
                "specialist": specialist,
                "label": label,
                "severity": r["severity"] or "",
                "confidence": r["confidence"] or "",
                "barrier_text": r["barrier_text"] or "",
                "source_category": r["source_category"] or "",
                "notes": r["notes"] or "",
                "page_file": f"specialist_packets/pages_specialist_{specialist}/{r['page_id']}_{r['persona']}.html",
                "wcag": sel.get("wcag", ""),
                "wcag_label": sel.get("wcag_label", ""),
                "page_source": sel.get("source", ""),
                "snippet_id": sel.get("snippet_id", ""),
                "label_version": args.version,
            })

    rows.sort(key=lambda r: r["page_id"])
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        raise SystemExit(f"{out} already exists; pass a new --version or --out instead of overwriting it.")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    by_persona = {}
    for r in rows:
        by_persona[r["persona"]] = by_persona.get(r["persona"], 0) + 1
    print(f"Wrote {len(rows)} labeled rows to {out}")
    print("  per persona:", by_persona)
    for pid, label in skipped:
        print(f"  skipped {pid}: unrecognized label {label!r}")


if __name__ == "__main__":
    main()
