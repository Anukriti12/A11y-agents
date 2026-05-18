"""
Condition A: axe-core Baseline
Pure automated testing, no LLM
"""

import sys
import os
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools.axe_core_agent import AxeCoreAgent


class AxeCoreBaseline:
    def __init__(self):
        self.axe_agent = AxeCoreAgent()
    
    def evaluate(self, html: str) -> dict:
        start_time = time.time()
        
        try:
            axe_result = self.axe_agent.execute(html)
            issues = self._format_issues(axe_result.get('violations', []))
            label, severity = self._determine_label_and_severity(issues)
            
            evaluation = {
                "label": label,
                "severity": severity,
                "issues": issues,
                "overall_assessment": axe_result.get('summary', 'No summary')
            }
            
            elapsed = time.time() - start_time
            metadata = {
                "tools_called": ["axe-core"],
                "iteration_count": 1,
                "total_time_seconds": round(elapsed, 2)
            }
            
            return {"evaluation": evaluation, "metadata": metadata}
            
        except Exception as e:
            return {
                "evaluation": {
                    "label": "error",
                    "severity": "N/A",
                    "issues": [],
                    "overall_assessment": f"axe-core failed: {str(e)}"
                },
                "metadata": {
                    "tools_called": ["axe-core"],
                    "iteration_count": 1,
                    "total_time_seconds": 0,
                    "error": str(e)
                }
            }
    
    def _format_issues(self, violations: list) -> list:
        issues = []
        
        for violation in violations:
            wcag_tags = [tag for tag in violation.get('tags', []) if 'wcag' in tag.lower()]
            wcag = ', '.join(wcag_tags) if wcag_tags else 'Unknown'
            
            nodes = violation.get('nodes', [])
            num_affected = len(nodes)
            
            evidence = f"axe-core rule '{violation.get('id')}' failed on {num_affected} element(s)"
            if nodes:
                html_snippet = nodes[0].get('html', '')[:100]
                evidence += f". Example: {html_snippet}"
            
            issues.append({
                "wcag": wcag,
                "description": violation.get('description', 'No description'),
                "evidence": evidence,
                "recommendation": violation.get('help', f"Fix {violation.get('id')}"),
                "axe_impact": violation.get('impact', 'unknown'),
                "affected_elements": num_affected
            })
        
        return issues
    
    def _determine_label_and_severity(self, issues: list) -> tuple:
        if len(issues) == 0:
            return ("passed", "N/A")
        
        impact_to_severity = {
            'critical': 'critical',
            'serious': 'serious',
            'moderate': 'moderate',
            'minor': 'minor',
            'unknown': 'moderate'
        }
        
        severity_order = ['critical', 'serious', 'moderate', 'minor']
        impacts = [issue.get('axe_impact', 'unknown') for issue in issues]
        severities = [impact_to_severity.get(imp, 'moderate') for imp in impacts]
        
        severity = 'moderate'
        for sev in severity_order:
            if sev in severities:
                severity = sev
                break
        
        return ("failed", severity)


if __name__ == "__main__":
    import json
    
    baseline = AxeCoreBaseline()
    
    html_bad = "<html><body><img src='test.jpg'><button></button></body></html>"
    result = baseline.evaluate(html_bad)
    
    print("=== CONDITION A TEST ===")
    print(json.dumps(result, indent=2))
    
    assert result['evaluation']['label'] == 'failed'
    print("\n✓ TEST PASSED")