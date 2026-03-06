"""
Target Size Checker Tool Agent
Detects interactive elements that are smaller than 44x44 pixels
Used by: Ade
"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time
import tempfile
import os

MIN_TARGET_SIZE = 44

class TargetSizeValidatorAgent:
    """Checks for interactive elements that are too small to easily click."""

    def execute(self, html):
        """
        Analyzes HTML for small interactive elements.

        Args:
            html: HTML string to analyze.

        Returns:
            A dictionary with analysis results.
        """
        driver = self._start_browser()

        # Create a temporary file to load the HTML reliably
        with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.html', encoding='utf-8') as tmp:
            tmp.write(html)
            tmp_path = tmp.name

        try:
            # Load the HTML from the local file
            driver.get(f"file://{os.path.abspath(tmp_path)}")
            time.sleep(1)

            small_targets = self._find_small_targets(driver)

            issue_found = len(small_targets) > 0
            
            summary = ""
            if issue_found:
                summary = f"Found {len(small_targets)} interactive elements smaller than the recommended {MIN_TARGET_SIZE}x{MIN_TARGET_SIZE} pixels."
            else:
                summary = f"All interactive elements meet the minimum target size of {MIN_TARGET_SIZE}x{MIN_TARGET_SIZE} pixels."

            return {
                "small_targets": small_targets,
                "small_targets_count": len(small_targets),
                "issue_found": issue_found,
                "summary": summary,
                "tool_name": "TargetSizeValidatorAgent"
            }

        finally:
            driver.quit()
            os.unlink(tmp_path) # Clean up the temporary file

    def _start_browser(self):
        """Start headless Chrome browser."""
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument("window-size=1200x600")
        return webdriver.Chrome(options=options)

    def _find_small_targets(self, driver):
        """Finds interactive elements smaller than MIN_TARGET_SIZE."""
        
        script = f"""
        const MIN_SIZE = {MIN_TARGET_SIZE};
        const elements = document.querySelectorAll('button, a, [role="button"], input:not([type="hidden"])');
        const results = [];

        elements.forEach(elem => {{
            const width = elem.offsetWidth;
            const height = elem.offsetHeight;

            if ((width > 0 && width < MIN_SIZE) || (height > 0 && height < MIN_SIZE)) {{
                results.push({{
                    tag: elem.tagName.toLowerCase(),
                    id: elem.id || '',
                    class: elem.className || '',
                    text: (elem.textContent || elem.value || "").trim().substring(0, 50),
                    width: Math.round(width),
                    height: Math.round(height)
                }});
            }}
        }});
        return results;
        """
        try:
            return driver.execute_script(script) or []
        except Exception as e:
            print(f"Error finding small targets: {e}")
            return []

# Test cases
if __name__ == "__main__":
    agent = TargetSizeValidatorAgent()

    # Test 1: One small button
    print("=" * 50)
    print("TEST 1: One small button")
    print("=" * 50)
    html1 = '<html><body><button style="width:20px; height:20px;">X</button></body></html>'
    result1 = agent.execute(html1)
    print("Result:", result1)
    assert result1["issue_found"] is True
    assert result1["small_targets_count"] == 1
    print("✓ PASS")
    print()

    # Test 2: Buttons of adequate size
    print("=" * 50)
    print("TEST 2: Buttons of adequate size")
    print("=" * 50)
    html2 = '<html><body><button style="width:50px; height:50px;">OK</button></body></html>'
    result2 = agent.execute(html2)
    print("Result:", result2)
    assert result2["issue_found"] is False
    assert result2["small_targets_count"] == 0
    print("✓ PASS")
    print()

    # Test 3: Mix of small and large targets
    print("=" * 50)
    print("TEST 3: Mix of small and large targets")
    print("=" * 50)
    html3 = '''
    <html>
    <head>
        <style>
            .small-a { width:30px; height:30px; display:inline-block; }
            .big-button { width:44px; height:44px; }
            .small-input { width:40px; height:20px; }
        </style>
    </head>
    <body>
        <a href="#" class="small-a">Small</a>
        <button class="big-button">Big</button>
        <input type="submit" value="Small Submit" class="small-input">
    </body></html>
    '''
    result3 = agent.execute(html3)
    print("Result:", result3)
    assert result3["issue_found"] is True
    assert result3["small_targets_count"] == 2
    print("✓ PASS")
    print()
    
    # Test 4: No interactive elements
    print("=" * 50)
    print("TEST 4: No interactive elements")
    print("=" * 50)
    html4 = '<html><body><p>Just text.</p></body></html>'
    result4 = agent.execute(html4)
    print("Result:", result4)
    assert result4["issue_found"] is False
    assert result4["small_targets_count"] == 0
    print("✓ PASS")
    print()
    print("=" * 50)
    print("ALL TESTS PASSED ✓")
    print("=" * 50)
