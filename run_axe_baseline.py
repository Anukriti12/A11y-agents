"""
Quick axe-only smoke test against a slice of the corpus.

Runs Condition A (axe baseline) only — no LLM calls, no API key needed —
against the first N snippets under a corpus root. Useful for sanity-checking
condition_a_axe.py changes without waiting on the full experiment.

Usage:
    python run_axe_baseline.py                       # first 10 snippets, corpus1
    python run_axe_baseline.py --limit 25
    python run_axe_baseline.py --corpus corpus --limit 5
"""

import argparse
import json
from datetime import datetime, timezone

from conditions.condition_a_axe import AxeCondition
from run_experiment import load_corpus_from_folders


def main():
    parser = argparse.ArgumentParser(description="Run the axe baseline against a corpus slice.")
    parser.add_argument("--corpus", default="corpus1", help="Corpus root directory (default: corpus1)")
    parser.add_argument("--limit", type=int, default=10, help="Number of snippets to run (default: 10)")
    parser.add_argument(
        "--output", default=None,
        help="Optional path to write results as JSONL (one row per snippet)",
    )
    args = parser.parse_args()

    corpus = load_corpus_from_folders(args.corpus)[: args.limit]
    print(f"Running axe baseline against {len(corpus)} snippet(s) from {args.corpus}/\n")

    out_file = open(args.output, "w", encoding="utf-8") if args.output else None

    cond = AxeCondition()
    for snippet in corpus:
        sid = snippet["snippet_id"]
        persona = snippet["persona"]
        expected = snippet["expected"]

        result = cond.evaluate(snippet["html"], persona)
        label = result["evaluation"]["label"]
        severity = result["evaluation"]["severity"]
        issue_count = len(result["evaluation"]["issues"])

        match = "OK" if label == expected or expected == "inapplicable" else "MISMATCH"
        print(
            f"[{sid}] persona={persona} expected={expected} "
            f"-> label={label} severity={severity} issues={issue_count} ({match})"
        )

        if out_file:
            row = {
                "snippet_id": sid,
                "persona": persona,
                "expected": expected,
                "html_path": snippet["html_path"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "match": match == "OK",
                **result,
            }
            out_file.write(json.dumps(row, default=str) + "\n")

    if out_file:
        out_file.close()
        print(f"\nResults written to {args.output}")

    print("\nDone.")


if __name__ == "__main__":
    main()
