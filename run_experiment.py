"""
Main experiment runner for A11yAgents.

Compares three conditions on the same HTML snippets:
  A. Axe            (rule engine baseline, no LLM)
  B. Persona-LLM    (persona prompt, no tools)
  C. Persona-Agent  (persona prompt + specialized tools)

Corpus layout (produced by build_corpus.py + fetch_axe_fixtures.py +
build_handauthored.py):
    corpus1/<persona>/<wcag>/<expected>/<id>.html
    corpus1/<persona>/<wcag>/<expected>/<id>.json

Each HTML is evaluated under all three conditions × N repetitions.
Results saved as JSONL for easy downstream analysis.

python run_experiment.py --corpus corpus1 --repetitions 3 --output results/experiment_results.jsonl

"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from conditions.condition_a_axe import AxeCondition
from conditions.condition_b_persona_llm import PersonaLLMCondition
from conditions.condition_c_persona_agent import PersonaAgentCondition

load_dotenv()


# --------------------------------------------------------------------------- #
#  Corpus loading                                                              #
# --------------------------------------------------------------------------- #

def load_corpus_from_folders(corpus_root):
    """
    Walk the corpus tree and yield one record per HTML file.

    Each record:
        {
            "snippet_id": <id from filename>,
            "html": <file contents>,
            "persona": <folder name>,
            "wcag_criterion": <folder name>,
            "expected": "passed" | "failed" | "inapplicable",
            "metadata": <sibling .json contents>,
            "html_path": <path for logging>,
        }
    """
    corpus_root = Path(corpus_root)
    if not corpus_root.exists():
        raise FileNotFoundError(f"Corpus root not found: {corpus_root}")

    records = []
    for persona_dir in sorted(corpus_root.iterdir()):
        if not persona_dir.is_dir():
            continue
        persona = persona_dir.name

        for wcag_dir in sorted(persona_dir.iterdir()):
            if not wcag_dir.is_dir():
                continue
            wcag = wcag_dir.name

            for bucket in ("passed", "failed", "inapplicable"):
                bucket_dir = wcag_dir / bucket
                if not bucket_dir.exists():
                    continue

                for html_path in sorted(bucket_dir.glob("*.html")):
                    snippet_id = html_path.stem
                    json_path = bucket_dir / f"{snippet_id}.json"

                    html = html_path.read_text(encoding="utf-8", errors="replace")
                    metadata = {}
                    if json_path.exists():
                        try:
                            metadata = json.loads(
                                json_path.read_text(encoding="utf-8")
                            )
                        except json.JSONDecodeError:
                            metadata = {"_parse_error": "invalid json"}

                    records.append({
                        "snippet_id": snippet_id,
                        "html": html,
                        "persona": persona,
                        "wcag_criterion": wcag,
                        "expected": bucket,
                        "metadata": metadata,
                        "html_path": str(html_path),
                    })

                # Also pick up .svg / .xml if present (ACT has a few)
                for other_ext in ("*.svg", "*.xml"):
                    for content_path in sorted(bucket_dir.glob(other_ext)):
                        snippet_id = content_path.stem
                        json_path = bucket_dir / f"{snippet_id}.json"
                        content = content_path.read_text(
                            encoding="utf-8", errors="replace"
                        )
                        metadata = {}
                        if json_path.exists():
                            try:
                                metadata = json.loads(
                                    json_path.read_text(encoding="utf-8")
                                )
                            except json.JSONDecodeError:
                                metadata = {"_parse_error": "invalid json"}
                        records.append({
                            "snippet_id": snippet_id,
                            "html": content,
                            "persona": persona,
                            "wcag_criterion": wcag,
                            "expected": bucket,
                            "metadata": metadata,
                            "html_path": str(content_path),
                            "content_type": content_path.suffix.lstrip("."),
                        })
    return records


# --------------------------------------------------------------------------- #
#  Result IO                                                                   #
# --------------------------------------------------------------------------- #

def append_result(result, output_path):
    with open(output_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(result, default=str) + "\n")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def already_run(output_path):
    """
    Return set of (snippet_id, condition, persona, repetition) tuples
    already recorded, so a partial run can be resumed without re-doing work.
    """
    done = set()
    if not os.path.exists(output_path):
        return done
    with open(output_path, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "error" in r and not r.get("evaluation"):
                # Failed row that we may want to retry. Keep it done to avoid
                # infinite loops; user can delete rows to force retry.
                pass
            key = (
                r.get("snippet_id"),
                r.get("condition"),
                r.get("persona"),
                r.get("repetition"),
            )
            if all(k is not None for k in (key[0], key[1], key[3])):
                done.add(key)
    return done


# --------------------------------------------------------------------------- #
#  Experiment                                                                  #
# --------------------------------------------------------------------------- #

CONDITION_NAMES = {
    "A": "axe",
    "B": "persona_llm",
    "C": "persona_agent",
}


def run_experiment(corpus_root, output_path, repetitions, limit, resume):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("FATAL: OPENAI_API_KEY not set.", file=sys.stderr)
        return 2

    print("=" * 70)
    print("A11yAgents evaluation")
    print("=" * 70)

    print(f"Loading corpus from {corpus_root}/ ...")
    corpus = load_corpus_from_folders(corpus_root)
    if limit:
        corpus = corpus[:limit]
    print(f"  {len(corpus)} snippets loaded")

    done = already_run(output_path) if resume else set()
    if resume and done:
        print(f"  {len(done)} evaluations already recorded (resuming)")

    print("Instantiating conditions ...")
    cond_a = AxeCondition()
    cond_b = PersonaLLMCondition(api_key)
    cond_c = PersonaAgentCondition(api_key)
    conditions = [
        ("A", "axe", cond_a),
        ("B", "persona_llm", cond_b),
        ("C", "persona_agent", cond_c),
    ]

    total = len(corpus) * len(conditions) * repetitions
    completed = 0
    skipped = 0
    print(f"Total evaluations to run: {total}")
    print()

    for snippet in corpus:
        sid = snippet["snippet_id"]
        html = snippet["html"]
        persona = snippet["persona"]
        wcag = snippet["wcag_criterion"]
        expected = snippet["expected"]

        print(f"[{sid}] persona={persona}, wcag={wcag}, expected={expected}")

        for cond_key, cond_name, cond_obj in conditions:
            for rep in range(repetitions):
                key = (sid, cond_name, persona, rep)
                if key in done:
                    skipped += 1
                    continue

                try:
                    result = cond_obj.evaluate(html, persona)
                except Exception as e:
                    result = {
                        "evaluation": {
                            "label": "error",
                            "severity": "N/A",
                            "issues": [],
                            "overall_assessment": f"Uncaught exception: {e}",
                        },
                        "metadata": {"error": str(e)},
                    }

                row = {
                    "snippet_id": sid,
                    "condition": cond_name,
                    "condition_key": cond_key,
                    "persona": persona,
                    "wcag_criterion": wcag,
                    "expected": expected,
                    "repetition": rep,
                    "timestamp": now_iso(),
                    "html_path": snippet["html_path"],
                    "corpus_metadata": snippet["metadata"],
                    **result,
                }
                append_result(row, output_path)
                completed += 1
                predicted = result.get("evaluation", {}).get("label", "?")
                print(
                    f"  {cond_name} rep {rep + 1}/{repetitions}: "
                    f"predicted={predicted}, "
                    f"progress={completed}/{total - skipped}"
                )

    print()
    print("=" * 70)
    print(f"Done. New evaluations: {completed}. Skipped (resumed): {skipped}.")
    print(f"Results: {output_path}")
    print("=" * 70)
    return 0


# --------------------------------------------------------------------------- #
#  CLI                                                                         #
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(description="Run the A11yAgents experiment.")
    parser.add_argument(
        "--corpus", default="corpus1",
        help="Corpus root directory (default: corpus1)",
    )
    parser.add_argument(
        "--output", default="results/experiment_results.jsonl",
        help="Output JSONL path (default: results/experiment_results.jsonl)",
    )
    parser.add_argument(
        "--repetitions", type=int, default=3,
        help="Number of repetitions per (snippet, condition) (default: 3)",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Only evaluate the first N snippets (for smoke tests)",
    )
    parser.add_argument(
        "--no-resume", action="store_true",
        help="Ignore existing results file and re-run everything.",
    )
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    return run_experiment(
        corpus_root=args.corpus,
        output_path=args.output,
        repetitions=args.repetitions,
        limit=args.limit,
        resume=not args.no_resume,
    )


if __name__ == "__main__":
    sys.exit(main())
