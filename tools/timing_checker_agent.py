"""
Timing Checker Tool Agent
Detects potential issues with a user not being able to turn off, adjust, or extend the time limit.
Used by: Ade
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time

class TimingCheckerAgent:
    """Detects if users have control over time limits."""

    def execute(self, html):
        """
        Analyzes HTML for time-limit-related accessibility issues.

        Args:
            html: HTML string to analyze.

        Returns:
            A dictionary with analysis results.
        """
        driver = self._start_browser()

        try:
            driver.get(f"data:text/html;charset=utf-8,{html}")
            time.sleep(1)
            meta_refreshes = self._detect_meta_refresh(driver)
            timeout_ui = self._detect_timeout_ui(driver)
            timeout_controls = self._detect_timeout_controls(driver)
            issue_found = (len(meta_refreshes) > 0 and len(timeout_controls) == 0) or \
                          (len(timeout_ui) > 0 and len(timeout_controls) == 0)
            summary = ""
            if len(meta_refreshes) > 0 and len(timeout_controls) == 0:
                summary = "Potential Issue: A meta refresh tag was found which can cause unexpected page changes. No controls to stop or adjust this were detected."
            elif len(timeout_ui) > 0 and len(timeout_controls) == 0:
                summary = "Potential Issue: UI elements indicating a time limit were found, but no controls to adjust or extend the time were detected."
            elif len(meta_refreshes) == 0 and len(timeout_ui) == 0:
                summary = "No clear evidence of time limits was found."
            else:
                summary = "UI elements indicating a time limit and potential controls were found. Manual verification is needed to ensure controls are adequate."
            return {
                "meta_refreshes": meta_refreshes,
                "meta_refreshes_count": len(meta_refreshes),
                "timeout_ui_elements": timeout_ui,
                "timeout_ui_elements_count": len(timeout_ui),
                "timeout_controls": timeout_controls,
                "timeout_controls_count": len(timeout_controls),
                "issue_found": issue_found,
                "summary": summary,
                "tool_name": "TimingCheckerAgent"
            }
        finally:
            driver.quit()

    def _start_browser(self):
        """Start headless Chrome browser."""
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        return webdriver.Chrome(options=options)

    def _detect_meta_refresh(self, driver):
        """Detects meta refresh tags."""
        refreshes = []
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, 'meta[http-equiv="refresh"]')
            for elem in elements:
                content = elem.get_attribute('content')
                if content:
                    refreshes.append({"content": content})
        except Exception as e:
            print(f"Error detecting meta refresh: {e}")
        return refreshes

    def _detect_timeout_ui(self, driver):
        """Detects UI elements that suggest a time limit."""
        keywords = ["session", "timeout", "expire", "time limit", "remaining", "countdown"]
        
        script = f"""
        const keywords = {keywords};
        const elements = document.querySelectorAll('body *');
        const results = [];
        const regex = new RegExp(keywords.join('|'), 'i');

        elements.forEach(elem => {{
            // Check element's own text, excluding children's text
            const ownText = Array.from(elem.childNodes)
                .filter(node => node.nodeType === Node.TEXT_NODE)
                .map(node => node.textContent.trim())
                .join(' ');
            
            if (ownText && regex.test(ownText)) {{
                results.push({{
                    tag: elem.tagName.toLowerCase(),
                    text: ownText.substring(0, 100), // snippet
                    id: elem.id || '',
                    class: elem.className || ''
                }});
            }}
        }});
        return results;
        """
        try:
            return driver.execute_script(script) or []
        except Exception as e:
            print(f"Error detecting timeout UI: {e}")
            return []

    def _detect_timeout_controls(self, driver):
        """Detects controls for managing time limits."""
        keywords = ["extend", "continue", "more time", "adjust", "don't log out", "stay signed in", "keep me signed in"]
        
        script = f"""
        const keywords = {keywords};
        const elements = document.querySelectorAll('button, a, [role="button"]');
        const results = [];
        const regex = new RegExp(keywords.join('|'), 'i');

        elements.forEach(elem => {{
            const text = elem.textContent || elem.getAttribute('aria-label') || '';
            if (regex.test(text)) {{
                results.push({{
                    tag: elem.tagName.toLowerCase(),
                    text: text.trim().substring(0, 100),
                    id: elem.id || '',
                    class: elem.className || ''
                }});
            }}
        }});
        return results;
        """
        try:
            return driver.execute_script(script) or []
        except Exception as e:
            print(f"Error detecting timeout controls: {e}")
            return []

# Test cases
if __name__ == "__main__":
    agent = TimingCheckerAgent()

    # Test 1: Meta refresh with no controls
    print("=" * 50)
    print("TEST 1: Meta refresh, no controls")
    print("=" * 50)
    html1 = '<html><head><meta http-equiv="refresh" content="5;url=newpage.html"></head><body>Page will refresh.</body></html>'
    result1 = agent.execute(html1)
    print("Result:", result1)
    assert result1["issue_found"] is True, "Test 1 Failed: Issue should be found"
    assert result1["meta_refreshes_count"] == 1, "Test 1 Failed: Should be 1 meta refresh"
    assert result1["timeout_controls_count"] == 0, "Test 1 Failed: Should be 0 controls"
    print("✓ PASS")
    print()

    # Test 2: Timeout text with a control
    print("=" * 50)
    print("TEST 2: Timeout text with control")
    print("=" * 50)
    html2 = '<html><body><p>Your session will expire in 1 minute.</p><button>Extend Session</button></body></html>'
    result2 = agent.execute(html2)
    print("Result:", result2)
    assert result2["issue_found"] is False, "Test 2 Failed: Issue should not be found"
    assert result2["timeout_ui_elements_count"] > 0, "Test 2 Failed: Should be > 0 UI elements"
    assert result2["timeout_controls_count"] > 0, "Test 2 Failed: Should be > 0 controls"
    print("✓ PASS")
    print()

    # Test 3: Timeout text with NO control
    print("=" * 50)
    print("TEST 3: Timeout text, no control")
    print("=" * 50)
    html3 = '<html><body><p>Your session timeout is approaching.</p></body></html>'
    result3 = agent.execute(html3)
    print("Result:", result3)
    assert result3["issue_found"] is True, "Test 3 Failed: Issue should be found"
    assert result3["timeout_ui_elements_count"] > 0, "Test 3 Failed: Should be > 0 UI elements"
    assert result3["timeout_controls_count"] == 0, "Test 3 Failed: Should be 0 controls"
    print("✓ PASS")
    print()

    # Test 4: No time limits
    print("=" * 50)
    print("TEST 4: No time limits")
    print("=" * 50)
    html4 = '<html><body><p>This is a static page.</p></body></html>'
    result4 = agent.execute(html4)
    print("Result:", result4)
    assert result4["issue_found"] is False, "Test 4 Failed: Issue should not be found"
    assert result4["meta_refreshes_count"] == 0, "Test 4 Failed: Should be 0 meta refreshes"
    assert result4["timeout_ui_elements_count"] == 0, "Test 4 Failed: Should be 0 UI elements"
    print("✓ PASS")
    print()
    print("=" * 50)
    print("ALL TESTS PASSED ✓")
    print("=" * 50)
