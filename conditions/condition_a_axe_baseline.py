import time
import urllib.request
import ssl
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

class AxeCoreBaseline:
    """
    Evaluates HTML for accessibility issues using axe-core to provide a baseline.
    Returns a structured dictionary matching the desired output format.
    """

    _axe_script = None

    def __init__(self):
        # Cache the axe-core library in memory to avoid downloading it every time.
        if not AxeCoreBaseline._axe_script:
            url = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.8.2/axe.min.js"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            # Use an unverified context to bypass strict SSL checks which can sometimes
            # block Python from fetching the script on certain networks or environments.
            context = ssl._create_unverified_context()
            with urllib.request.urlopen(req, context=context) as response:
                AxeCoreBaseline._axe_script = response.read().decode('utf-8')

    def evaluate(self, html: str) -> dict:
        start_time = time.time()
        
        # Axe-core runs inside a browser, so the HTML needs to be a valid document.
        # If the user just passed a snippet (e.g., <button>Click</button>), we wrap it.
        if "<html" not in html.lower():
            html_to_test = f"<!DOCTYPE html><html lang='en'><head><title>Test</title></head><body>{html}</body></html>"
        else:
            html_to_test = html

        # Start a hidden Chrome browser to load the HTML and run the JS library.
        driver = self._start_browser()
        try:
            # Load the HTML string directly into the browser using a data URI
            driver.get(f"data:text/html;charset=utf-8,{html_to_test}")
            time.sleep(0.5)

            # Inject the axe-core JS code into the page
            driver.execute_script(self._axe_script)

            # If the original HTML was just a snippet, we disable document-level rules
            # to avoid noise (missing title, lang, main landmark)
            is_snippet = "<html" not in html.lower()
            
            # Run axe-core asynchronously
            script = f"""
            var callback = arguments[arguments.length - 1];
            var options = {{}};
            if ({str(is_snippet).lower()}) {{
                options = {{
                    rules: {{
                        'document-title': {{ enabled: false }},
                        'html-has-lang': {{ enabled: false }},
                        'landmark-one-main': {{ enabled: false }},
                        'page-has-heading-one': {{ enabled: false }},
                        'region': {{ enabled: false }},
                        'bypass': {{ enabled: false }}
                    }}
                }};
            }}
            
            axe.run(document, options).then(results => {{
                callback(results);
            }}).catch(err => {{
                callback({{error: err.message}});
            }});
            """
            
            driver.set_script_timeout(10)
            axe_results = driver.execute_async_script(script)

            if "error" in axe_results:
                return self._build_error_result(axe_results["error"], start_time)

            # If successful, parse the massive JSON result into our desired format
            return self._format_results(axe_results, start_time)

        finally:
            # Close the browser even if an error occurred
            driver.quit()

    def _format_results(self, axe_results: dict, start_time: float) -> dict:
        """
        Takes the raw axe-core output and shapes it into our standardized JSON format.
        """
        violations = axe_results.get('violations', [])
        
        issues = []
        highest_severity = "none"
        # Define severity levels
        severity_levels = {"none": 0, "minor": 1, "moderate": 2, "serious": 3, "critical": 4}
        total_elements = 0
        
        for violation in violations:
            # Determine overall severity by keeping the highest severity encountered
            impact = violation.get("impact", "unknown")
            if severity_levels.get(impact, 0) > severity_levels.get(highest_severity, 0):
                highest_severity = impact
                
            # Extract the specific WCAG rule from the tags ('wcag111' -> '1.1.1')
            wcag = self._get_wcag_from_tags(violation.get("tags", []))
            
            nodes = violation.get("nodes", [])
            total_elements += len(nodes)
            
            for node in nodes:
                # Failure summary formatting
                evidence = node.get("failureSummary", "No evidence provided")
                if "Fix any of the following:" in evidence:
                    evidence = evidence.replace("Fix any of the following:", "").strip()
                
                issues.append({
                    "wcag": wcag,
                    "description": violation.get("help", "No description"),
                    "evidence": evidence,
                    "recommendation": violation.get("description", "Review axe-core documentation for recommendation")
                })
        
        # Build the final top-level assessment string
        label = "failed" if len(issues) > 0 else "passed"
        if len(violations) == 1 and total_elements == 1:
            overall_assessment = "axe-core found 1 violation type affecting 1 element"
        else:
            overall_assessment = f"axe-core found {len(violations)} violation type(s) affecting {total_elements} element(s)"
            
        if len(issues) == 0:
            label = "passed"
            severity = "none"
            overall_assessment = "axe-core found no violations"

        end_time = time.time()
        
        return {
            "evaluation": {
                "label": label,
                "severity": highest_severity,
                "issues": issues,
                "overall_assessment": overall_assessment
            },
            "metadata": {
                "tools_called": ["axe-core"],
                "iteration_count": 1,
                "total_time_seconds": round(end_time - start_time, 2)
            }
        }

    def _build_error_result(self, error_msg: str, start_time: float) -> dict:
        return {
            "evaluation": {
                "label": "error",
                "severity": "critical",
                "issues": [],
                "overall_assessment": f"Error running axe-core: {error_msg}"
            },
            "metadata": {
                "tools_called": ["axe-core"],
                "iteration_count": 1,
                "total_time_seconds": round(time.time() - start_time, 2)
            }
        }

    def _get_wcag_from_tags(self, tags: list) -> str:
        for tag in tags:
            match = re.match(r'^wcag(\d)(\d)(\d)$', tag)
            if match:
                return f"{match.group(1)}.{match.group(2)}.{match.group(3)}"
        return "unknown"

    def _start_browser(self):
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        return webdriver.Chrome(options=options)

if __name__ == "__main__":
    import json
    # Changed this since the original test string was recognized as an HTML document.
    html = "<img src='test.jpg'>"
    result = AxeCoreBaseline().evaluate(html)
    print(json.dumps(result, indent=2))
