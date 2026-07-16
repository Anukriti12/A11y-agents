"""
Axe-Core Tool Agent — BASELINE CONDITION for the A11yAgents study.

This agent runs Deque's axe-core engine against an HTML page and returns
the full set of violations. It is the BASELINE condition for comparison
against the persona-grounded LLM condition and the generic LLM condition.

Unlike the persona-grounded agents, this is NOT a tool. It is a complete
evaluator that produces verdicts directly from the rule engine, without
any LLM involvement.

Key features:
  - Downloads axe-core 4.8.2 from CDN once per session
  - Runs against headless Chrome via Selenium
  - Optional wcag_criteria filter so the baseline can be restricted to
    the same WCAG criteria a persona evaluates (apples-to-apples)
  - Returns a structured violations report with WCAG tags preserved
"""

import time
import urllib.request
import ssl

from selenium import webdriver
from selenium.webdriver.chrome.options import Options


# WCAG criterion to axe-core tag mapping. Axe tags use the form
# "wcag<level><sc>", e.g. "wcag211" for 2.1.1, "wcag143" for 1.4.3.
# Older axe versions also emit "wcag2a", "wcag2aa", "wcag21aa" level tags.
def _criterion_to_axe_tag(criterion):
    """Convert '2.1.1' to 'wcag211' (axe-core's tag format)."""
    return "wcag" + criterion.replace(".", "")


class AxeCoreAgent:
    """
    Analyzes HTML for accessibility violations using Deque's axe-core
    rule engine. Used as the baseline condition in the study.
    """

    # Cache the axe-core script across calls in the same Python session.
    _axe_script = None

    AXE_CDN_URL = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.8.2/axe.min.js"

    def __init__(self, wcag_criteria=None):
        """
        Args:
            wcag_criteria: optional list of WCAG criterion strings like
                ['2.1.1', '2.4.7']. If given, only violations tagged with
                one of these criteria are returned. If None, all violations
                are returned (full axe scan).
        """
        self.wcag_criteria = wcag_criteria
        self._ensure_axe_script_loaded()

    def _ensure_axe_script_loaded(self):
        """Download axe-core from CDN once per Python session."""
        if AxeCoreAgent._axe_script is not None:
            return
        req = urllib.request.Request(
            self.AXE_CDN_URL,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        # Bypass cert verification - axe.min.js is a public, well-known
        # script and we just need the bytes. If the network blocks this,
        # the agent should fail loudly during construction, not during eval.
        context = ssl._create_unverified_context()
        with urllib.request.urlopen(req, context=context, timeout=30) as response:
            AxeCoreAgent._axe_script = response.read().decode("utf-8")

    # ------------------------------------------------------------------ #
    #  Main entry point                                                    #
    # ------------------------------------------------------------------ #

    def execute(self, html):
        """
        Run axe-core against the given HTML and return a violations report.

        Returns:
            {
                "summary": short human-readable summary,
                "issues_found": integer total node-level issues,
                "violations": list of {id, impact, description, help,
                                       helpUrl, tags, nodes},
                "filtered_by_criteria": list of WCAG criteria the result
                                        was filtered to, or None,
                "tool_name": "AxeCoreAgent"
            }
        """
        # Wrap snippets in a minimal HTML shell so axe has a document
        if "<html" not in html.lower():
            html = (
                "<!DOCTYPE html><html lang='en'><head><title>Test</title>"
                "</head><body>" + html + "</body></html>"
            )

        driver = self._start_browser()
        try:
            driver.get(f"data:text/html;charset=utf-8,{html}")
            time.sleep(0.5)

            driver.execute_script(AxeCoreAgent._axe_script)

            script = """
            var callback = arguments[arguments.length - 1];
            axe.run().then(results => callback(results))
                     .catch(err => callback({error: err.message}));
            """
            driver.set_script_timeout(15)
            axe_results = driver.execute_async_script(script)

            if "error" in axe_results:
                return {
                    "summary": f"Error running axe-core: {axe_results['error']}",
                    "issues_found": 0,
                    "violations": [],
                    "filtered_by_criteria": self.wcag_criteria,
                    "tool_name": "AxeCoreAgent",
                }

            violations = axe_results.get("violations", [])

            # Optional criterion filter
            if self.wcag_criteria:
                allowed_tags = {_criterion_to_axe_tag(c) for c in self.wcag_criteria}
                violations = [
                    v for v in violations
                    if any(tag in allowed_tags for tag in v.get("tags", []))
                ]

            formatted = []
            for v in violations:
                formatted.append({
                    "id": v.get("id"),
                    "impact": v.get("impact"),
                    "description": v.get("description"),
                    "help": v.get("help"),
                    "helpUrl": v.get("helpUrl"),
                    "tags": v.get("tags", []),
                    "nodes": [
                        {
                            "html": node.get("html"),
                            "target": node.get("target"),
                            "failureSummary": node.get("failureSummary"),
                        }
                        for node in v.get("nodes", [])
                    ],
                })

            total_nodes = sum(len(v["nodes"]) for v in formatted)
            scope = (
                f" (filtered to {len(self.wcag_criteria)} criteria)"
                if self.wcag_criteria else ""
            )
            summary = (
                f"Found {len(formatted)} rule violation(s) affecting "
                f"{total_nodes} element(s){scope}."
            )

            return {
                "summary": summary,
                "issues_found": total_nodes,
                "violations": formatted,
                "filtered_by_criteria": self.wcag_criteria,
                "tool_name": "AxeCoreAgent",
            }

        finally:
            driver.quit()

    def _start_browser(self):
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        return webdriver.Chrome(options=options)


# --------------------------------------------------------------------------- #
#  Tests                                                                       #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    # Test 1: Bad HTML with multiple accessibility issues — full scan
    print("=" * 60)
    print("TEST 1: Bad HTML, full scan (no criteria filter)")
    print("=" * 60)
    bad = """
    <!DOCTYPE html>
    <html>
    <head><title>Bad Page</title></head>
    <body>
        <img src="logo.png" />
        <button></button>
        <div style="color: #777; background-color: #888;">Low contrast</div>
        <div role="button" aria-checked="invalid">Fake Button</div>
    </body>
    </html>
    """
    agent = AxeCoreAgent()
    r = agent.execute(bad)
    print(r["summary"])
    print(f"Violations: {len(r['violations'])}")
    for v in r["violations"][:3]:
        print(f"  - {v['id']} [{v['impact']}] tags={v['tags'][:4]}")
    assert r["issues_found"] > 0
    print("PASS\n")

    # Test 2: Same HTML, filtered to one criterion
    print("=" * 60)
    print("TEST 2: Same HTML, filtered to WCAG 1.4.3 only")
    print("=" * 60)
    agent_filtered = AxeCoreAgent(wcag_criteria=["1.4.3"])
    r = agent_filtered.execute(bad)
    print(r["summary"])
    assert r["filtered_by_criteria"] == ["1.4.3"]
    print("PASS\n")

    # Test 3: Good HTML — no violations expected
    print("=" * 60)
    print("TEST 3: Clean HTML, expect zero violations")
    print("=" * 60)
    good = """
    <!DOCTYPE html>
    <html lang="en">
    <head><title>Good Page</title></head>
    <body>
        <main>
            <h1>Welcome</h1>
            <img src="logo.png" alt="Company Logo" />
            <button type="button">Click Me</button>
            <p style="color: #000; background-color: #fff;">High contrast text</p>
        </main>
    </body>
    </html>
    """
    r = AxeCoreAgent().execute(good)
    print(r["summary"])
    assert r["issues_found"] == 0
    print("PASS\n")

    print("=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
