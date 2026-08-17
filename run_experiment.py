"""
Main experiment runner for A11yAgents / AgentA11y.

Compares five conditions on the same HTML snippets:
  A. Axe            (rule engine baseline, no LLM)
  B. Persona-LLM    (persona prompt, no tools)
  C. Persona-Agent  (persona prompt + specialized tools)
  D. Vanilla-LLM    (generic accessibility prompt, no persona, no tools)
  E. Vanilla-Agent  (generic accessibility prompt, no persona, with all tools)

Conditions D and E complete the 2x2 ablation:

                        no tools               with tools
    no persona    Vanilla-LLM (D)         Vanilla-Agent (E)
    with persona  Persona-LLM (B)         Persona-Agent (C)

MULTI-MODEL VERSION. `--model` selects the LLM backing conditions B-E:
    gpt-4o              (needs OPENAI_API_KEY)
    claude-sonnet-4-6   (needs ANTHROPIC_API_KEY)
    claude-opus-4-8     (needs ANTHROPIC_API_KEY)

Condition A is model-independent. Use --skip-axe on the second and third
model runs to avoid re-running identical axe results.

Corpus layout (produced by build_corpus.py + fetch_axe_fixtures.py +
build_handauthored.py):
    corpus1/<persona>/<wcag>/<expected>/<id>.html
    corpus1/<persona>/<wcag>/<expected>/<id>.json

Each HTML is evaluated under all enabled conditions x N repetitions.
Results saved as JSONL for easy downstream analysis. Every row records the
model, and the resume key includes the model, so multiple models can safely
share one output file.

Examples:
    python run_experiment.py --corpus corpus1 --repetitions 3 --model gpt-4o --output results/results_gpt4o.jsonl
    python run_experiment.py --corpus corpus1 --repetitions 3 --model claude-sonnet-4-6 --skip-axe --output results/results_sonnet46.jsonl
    python run_experiment.py --corpus corpus1 --repetitions 3 --model claude-opus-4-8 --skip-axe --output results/results_opus48.jsonl
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


SUPPORTED_MODELS = ("gpt-4o", "claude-sonnet-4-6", "claude-opus-4-8")


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
    Return set of (snippet_id, condition, persona, repetition, model) tuples
    already recorded, so a partial run can be resumed without re-doing work.

    MODEL IS PART OF THE KEY. Without it, running a second model into the
    same output file would skip every row as already done. Rows written by
    the older single-model version have no "model" field; they are keyed as
    the legacy model name so a pre-existing gpt-4o file still resumes.
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
            model = (
                r.get("model")
                or r.get("metadata", {}).get("model")
                or "gpt-4o"  # legacy rows predate the model field
            )
            key = (
                r.get("snippet_id"),
                r.get("condition"),
                r.get("persona"),
                r.get("repetition"),
                model,
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
    "D": "vanilla_llm",
    "E": "vanilla_agent",
}


def run_experiment(corpus_root, output_path, repetitions, limit, resume,
                   model, skip_axe=False):
    # Announce the model to every downstream module BEFORE importing the
    # conditions, so persona agents constructed at import/instantiation time
    # pick up the right provider.
    os.environ["A11Y_MODEL"] = model

    from llm_client1 import key_env_var
    from conditions.condition_a_axe import AxeCondition
    from conditions.condition_b_persona_llm import PersonaLLMCondition
    from conditions.condition_c_persona_agent import PersonaAgentCondition
    from conditions.condition_d_vanilla_llm import VanillaLLMCondition
    from conditions.condition_e_vanilla_agent import VanillaAgentCondition

    # Resolve API key BEFORE constructing any LLM-backed condition, and
    # BEFORE the skip-axe branch (axe is model-independent but the other
    # conditions all need the key).
    env_var = key_env_var(model)
    api_key = os.environ.get(env_var)
    if not api_key:
        print(f"FATAL: {env_var} not set (required for model '{model}').",
              file=sys.stderr)
        return 2

    print("=" * 70)
    print("AgentA11y evaluation")
    print(f"Model: {model}   Key: {env_var}")
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
    conditions = []
    if skip_axe:
        print("  Condition A (axe) SKIPPED: model-independent, run it once.")
    else:
        conditions.append(("A", "axe", AxeCondition()))
    conditions.append(("B", "persona_llm",   PersonaLLMCondition(api_key, model=model)))
    conditions.append(("C", "persona_agent", PersonaAgentCondition(api_key, model=model)))
    conditions.append(("D", "vanilla_llm",   VanillaLLMCondition(api_key, model=model)))
    conditions.append(("E", "vanilla_agent", VanillaAgentCondition(api_key, model=model)))

    print(f"  Enabled conditions: {', '.join(name for _, name, _ in conditions)}")

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
                # Condition A has no model, but keying it under the current
                # model keeps the resume logic uniform. Use --skip-axe to
                # avoid the duplicate work on later model runs.
                row_model = "n/a" if cond_name == "axe" else model
                key = (sid, cond_name, persona, rep, row_model)
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
                    "model": row_model,
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
    print(f"Done. Model: {model}")
    print(f"New evaluations: {completed}. Skipped (resumed): {skipped}.")
    print(f"Results: {output_path}")
    print("=" * 70)
    return 0


# --------------------------------------------------------------------------- #
#  CLI                                                                         #
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(description="Run the AgentA11y experiment.")
    parser.add_argument(
        "--corpus", default="corpus1",
        help="Corpus root directory (default: corpus1)",
    )
    parser.add_argument(
        "--output", default="results/experiment_results.jsonl",
        help="Output JSONL path (default: results/experiment_results.jsonl)",
    )
    parser.add_argument(
        "--model", default="gpt-4o",
        help=f"LLM for conditions B-E. One of: {', '.join(SUPPORTED_MODELS)}",
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
        "--skip-axe", action="store_true",
        help="Skip Condition A. It is model-independent; run it once only.",
    )
    parser.add_argument(
        "--no-resume", action="store_true",
        help="Ignore existing results file and re-run everything.",
    )
    args = parser.parse_args()

    if args.model not in SUPPORTED_MODELS:
        print(f"WARN: '{args.model}' is not in the tested set "
              f"({', '.join(SUPPORTED_MODELS)}). Continuing anyway.",
              file=sys.stderr)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    return run_experiment(
        corpus_root=args.corpus,
        output_path=args.output,
        repetitions=args.repetitions,
        limit=args.limit,
        resume=not args.no_resume,
        model=args.model,
        skip_axe=args.skip_axe,
    )


if __name__ == "__main__":
    sys.exit(main())