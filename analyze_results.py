#!/usr/bin/env python3
"""
analyze_results.py

Analysis script for A11yAgents experiment results.

Usage:
    python analyze_results.py results/experiment_results.jsonl

Produces:
  - Verdict distribution per (condition, persona, expected)
  - Agreement matrix: Condition C vs expected ground truth
  - Tool call frequency per persona
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

def load_results(path):
    """Yield one dict per row, skip malformed lines."""
    rows = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(
                    f"WARN: skipping malformed line {lineno}: {e}",
                    file=sys.stderr,
                )
    return rows


# --------------------------------------------------------------------------- #
#  Verdict analysis                                                            #
# --------------------------------------------------------------------------- #

def verdict_distribution(rows):
    """Table: (condition, expected) -> {predicted -> count}."""
    dist = defaultdict(Counter)
    for r in rows:
        cond = r.get("condition")
        exp = r.get("expected")
        pred = r.get("evaluation", {}).get("label")
        dist[(cond, exp)][pred] += 1
    return dist


def print_verdict_table(dist):
    print("=" * 70)
    print("VERDICT DISTRIBUTION")
    print("=" * 70)
    print(f"{'condition':<15} {'expected':<15} {'predicted':<12} {'count':>6}")
    print("-" * 70)
    for (cond, exp), counter in sorted(dist.items()):
        for pred, count in sorted(counter.items(), key=lambda x: -x[1]):
            print(f"{cond:<15} {exp:<15} {str(pred):<12} {count:>6}")
    print()


def agreement_by_persona(rows):
    """
    Fraction of rows where predicted verdict matches expected verdict,
    broken down by (condition, persona).
    """
    correct = defaultdict(int)
    total = defaultdict(int)
    for r in rows:
        cond = r.get("condition")
        persona = r.get("persona")
        expected = r.get("expected")
        predicted = r.get("evaluation", {}).get("label")
        if predicted == "error":
            continue
        total[(cond, persona)] += 1
        if predicted == expected:
            correct[(cond, persona)] += 1
    return {k: (correct[k], total[k]) for k in total}


def print_agreement(agr):
    print("=" * 70)
    print("VERDICT AGREEMENT (predicted == expected)")
    print("=" * 70)
    print(f"{'condition':<15} {'persona':<10} {'agree':>8} {'total':>8} {'rate':>8}")
    print("-" * 70)
    by_cond_persona = sorted(agr.keys())
    for (cond, persona) in by_cond_persona:
        correct, total = agr[(cond, persona)]
        rate = correct / total if total else 0
        print(f"{cond:<15} {persona:<10} {correct:>8} {total:>8} {rate:>8.2%}")
    print()


# --------------------------------------------------------------------------- #
#  Surface tool analysis (works on the current data)                           #
# --------------------------------------------------------------------------- #

def tool_call_frequency(rows):
    """Per-persona counter of tool names appearing in tools_called lists."""
    per_persona = defaultdict(Counter)
    zero_call_rows = defaultdict(int)
    total_c_rows = defaultdict(int)

    for r in rows:
        if r.get("condition") != "persona_agent":
            continue
        persona = r.get("persona")
        total_c_rows[persona] += 1
        tools = r.get("metadata", {}).get("tools_called", [])
        if not tools:
            zero_call_rows[persona] += 1
        for tool in tools:
            per_persona[persona][tool] += 1
    return per_persona, zero_call_rows, total_c_rows


def print_tool_frequency(per_persona, zero_calls, totals):
    print("=" * 70)
    print("TOOL CALL FREQUENCY (Condition C only)")
    print("=" * 70)
    for persona in sorted(per_persona):
        zc = zero_calls.get(persona, 0)
        tot = totals.get(persona, 0)
        pct = zc / tot if tot else 0
        print(f"\n{persona}: {tot} rows total, {zc} zero-tool rows ({pct:.1%})")
        for tool, count in per_persona[persona].most_common():
            print(f"  {tool}: {count}")
    print()


# --------------------------------------------------------------------------- #
#  Deep tool analysis (requires tool_trace field, i.e. re-run data)            #
# --------------------------------------------------------------------------- #

def has_tool_trace(rows):
    """Detect whether ANY row has the new tool_trace field."""
    for r in rows:
        if r.get("metadata", {}).get("tool_trace"):
            return True
    return False


def per_tool_stats(rows):
    """
    Aggregate per-tool statistics from tool_trace entries.
    Returns {tool_name: {calls, mean_elapsed, median_elapsed, errors,
                         mean_output_bytes, truncated_count}}
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
        trace = r.get("metadata", {}).get("tool_trace", [])
        for call in trace:
            name = call.get("name")
            t = tools[name]
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
    print("=" * 70)
    print("PER-TOOL STATISTICS (from tool_trace)")
    print("=" * 70)
    if not tools:
        print("No tool_trace data found in this results file.")
        print("Re-run with the enhanced base_agent.py to capture rich traces.")
        print()
        return

    header = (
        f"{'tool':<40} {'calls':>6} {'errs':>5} {'mean_s':>7} "
        f"{'med_s':>7} {'mean_kb':>8} {'trunc':>6}"
    )
    print(header)
    print("-" * len(header))
    for name in sorted(tools):
        t = tools[name]
        mean_e = mean(t["elapsed"]) if t["elapsed"] else 0
        med_e = median(t["elapsed"]) if t["elapsed"] else 0
        mean_sz = (
            mean(t["output_sizes"]) / 1024 if t["output_sizes"] else 0
        )
        print(
            f"{name:<40} {t['calls']:>6} {t['errors']:>5} "
            f"{mean_e:>7.2f} {med_e:>7.2f} {mean_sz:>8.1f} "
            f"{t['truncated_count']:>6}"
        )
    print()


# --------------------------------------------------------------------------- #
#  CSV export                                                                  #
# --------------------------------------------------------------------------- #

def export_csv(rows, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Flat verdict table
    with (out_dir / "verdicts.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "snippet_id", "condition", "persona", "wcag_criterion",
            "expected", "predicted", "severity", "repetition",
            "iteration_count", "total_time_seconds", "num_tool_calls",
            "num_issues",
        ])
        for r in rows:
            md = r.get("metadata", {})
            ev = r.get("evaluation", {})
            w.writerow([
                r.get("snippet_id"),
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
                "persona": r.get("persona"),
                "wcag_criterion": r.get("wcag_criterion"),
                "expected": r.get("expected"),
                "repetition": r.get("repetition"),
                "tool_name": call.get("name"),
                "iteration": call.get("iteration"),
                "elapsed_seconds": call.get("elapsed_seconds"),
                "output_size_bytes": call.get("output_size_bytes"),
                "output_truncated": call.get("output_truncated"),
                "error": call.get("error"),
            })

    if trace_rows:
        with (out_dir / "tool_calls.csv").open("w", newline="") as f:
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
    parser.add_argument("results_path", type=Path)
    parser.add_argument(
        "--out-dir", default="results/analysis",
        help="Where to write CSVs (default: results/analysis)",
    )
    args = parser.parse_args()

    rows = load_results(args.results_path)
    print(f"Loaded {len(rows)} rows from {args.results_path}\n")

    # Which analyses are possible?
    rich = has_tool_trace(rows)
    print(f"Rich tool_trace present: {rich}")
    if not rich:
        print("  (Surface-level tool analysis only. Re-run with the enhanced")
        print("   base_agent.py to capture per-call arguments, output, timing.)")
    print()

    # Verdict analysis (always possible)
    dist = verdict_distribution(rows)
    print_verdict_table(dist)

    agr = agreement_by_persona(rows)
    print_agreement(agr)

    # Surface tool analysis
    freq, zero_calls, totals = tool_call_frequency(rows)
    print_tool_frequency(freq, zero_calls, totals)

    # Deep tool analysis (only if trace present)
    if rich:
        tools = per_tool_stats(rows)
        print_per_tool_stats(tools)

    # CSV export
    export_csv(rows, args.out_dir)


if __name__ == "__main__":
    main()
