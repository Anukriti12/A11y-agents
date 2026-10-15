"""
Run the five conditions on the BARRIER task: "is this page a barrier for
this person?", scored against the specialist labels instead of the WCAG
folder labels. Companion to run_experiment.py, which is left unchanged.

Input: a labels CSV from barrier_study/ground_truth/export_labels.py. Each
row is one (page, persona) pair; the HTML is read from the de-identified
specialist packet copy (P0xx_<persona>.html).

Before the HTML reaches any condition, ACT titles that give away the WCAG
label ("Failed Example 3", "Passed Example 5", ...) are replaced with a
neutral title. 26 of the 54 packet pages carry such a title.

Usage:
    # Print prompts for one row and the run plan, no API calls:
    python run_barrier_experiment.py --dry-run

    python run_barrier_experiment.py --model claude-sonnet-4-6 \
        --output results/barrier/barrier_sonnet46.jsonl
    python run_barrier_experiment.py --model gpt-5.2 --conditions B,C,D,E \
        --output results/barrier/barrier_gpt52.jsonl

    python score_barrier_results.py results/barrier/barrier_sonnet46.jsonl
"""

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent
STUDY = ROOT / "barrier_study"
DEFAULT_LABELS = STUDY / "ground_truth" / "barrier_labels_v0.csv"

LEAKY_TITLE = re.compile(
    r"<title>\s*(passed|failed|inapplicable)\s+example[^<]*</title>", re.IGNORECASE
)


def sanitize(html):
    """Remove WCAG-label giveaways from the page. Returns (html, changed)."""
    clean, n = LEAKY_TITLE.subn("<title>Example page</title>", html)
    return clean, n > 0


def load_rows(labels_csv):
    rows = []
    for r in csv.DictReader(open(labels_csv, encoding="utf-8")):
        page_path = STUDY / r["page_file"]
        html = page_path.read_text(encoding="utf-8", errors="replace")
        html, sanitized = sanitize(html)
        rows.append({**r, "html": html, "sanitized": sanitized})
    return rows


def already_run(output_path):
    done = set()
    if output_path.exists():
        for line in open(output_path, encoding="utf-8"):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("evaluated") != "error":
                done.add((r["page_id"], r["condition"], r["repetition"], r["model"]))
    return done


def dry_run(rows, condition_keys, repetitions):
    from barrier_task import prompts
    r = rows[0]
    print(f"{len(rows)} rows, {sum(x['sanitized'] for x in rows)} with leaky titles neutralized")
    per_row = sum(1 if k == "A" else repetitions for k in condition_keys)
    print(f"Planned evaluations: {len(rows)} rows x {per_row} per row "
          f"(axe once, others x{repetitions}) = {len(rows) * per_row}")
    print(f"\nExample row: {r['page_id']} ({r['persona']}), specialist label = {r['label']}")
    print("\n--- persona system prompt (B; C adds the tool note) ---")
    print(prompts.persona_system_prompt(r["persona"], with_tools=False))
    print("\n--- vanilla system prompt (D; E adds the tool note) ---")
    print(prompts.vanilla_system_prompt(r["persona"], with_tools=False))
    print("\n--- user message ---")
    print(prompts.user_message(r["html"]))


def main():
    ap = argparse.ArgumentParser(description="Run the barrier-task experiment.")
    ap.add_argument("--labels", default=str(DEFAULT_LABELS))
    ap.add_argument("--model", default="gpt-4o")
    ap.add_argument("--conditions", default="A,B,C,D,E",
                    help="Comma-separated condition keys (A is model-independent)")
    ap.add_argument("--repetitions", type=int, default=3)
    ap.add_argument("--personas", default=None,
                    help="Comma-separated subset, e.g. sophie,stefan")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--output", default=None)
    ap.add_argument("--no-resume", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print prompts and the run plan; make no API calls")
    args = ap.parse_args()

    rows = load_rows(args.labels)
    if args.personas:
        keep = set(args.personas.split(","))
        rows = [r for r in rows if r["persona"] in keep]
    if args.limit:
        rows = rows[:args.limit]
    condition_keys = [k.strip().upper() for k in args.conditions.split(",") if k.strip()]

    if args.dry_run:
        dry_run(rows, condition_keys, args.repetitions)
        return 0

    os.environ["A11Y_MODEL"] = args.model
    from llm_client1 import key_env_var
    from barrier_task.conditions import CONDITIONS

    api_key = None
    if any(k != "A" for k in condition_keys):
        env_var = key_env_var(args.model)
        api_key = os.environ.get(env_var)
        if not api_key:
            print(f"FATAL: {env_var} not set (required for model '{args.model}').", file=sys.stderr)
            return 2

    safe_model = re.sub(r"[^A-Za-z0-9.-]", "_", args.model)
    output = Path(args.output or ROOT / "results" / "barrier" / f"barrier_{safe_model}.jsonl")
    output.parent.mkdir(parents=True, exist_ok=True)
    done = set() if args.no_resume else already_run(output)

    conditions = []
    for key in condition_keys:
        name, cls = CONDITIONS[key]
        print(f"Instantiating {key}:{name} ...")
        conditions.append((key, name, cls() if key == "A" else cls(api_key, model=args.model)))

    total = len(rows) * sum(1 if k == "A" else args.repetitions for k, _, _ in conditions)
    n = 0
    print(f"{len(rows)} rows from {args.labels}; {total} evaluations -> {output}")
    for row in rows:
        for key, name, cond in conditions:
            reps = 1 if key == "A" else args.repetitions  # axe is deterministic
            for rep in range(reps):
                n += 1
                row_model = "n/a" if key == "A" else args.model
                if (row["page_id"], name, rep, row_model) in done:
                    continue
                try:
                    result = cond.evaluate(row["html"], row["persona"])
                except Exception as e:
                    result = {"evaluation": {"label": "error", "rationale": f"Uncaught: {e}"},
                              "metadata": {"error": str(e)}}
                ev = result.get("evaluation", {})
                record = {
                    "task": "barrier",
                    "page_id": row["page_id"],
                    "persona": row["persona"],
                    "condition": name,
                    "condition_key": key,
                    "model": row_model,
                    "repetition": rep,
                    "expected": row["label"],
                    "evaluated": ev.get("label", "error"),
                    "correct": ev.get("label") == row["label"],
                    "label_version": row.get("label_version", ""),
                    "wcag": row["wcag"],
                    "wcag_label": row["wcag_label"],
                    "snippet_id": row["snippet_id"],
                    "html_sanitized": row["sanitized"],
                    "evaluation": ev,
                    "metadata": result.get("metadata", {}),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                with open(output, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, default=str) + "\n")
                mark = "ok " if record["correct"] else "   "
                print(f"[{n}/{total}] {mark}{row['page_id']} {row['persona']:8} {name:14} rep{rep} "
                      f"expected={row['label']:15} got={record['evaluated']}")
    print(f"Done. Results in {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
