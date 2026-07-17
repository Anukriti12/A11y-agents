"""
Axe-Core Tool Agent
Detects accessibility issues in HTML using the axe-core library.
Used by: Ade, Elias, Ian, Lakshmi, Sophie, Stefan
"""

import time
import urllib.request
import ssl
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

class AxeCoreAgent:
    """
    Analyzes HTML for accessibility issues using Deque's axe-core engine.
    Checks for a wide variety of WCAG violations including:
    1. Color contrast
    2. Missing alt text
    3. ARIA attribute validity
    4. Semantic HTML structure
    """

    # Cache the axe-core script so we only download it once per session
    _axe_script = None

    def __init__(self):
        if not AxeCoreAgent._axe_script:
            # Fetch axe-core from CDN
            url = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.8.2/axe.min.js"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            
            # Create an unverified SSL context to avoid CERTIFICATE_VERIFY_FAILED errors
            context = ssl._create_unverified_context()
            
            with urllib.request.urlopen(req, context=context) as response:
                AxeCoreAgent._axe_script = response.read().decode('utf-8')

    def execute(self, html: str) -> dict:
        """
        Analyzes the given HTML for accessibility issues using axe-core.
        """
        # Ensure the HTML has a basic structure if it's just a snippet
        if "<html" not in html.lower():
            html = f"<!DOCTYPE html><html lang='en'><head><title>Test</title></head><body>{html}</body></html>"

        driver = self._start_browser()
        try:
            # Load the HTML
            driver.get(f"data:text/html;charset=utf-8,{html}")
            time.sleep(0.5)

            # Inject axe-core
            driver.execute_script(self._axe_script)

            # Run axe-core asynchronously
            script = """
            var callback = arguments[arguments.length - 1];
            axe.run().then(results => {
                callback(results);
            }).catch(err => {
                callback({error: err.message});
            });
            """
            
            # Increase script timeout for axe-core to finish
            driver.set_script_timeout(10)
            axe_results = driver.execute_async_script(script)

            if "error" in axe_results:
                return {
                    "summary": f"Error running axe-core: {axe_results['error']}",
                    "issues_found": 0,
                    "tool_name": "AxeCoreAgent",
                    "details": []
                }

            violations = axe_results.get('violations', [])
            total_issues = sum(len(v.get('nodes', [])) for v in violations)

            formatted_violations = []
            for violation in violations:
                formatted_violations.append({
                    "id": violation.get("id"),
                    "impact": violation.get("impact"),
                    "description": violation.get("description"),
                    "help": violation.get("help"),
                    "helpUrl": violation.get("helpUrl"),
                    "tags": violation.get("tags", []),
                    "nodes": [
                        {
                            "html": node.get("html"),
                            "failureSummary": node.get("failureSummary")
                        }
                        for node in violation.get("nodes", [])
                    ]
                })

            summary = f"Found {len(violations)} rule violation(s) affecting {total_issues} element(s)."

            return {
                "summary": summary,
                "issues_found": total_issues,
                "violations": formatted_violations,
                "tool_name": "AxeCoreAgent"
            }

        finally:
            driver.quit()

    def _start_browser(self):
        """Starts a headless Chrome browser."""
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        return webdriver.Chrome(options=options)


# Test cases
if __name__ == "__main__":
    agent = AxeCoreAgent()

    # Test 1: Bad HTML with multiple accessibility issues
    html_bad = """
    <!DOCTYPE html>
    <html>
    <head><title>Bad Page</title></head>
    <body>
        <!-- Missing alt text -->
        <img src="logo.png" />
        
        <!-- Empty button -->
        <button></button>
        
        <!-- Poor color contrast -->
        <div style="color: #777; background-color: #888;">Low contrast text</div>
        
        <!-- Invalid ARIA -->
        <div role="button" aria-checked="invalid">Fake Button</div>
    </body>
    </html>
    """
    print("="*50)
    print("TEST 1: Bad HTML")
    result_bad = agent.execute(html_bad)
    print(f"Summary: {result_bad['summary']}")
    assert result_bad['issues_found'] > 0, "Test 1 Failed: Should find issues"
    print("✓ PASS")
    print()

    # Test 2: Good HTML, fully accessible
    html_good = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <title>Good Page</title>
    </head>
    <body>
        <main>
            <h1>Welcome to the Accessible Page</h1>
            <img src="logo.png" alt="Company Logo" />
            <button type="button">Click Me</button>
            <div style="color: #000000; background-color: #FFFFFF;">High contrast text</div>
        </main>
    </body>
    </html>
    """
    print("="*50)
    print("TEST 2: Good HTML")
    result_good = agent.execute(html_good)
    print(f"Summary: {result_good['summary']}")
    assert result_good['issues_found'] == 0, "Test 2 Failed: Should find no issues"
    print("✓ PASS")
    print()

    print("=" * 50)
    print("ALL TESTS PASSED ✓")
    print("=" * 50)