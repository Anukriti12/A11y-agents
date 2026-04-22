import requests
from playwright.sync_api import sync_playwright

# Download once at module level
AXE_CORE_JS = requests.get(
    "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.8.2/axe.min.js"
).text

class ContrastAAA_HTML_Agent:
    def execute(self, html_content):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            try:
                page.set_content(html_content, wait_until="domcontentloaded")
                
                # Inject axe-core as inline script, not a URL fetch
                page.add_script_tag(content=AXE_CORE_JS)

                # Sanity check — remove once confirmed working
                axe_loaded = page.evaluate("typeof axe !== 'undefined'")
                print(f"axe loaded: {axe_loaded}")
                
                results = page.evaluate("""
                    axe.run({
                        runOnly: {
                            type: 'tag',
                            values: ['cat.color']
                        },
                        rules: {
                            'color-contrast-enhanced': { enabled: true },
                            'color-contrast': { enabled: false }
                        }
                    })
                """)


                violations = results.get("violations", [])
                
                formatted_violations = []
                for v in violations:
                    for node in v['nodes']:
                        formatted_violations.append({
                            "element": node['target'],
                            "summary": node['failureSummary'],
                            "impact": v['impact']
                        })

                return {
                    "status": "FAIL" if formatted_violations else "PASS",
                    "violation_count": len(formatted_violations),
                    "violations": formatted_violations,
                    "tool_name": "ContrastAAA_HTML_Agent"
                }

            except Exception as e:
                return {"error": str(e)}
            finally:
                browser.close()


# Example Usage
if __name__ == "__main__":
    agent = ContrastAAA_HTML_Agent()

    # FAIL CASE
    fail_html = """
    <html>
    <body>
        <p style="color: #777777; background-color: #ffffff;">
            This text has low contrast and will fail AAA.
        </p>
    </body>
    </html>
    """

    # PASS CASE
    pass_html = """
    <html>
    <body>
        <p style="color: #000000; background-color: #ffffff;">
            This text has high contrast and will pass AAA.
        </p>
    </body>
    </html>
    """

    for label, html_content in [("FAIL", fail_html), ("PASS", pass_html)]:
        result = agent.execute(html_content)
        print("\n" + "="*50)
        print(f"TEST CASE: {label}")
        print(f"STATUS: {result['status']}")
        print(f"TOTAL AAA VIOLATIONS: {result.get('violation_count', 0)}")
        print("="*50)
        if result.get("violations"):
            for i, v in enumerate(result['violations'], 1):
                print(f"{i}. Element: {v['element']}")
                print(f"   Issue: {v['summary']}\n")