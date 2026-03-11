from playwright.sync_api import sync_playwright

class ContrastAAA_URL_Agent:
    """
    Analyzes a live URL for WCAG 2.1 AAA Contrast (Enhanced) requirements.
    """

    def execute(self, url):
        """
        Args:
            url (str): The full URL (including http/https) to analyze.
        """
        with sync_playwright() as p:
            # Launching chromium
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            try:
                print(f"Navigating to: {url}...")
                # wait_until="networkidle" ensures the CSS and assets are loaded
                page.goto(url, wait_until="networkidle")
                
                # Injecting axe-core
                page.add_script_tag(url="https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.8.2/axe.min.js")
                
                # Run axe-core specifically for AAA contrast
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
                
                # Format the output to be scannable
                formatted_violations = []
                for v in violations:
                    for node in v['nodes']:
                        formatted_violations.append({
                            "element": node['target'],
                            "summary": node['failureSummary'],
                            "impact": v['impact']
                        })

                return {
                    "url": url,
                    "status": "FAIL" if formatted_violations else "PASS",
                    "violation_count": len(formatted_violations),
                    "violations": formatted_violations,
                    "tool_name": "ContrastAAA_URL_Agent"
                }

            except Exception as e:
                return {"error": str(e), "url": url}
            finally:
                browser.close()

# Example Usage
if __name__ == "__main__":
    agent = ContrastAAA_URL_Agent()
    
    # Input a live URL here
    target_url = "https://www.w3.org/WAI/content-assets/wcag-act-rules/testcases/09o5cg/67fe402a5de9743bf9882d7d52deb9749005d16c.html" # FAIL CASE
    # target_url = "https://www.w3.org/WAI/content-assets/wcag-act-rules/testcases/09o5cg/fd406bedf0bb3bdc4c2a718f49a3dd0f7aaa7556.html" # PASS CASE
    
    result = agent.execute(target_url)
    
    print("\n" + "="*50)
    print(f"ANALYSIS FOR: {result['url']}")
    print(f"STATUS: {result['status']}")
    print(f"TOTAL AAA VIOLATIONS: {result.get('violation_count', 0)}")
    print("="*50)

    if result.get("violations"):
        for i, v in enumerate(result['violations'], 1):
            print(f"{i}. Element: {v['element']}")
            print(f"   Issue: {v['summary']}\n")