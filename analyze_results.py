#!/usr/bin/env python3
"""
analyze_results.py

Analysis script for AgentA11y experiment results.

MULTI-MODEL VERSION. Every breakdown now carries a `model` dimension, so
result files from gpt-4o, claude-sonnet-4-6, and claude-opus-4-8 can be
concatenated and analyzed together without collapsing into one another.

Usage:
    python analyze_results.py results/results_gpt4o.jsonl
    python analyze_results.py results/results_gpt4o.jsonl results/results_sonnet46.jsonl results/results_opus48.jsonl
    python analyze_results.py results/*.jsonl --model claude-opus-4-8

Produces:
  - Verdict distribution per (model, condition, expected)
  - Agreement matrix per (model, condition, persona) vs expected ground truth
  - Cross-model agreement summary per condition
  - Tool call frequency per (model, persona)
  - Tool trace analysis IF present in the data (rich):
      - Per-tool timing distributions
      - Per-tool error rate
      - Per-tool output size stats
  - Falls back gracefully if tool_trace is missing (surface analysis only)

The script prints to stdout and writes CSVs to results/analysis/.
"""

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median


# --------------------------------------------------------------------------- #
#  Data loading                                                                #
# --------------------------------------------------------------------------- #

def row_model(r):
    """
    Resolve the model for a row. Condition A rows are model-independent and
    are labelled "n/a". Rows written by the pre-multi-model runner have no
    model field at all; treat those as gpt-4o.
    """
    m = r.get("model") or r.get("metadata", {}).get("model")
    if m:
        return m
    if r.get("condition") == "axe":
        return "n/a"
    return "gpt-4o"


def load_results(paths):
    """Yield one dict per row across all given files, skip malformed lines."""
    rows = []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError as e:
                    print(
                        f"WARN: skipping malformed line {lineno} in {path}: {e}",
                        file=sys.stderr,
                    )
                    continue
                r["_model"] = row_model(r)
                r["_source_file"] = str(path)
                rows.append(r)
    return rows


def dedupe(rows):
    """
    Drop duplicate (snippet, condition, persona, repetition, model) rows,
    keeping the last occurrence. Useful when concatenating files that share
    Condition A rows.
    """
    seen = {}
    for r in rows:
        key = (
            r.get("snippet_id"),
            r.get("condition"),
            r.get("persona"),
            r.get("repetition"),
            r["_model"],
        )
        seen[key] = r
    return list(seen.values())


# --------------------------------------------------------------------------- #
#  Verdict analysis                                                            #
# --------------------------------------------------------------------------- #

def verdict_distribution(rows):
    """Table: (model, condition, expected) -> {predicted -> count}."""
    dist = defaultdict(Counter)
    for r in rows:
        key = (r["_model"], r.get("condition"), r.get("expected"))
        pred = r.get("evaluation", {}).get("label")
        dist[key][pred] += 1
    return dist


def print_verdict_table(dist):
    print("=" * 86)
    print("VERDICT DISTRIBUTION")
    print("=" * 86)
    print(f"{'model':<20} {'condition':<15} {'expected':<15} "
          f"{'predicted':<12} {'count':>6}")
    print("-" * 86)
    for (model, cond, exp), counter in sorted(dist.items(), key=lambda x: str(x[0])):
        for pred, count in sorted(counter.items(), key=lambda x: -x[1]):
            print(f"{str(model):<20} {str(cond):<15} {str(exp):<15} "
                  f"{str(pred):<12} {count:>6}")
    print()


def agreement_by_persona(rows):
    """
    Fraction of rows where predicted verdict matches expected verdict,
    broken down by (model, condition, persona).
    """
    correct = defaultdict(int)
    total = defaultdict(int)
    for r in rows:
        key = (r["_model"], r.get("condition"), r.get("persona"))
        expected = r.get("expected")
        predicted = r.get("evaluation", {}).get("label")
        if predicted == "error":
            continue
        total[key] += 1
        if predicted == expected:
            correct[key] += 1
    return {k: (correct[k], total[k]) for k in total}


def print_agreement(agr):
    print("=" * 86)
    print("VERDICT AGREEMENT (predicted == expected)")
    print("=" * 86)
    print(f"{'model':<20} {'condition':<15} {'persona':<10} "
          f"{'agree':>8} {'total':>8} {'rate':>8}")
    print("-" * 86)
    for (model, cond, persona) in sorted(agr.keys(), key=lambda k: tuple(map(str, k))):
        correct, total = agr[(model, cond, persona)]
        rate = correct / total if total else 0
        print(f"{str(model):<20} {str(cond):<15} {str(persona):<10} "
              f"{correct:>8} {total:>8} {rate:>8.2%}")
    print()


def cross_model_summary(rows):
    """
    Headline table for the paper: overall accuracy per (model, condition),
    plus an error-row count so silent parse failures are visible.
    """
    correct = defaultdict(int)
    total = defaultdict(int)
    errors = defaultdict(int)
    for r in rows:
        key = (r["_model"], r.get("condition"))
        predicted = r.get("evaluation", {}).get("label")
        if predicted == "error":
            errors[key] += 1
            continue
        total[key] += 1
        if predicted == r.get("expected"):
            correct[key] += 1

    print("=" * 86)
    print("CROSS-MODEL SUMMARY (overall accuracy per model x condition)")
    print("=" * 86)
    print(f"{'model':<20} {'condition':<15} {'agree':>8} {'scored':>8} "
          f"{'rate':>8} {'error_rows':>11}")
    print("-" * 86)
    for key in sorted(set(list(total.keys()) + list(errors.keys())),
                      key=lambda k: tuple(map(str, k))):
        c, t, e = correct[key], total[key], errors[key]
        rate = c / t if t else 0
        print(f"{str(key[0]):<20} {str(key[1]):<15} {c:>8} {t:>8} "
              f"{rate:>8.2%} {e:>11}")
    print()


def inapplicable_breakdown(rows):
    """
    The headline finding is correct identification of inapplicable cases.
    Report it explicitly per (model, condition).
    """
    hits = defaultdict(int)
    total = defaultdict(int)
    for r in rows:
        if r.get("expected") != "inapplicable":
            continue
        key = (r["_model"], r.get("condition"))
        total[key] += 1
        if r.get("evaluation", {}).get("label") == "inapplicable":
            hits[key] += 1

    if not total:
        return

    print("=" * 86)
    print("INAPPLICABLE-CASE IDENTIFICATION")
    print("=" * 86)
    print(f"{'model':<20} {'condition':<15} {'correct':>8} {'total':>8} {'rate':>8}")
    print("-" * 86)
    for key in sorted(total.keys(), key=lambda k: tuple(map(str, k))):
        rate = hits[key] / total[key] if total[key] else 0
        print(f"{str(key[0]):<20} {str(key[1]):<15} "
              f"{hits[key]:>8} {total[key]:>8} {rate:>8.2%}")
    print()


def repetition_variance(rows):
    """
    Anthropic has no `seed` parameter, so Claude runs are less controlled
    than the OpenAI runs. Quantify it: for each (model, condition, snippet,
    persona), how often do the N repetitions disagree with each other?
    """
    groups = defaultdict(list)
    for r in rows:
        if r.get("condition") == "axe":
            continue
        key = (r["_model"], r.get("condition"), r.get("snippet_id"),
               r.get("persona"))
        groups[key].append(r.get("evaluation", {}).get("label"))

    unstable = defaultdict(int)
    counted = defaultdict(int)
    for (model, cond, _, _), labels in groups.items():
        if len(labels) < 2:
            continue
        counted[(model, cond)] += 1
        if len(set(labels)) > 1:
            unstable[(model, cond)] += 1

    if not counted:
        return

    print("=" * 86)
    print("REPETITION INSTABILITY (repetitions of the same item disagreeing)")
    print("=" * 86)
    print(f"{'model':<20} {'condition':<15} {'unstable':>9} {'items':>8} {'rate':>8}")
    print("-" * 86)
    for key in sorted(counted.keys(), key=lambda k: tuple(map(str, k))):
        rate = unstable[key] / counted[key] if counted[key] else 0
        print(f"{str(key[0]):<20} {str(key[1]):<15} "
              f"{unstable[key]:>9} {counted[key]:>8} {rate:>8.2%}")
    print()


# --------------------------------------------------------------------------- #
#  Surface tool analysis                                                       #
# --------------------------------------------------------------------------- #

def tool_call_frequency(rows):
    """Per (model, persona) counter of tool names in tools_called lists."""
    per_key = defaultdict(Counter)
    zero_call_rows = defaultdict(int)
    total_c_rows = defaultdict(int)

    for r in rows:
        if r.get("condition") != "persona_agent":
            continue
        key = (r["_model"], r.get("persona"))
        total_c_rows[key] += 1
        tools = r.get("metadata", {}).get("tools_called", [])
        if not tools:
            zero_call_rows[key] += 1
        for tool in tools:
            per_key[key][tool] += 1
    return per_key, zero_call_rows, total_c_rows


def print_tool_frequency(per_key, zero_calls, totals):
    print("=" * 86)
    print("TOOL CALL FREQUENCY (Condition C only)")
    print("=" * 86)
    for key in sorted(per_key, key=lambda k: tuple(map(str, k))):
        model, persona = key
        zc = zero_calls.get(key, 0)
        tot = totals.get(key, 0)
        pct = zc / tot if tot else 0
        print(f"\n{model} / {persona}: {tot} rows total, "
              f"{zc} zero-tool rows ({pct:.1%})")
        for tool, count in per_key[key].most_common():
            print(f"  {tool}: {count}")
    print()
    print("NOTE: a high zero-tool rate for one model and not another usually")
    print("means the tool schema conversion failed for that provider, not")
    print("that the model chose not to call tools. Check llm_client.py.")
    print()


# --------------------------------------------------------------------------- #
#  Deep tool analysis (requires tool_trace field)                              #
# --------------------------------------------------------------------------- #

def has_tool_trace(rows):
    """Detect whether ANY row has the tool_trace field."""
    for r in rows:
        if r.get("metadata", {}).get("tool_trace"):
            return True
    return False


def per_tool_stats(rows):
    """
    Aggregate per-tool statistics from tool_trace entries, keyed by
    (model, tool_name).
    """
    tools = defaultdict(lambda: {
        "calls": 0,
        "errors": 0,
        "elapsed": [],
        "output_sizes": [],
        "truncated_count": 0,
        "personas_using": set(),
    })

    for r in rows:
        if r.get("condition") != "persona_agent":
            continue
        persona = r.get("persona")
        model = r["_model"]
        trace = r.get("metadata", {}).get("tool_trace", [])
        for call in trace:
            t = tools[(model, call.get("name"))]
            t["calls"] += 1
            t["personas_using"].add(persona)
            if call.get("error"):
                t["errors"] += 1
            elapsed = call.get("elapsed_seconds")
            if isinstance(elapsed, (int, float)):
                t["elapsed"].append(elapsed)
            size = call.get("output_size_bytes")
            if isinstance(size, (int, float)):
                t["output_sizes"].append(size)
            if call.get("output_truncated"):
                t["truncated_count"] += 1
    return tools


def print_per_tool_stats(tools):
    print("=" * 110)
    print("PER-TOOL STATISTICS (from tool_trace)")
    print("=" * 110)
    if not tools:
        print("No tool_trace data found in this results file.")
        print()
        return

    header = (
        f"{'model':<20} {'tool':<40} {'calls':>6} {'errs':>5} "
        f"{'mean_s':>7} {'med_s':>7} {'mean_kb':>8} {'trunc':>6}"
    )
    print(header)
    print("-" * len(header))
    for key in sorted(tools, key=lambda k: tuple(map(str, k))):
        model, name = key
        t = tools[key]
        mean_e = mean(t["elapsed"]) if t["elapsed"] else 0
        med_e = median(t["elapsed"]) if t["elapsed"] else 0
        mean_sz = mean(t["output_sizes"]) / 1024 if t["output_sizes"] else 0
        print(
            f"{str(model):<20} {str(name):<40} {t['calls']:>6} {t['errors']:>5} "
            f"{mean_e:>7.2f} {med_e:>7.2f} {mean_sz:>8.1f} "
            f"{t['truncated_count']:>6}"
        )
    print()


# --------------------------------------------------------------------------- #
#  Cost / token accounting                                                     #
# --------------------------------------------------------------------------- #

def token_usage(rows):
    """Sum token usage per (model, condition) where the adapter reported it."""
    agg = defaultdict(lambda: {"in": 0, "out": 0, "rows": 0})
    for r in rows:
        usage = r.get("metadata", {}).get("usage") or {}
        if not usage:
            continue
        key = (r["_model"], r.get("condition"))
        agg[key]["in"] += usage.get("input_tokens") or 0
        agg[key]["out"] += usage.get("output_tokens") or 0
        agg[key]["rows"] += 1

    if not agg:
        return

    print("=" * 86)
    print("TOKEN USAGE")
    print("=" * 86)
    print(f"{'model':<20} {'condition':<15} {'rows':>7} "
          f"{'in_tokens':>13} {'out_tokens':>13}")
    print("-" * 86)
    for key in sorted(agg.keys(), key=lambda k: tuple(map(str, k))):
        a = agg[key]
        print(f"{str(key[0]):<20} {str(key[1]):<15} {a['rows']:>7} "
              f"{a['in']:>13,} {a['out']:>13,}")
    print()


# --------------------------------------------------------------------------- #
#  CSV export                                                                  #
# --------------------------------------------------------------------------- #

def export_csv(rows, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Flat verdict table
    with (out_dir / "verdicts.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "snippet_id", "model", "provider", "condition", "persona",
            "wcag_criterion", "expected", "predicted", "severity",
            "repetition", "iteration_count", "total_time_seconds",
            "num_tool_calls", "num_issues", "input_tokens", "output_tokens",
        ])
        for r in rows:
            md = r.get("metadata", {})
            ev = r.get("evaluation", {})
            usage = md.get("usage") or {}
            w.writerow([
                r.get("snippet_id"),
                r["_model"],
                md.get("provider"),
                r.get("condition"),
                r.get("persona"),
                r.get("wcag_criterion"),
                r.get("expected"),
                ev.get("label"),
                ev.get("severity"),
                r.get("repetition"),
                md.get("iteration_count"),
                md.get("total_time_seconds"),
                len(md.get("tools_called", [])),
                len(ev.get("issues", [])),
                usage.get("input_tokens"),
                usage.get("output_tokens"),
            ])

    # 2. Per-tool-call trace (only rows that have tool_trace)
    trace_rows = []
    for r in rows:
        if r.get("condition") != "persona_agent":
            continue
        trace = r.get("metadata", {}).get("tool_trace", [])
        for call in trace:
            trace_rows.append({
                "snippet_id": r.get("snippet_id"),
                "model": r["_model"],
                "persona": r.get("persona"),
                "wcag_criterion": r.get("wcag_criterion"),
                "expected": r.get("expected"),
                "repetition": r.get("repetition"),
                "tool_name": call.get("name"),
                "iteration": call.get("iteration"),
                "elapsed_seconds": call.get("elapsed_seconds"),
                "output_size_bytes": call.get("output_size_bytes"),
                "output_truncated": call.get("output_truncated"),
                "status": call.get("status"),
                "error": call.get("error"),
            })

    if trace_rows:
        with (out_dir / "tool_calls.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(trace_rows[0].keys()))
            w.writeheader()
            w.writerows(trace_rows)
        print(f"Wrote {out_dir / 'tool_calls.csv'} ({len(trace_rows)} calls)")

    print(f"Wrote {out_dir / 'verdicts.csv'} ({len(rows)} rows)")
    print()


# --------------------------------------------------------------------------- #
#  Main                                                                        #
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("results_paths", type=Path, nargs="+",
                        help="One or more results JSONL files.")
    parser.add_argument(
        "--out-dir", default="results/analysis",
        help="Where to write CSVs (default: results/analysis)",
    )
    parser.add_argument(
        "--model", default=None,
        help="Restrict analysis to a single model string.",
    )
    parser.add_argument(
        "--no-dedupe", action="store_true",
        help="Keep duplicate rows across input files.",
    )
    args = parser.parse_args()

    rows = load_results(args.results_paths)
    print(f"Loaded {len(rows)} rows from {len(args.results_paths)} file(s)\n")

    if not args.no_dedupe:
        before = len(rows)
        rows = dedupe(rows)
        if before != len(rows):
            print(f"Deduped {before - len(rows)} duplicate rows\n")

    if args.model:
        rows = [r for r in rows if r["_model"] in (args.model, "n/a")]
        print(f"Filtered to model={args.model}: {len(rows)} rows\n")

    models = sorted({r["_model"] for r in rows})
    print(f"Models present: {', '.join(models)}\n")

    rich = has_tool_trace(rows)
    print(f"Rich tool_trace present: {rich}")
    if not rich:
        print("  (Surface-level tool analysis only.)")
    print()

    cross_model_summary(rows)
    inapplicable_breakdown(rows)
    repetition_variance(rows)

    dist = verdict_distribution(rows)
    print_verdict_table(dist)

    agr = agreement_by_persona(rows)
    print_agreement(agr)

    freq, zero_calls, totals = tool_call_frequency(rows)
    print_tool_frequency(freq, zero_calls, totals)

    if rich:
        print_per_tool_stats(per_tool_stats(rows))

    token_usage(rows)

    export_csv(rows, args.out_dir)


if __name__ == "__main__":
    main()
