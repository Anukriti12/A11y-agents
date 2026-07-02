"""
Condition A: Axe (rule-based baseline)

Runs Deque's axe-core rule engine against the HTML. No LLM, no persona.

Filtering: axe reports violations across ALL WCAG criteria it knows about.
This wrapper filters the reported violations to just the criteria the
current persona evaluates, so we compare like-with-like against the
Persona-LLM and Persona-Agent conditions.

Filtering requires each violation's `tags` field (which contains WCAG
level tags like "wcag2aa", "wcag211"). Your current axe_core_agent.py
strips tags from its formatted output. This wrapper:
  - filters IF tags are present in the output (defensive)
  - degrades to unfiltered evaluation and prints a warning otherwise

To enable filtering, apply this one-line patch to tools/axe_core_agent.py
inside the formatted_violations.append({...}) block:

    formatted_violations.append({
        "id": violation.get("id"),
        "impact": violation.get("impact"),
        "description": violation.get("description"),
        "help": violation.get("help"),
        "helpUrl": violation.get("helpUrl"),
        "tags": violation.get("tags", []),      # <-- ADD THIS LINE
        "nodes": [ ... ]
    })

Uniform interface across all three conditions:
    condition.evaluate(html, persona) -> {"evaluation": ..., "metadata": ...}
"""

import os
import sys
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools.axe_core_agent import AxeCoreAgent


# Persona to WCAG criteria mapping. Matches the locked matrix in personas/.
PERSONA_CRITERIA = {
    "ade":     ["2.1.1", "2.2.1", "2.4.3", "2.4.7", "2.5.5"],
    "elias":   ["1.3.5", "1.4.3", "1.4.12", "2.2.2", "2.4.8"],
    "ian":     ["1.3.1", "2.2.2", "2.4.6", "3.1.4", "3.1.5"],
    "lakshmi": ["1.1.1", "1.3.1", "2.1.1", "2.4.1", "4.1.2"],
    "sophie":  ["2.2.1", "2.4.8", "3.1.4", "3.3.1", "3.3.2"],
    "stefan":  ["1.4.12", "2.2.2", "2.4.5", "2.4.6", "3.1.4"],
}


def _criterion_to_tag(criterion):
    """Convert '2.1.1' to axe tag 'wcag211'."""
    return "wcag" + criterion.replace(".", "")


class AxeCondition:
    """Baseline rule-engine evaluation. No persona, no LLM."""

    def __init__(self):
        # One shared AxeCoreAgent - axe-core loaded once per session,
        # driver spins up per call regardless.
        self.axe = AxeCoreAgent()
        self._warned_no_tags = False

    def evaluate(self, html, persona):
        start = time.time()
        try:
            axe_result = self.axe.execute(html)
            all_violations = axe_result.get("violations", [])

            criteria = PERSONA_CRITERIA.get(persona)
            filtered, was_filtered = self._filter_by_criteria(
                all_violations, criteria
            )

            issues = self._format_issues(filtered)
            label, severity = self._label_and_severity(issues)

            return {
                "evaluation": {
                    "label": label,
                    "severity": severity,
                    "issues": issues,
                    "overall_assessment": axe_result.get("summary", ""),
                },
                "metadata": {
                    "tools_called": ["axe-core"],
                    "iteration_count": 1,
                    "total_time_seconds": round(time.time() - start, 2),
                    "wcag_criteria_filter": criteria,
                    "filter_applied": was_filtered,
                    "unfiltered_violation_count": len(all_violations),
                    "filtered_violation_count": len(filtered),
                },
            }
        except Exception as e:
            return {
                "evaluation": {
                    "label": "error",
                    "severity": "N/A",
                    "issues": [],
                    "overall_assessment": f"Axe failed: {e}",
                },
                "metadata": {
                    "tools_called": ["axe-core"],
                    "iteration_count": 1,
                    "total_time_seconds": round(time.time() - start, 2),
                    "error": str(e),
                },
            }

    def _filter_by_criteria(self, violations, criteria):
        """
        Filter axe violations to only those tagged with one of `criteria`.
        Returns (filtered_list, was_actually_filtered).
        If violations don't carry a `tags` field, returns the full list
        and warns once per run.
        """
        if not criteria or not violations:
            return violations, False

        has_tags = any("tags" in v for v in violations)

        if not has_tags:
            if not self._warned_no_tags:
                print(
                    "  [Condition A warning] axe output has no `tags` field. "
                    "Running unfiltered baseline. To enable criterion "
                    "filtering, patch tools/axe_core_agent.py per the "
                    "docstring in this file.",
                    file=sys.stderr,
                )
                self._warned_no_tags = True
            return violations, False

        allowed_tags = {_criterion_to_tag(c) for c in criteria}
        filtered = [
            v for v in violations
            if any(tag in allowed_tags for tag in v.get("tags", []))
        ]
        return filtered, True

    def _format_issues(self, violations):
        issues = []
        for v in violations:
            wcag_tags = [
                t for t in v.get("tags", []) if "wcag" in t.lower()
            ]
            nodes = v.get("nodes", [])
            evidence = (
                f"axe rule '{v.get('id')}' failed on {len(nodes)} element(s)"
            )
            if nodes:
                evidence += f". Example: {nodes[0].get('html', '')[:100]}"
            issues.append({
                "wcag": ", ".join(wcag_tags) if wcag_tags else "Unknown",
                "description": v.get("description", ""),
                "evidence": evidence,
                "recommendation": v.get("help", ""),
                "axe_impact": v.get("impact", "unknown"),
                "affected_elements": len(nodes),
            })
        return issues

    def _label_and_severity(self, issues):
        if not issues:
            return "passed", "N/A"
        impacts = [i.get("axe_impact", "unknown") for i in issues]
        for level in ("critical", "serious", "moderate", "minor"):
            if level in impacts:
                return "failed", level
        return "failed", "moderate"


if __name__ == "__main__":
    import json
    cond = AxeCondition()
    result = cond.evaluate(
        "<html><body><img src='x.jpg'><button></button></body></html>",
        persona="lakshmi",
    )
    print(json.dumps(result, indent=2))
    assert result["evaluation"]["label"] in ("failed", "passed", "error")
    print("\nOK")