"""
Condition A: Axe (rule-based baseline)

Runs Deque's axe-core rule engine against the HTML. No LLM, no persona.
Accepts the persona's WCAG criteria list so the baseline is filtered to
the same criteria the Persona-Agent evaluates. Without this filter, the
baseline would report violations for criteria the persona doesn't cover,
inflating baseline issue counts unfairly.

The uniform interface across all three conditions is:
    condition.evaluate(html, persona) -> {"evaluation": ..., "metadata": ...}
"""

import os
import sys
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools.axe_core_agent import AxeCoreAgent


# Persona to WCAG criteria mapping. Matches the locked matrix in personas1/.
PERSONA_CRITERIA = {
    "ade":     ["2.1.1", "2.2.1", "2.4.3", "2.4.7", "2.5.5"],
    "elias":   ["1.3.5", "1.4.3", "1.4.12", "2.2.2", "2.4.8"],
    "ian":     ["1.3.1", "2.2.2", "2.4.6", "3.1.4", "3.1.5"],
    "lakshmi": ["1.1.1", "1.3.1", "2.1.1", "2.4.1", "4.1.2"],
    "sophie":  ["2.2.1", "2.4.8", "3.1.4", "3.3.1", "3.3.2"],
    "stefan":  ["1.4.12", "2.2.2", "2.4.5", "2.4.6", "3.1.4"],
}


class AxeCondition:
    """Baseline rule-engine evaluation. No persona, no LLM."""

    def __init__(self):
        # One AxeCoreAgent per persona so we don't re-download axe-core
        # every call. Each is scoped to the persona's WCAG criteria.
        self.axe_by_persona = {
            persona: AxeCoreAgent(wcag_criteria=criteria)
            for persona, criteria in PERSONA_CRITERIA.items()
        }

    def evaluate(self, html, persona):
        start = time.time()
        try:
            axe = self.axe_by_persona[persona]
            axe_result = axe.execute(html)
            issues = self._format_issues(axe_result.get("violations", []))
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
                    "wcag_criteria_filter": PERSONA_CRITERIA[persona],
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

    def _format_issues(self, violations):
        issues = []
        for v in violations:
            wcag_tags = [t for t in v.get("tags", []) if "wcag" in t.lower()]
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
    assert result["evaluation"]["label"] in ("failed", "passed")
    print("\nOK")
