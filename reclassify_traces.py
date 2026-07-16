#!/usr/bin/env python3
"""
reclassify_traces.py

Fixes a subtle mis-classification in the tool_trace field. The base_agent
records status=ok whenever the tool function returned without raising.
But your persona files' execute_tool catches exceptions and returns
{"error": ..., "status": "failed"} as the tool output. The function
returned cleanly, so base_agent labels it "ok" even though the tool
actually failed silently.

This script walks every tool_trace entry, inspects the tool's output
dict, and reclassifies:
  - "ok"                -> "tool_error"       (output has error dict)
  - "ok"                -> "ok_inapplicable"  (tool returned no-work verdict)
  - "ok"                -> "ok"               (real successful analysis)

Writes results/experiment_results_reclassified.jsonl. Leaves the input
file untouched. Prints a summary of what got reclassified per (tool,
new_status).

Usage:
    python reclassify_traces.py results/experiment_results.jsonl
"""

import json
import sys
from collections import Counter
from pathlib import Path


def reclassify_call(call):
    """
    Return (new_status, optional_error_msg) for one tool_trace entry.
    Only reclassifies from "ok"; other statuses pass through unchanged.
    """
    if call.get("status") != "ok":
        return call.get("status"), None

    output = call.get("output")
    if not isinstance(output, dict):
        return "ok", None

    # Truncated output: peek at the head
    if output.get("_truncated"):
        head = output.get("_head", "")
        if '"error"' in head or '"status": "failed"' in head:
            return "tool_error", "error found in truncated output"
        return "ok", None

    # Persona execute_tool exception handler pattern:
    #   {"error": "...", "tool_name": "...", "status": "failed"}
    if isinstance(output.get("error"), str) and output.get("status") == "failed":
        return "tool_error", output["error"][:200]

    # Standalone error dict (tools that return error without status field)
    if isinstance(output.get("error"), str) and "tool_name" in output:
        return "tool_error", output["error"][:200]

    # Legitimate inapplicable short-circuits — tool ran and correctly
    # emitted INAPPLICABLE. Separate label so analysis can slice.
    for key in ("wcag_status", "wcag_135_status", "wcag_222_status",
                "wcag_244_status", "wcag_248_status"):
        v = output.get(key)
        if isinstance(v, str) and v.lower() == "inapplicable":
            return "ok_inapplicable", None

    # Readability tool returns default zeros on no-text pages
    if call.get("name", "").startswith("analyze_readability"):
        if output.get("word_count") == 0:
            return "ok_inapplicable", None

    return "ok", None


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} results/experiment_results.jsonl",
              file=sys.stderr)
        return 2

    in_path = Path(sys.argv[1])
    out_path = in_path.with_name(in_path.stem + "_reclassified.jsonl")

    total_calls = 0
    reclassified = Counter()
    per_tool_final = Counter()

    with in_path.open(encoding="utf-8") as f_in, \
         out_path.open("w", encoding="utf-8") as f_out:
        for line in f_in:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                f_out.write(line + "\n")
                continue

            trace = row.get("metadata", {}).get("tool_trace", [])
            for call in trace:
                total_calls += 1
                original = call.get("status")
                new_status, error_msg = reclassify_call(call)
                if new_status != original:
                    reclassified[(call.get("name"), new_status)] += 1
                    call["status"] = new_status
                    if error_msg:
                        call["reclassified_error"] = error_msg
                per_tool_final[(call.get("name"), call.get("status"))] += 1

            f_out.write(json.dumps(row, default=str) + "\n")

    print(f"Total tool calls: {total_calls}")
    print(f"Reclassifications: {sum(reclassified.values())}")
    print()
    print("Reclassified from ok -> new_status:")
    print(f"  {'tool':<45} {'new_status':<20} {'count':>6}")
    print(f"  {'-'*45} {'-'*20} {'-'*6}")
    for (name, new_status), n in reclassified.most_common():
        print(f"  {str(name):<45} {new_status:<20} {n:>6}")

    print()
    print("Final status counts per tool:")
    print(f"  {'tool':<45} {'status':<20} {'count':>6}")
    print(f"  {'-'*45} {'-'*20} {'-'*6}")
    for (name, status), n in sorted(
        per_tool_final.items(), key=lambda x: (str(x[0][0]), str(x[0][1]))
    ):
        print(f"  {str(name):<45} {str(status):<20} {n:>6}")

    print()
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
