"""
Keyboard Navigation Tool Agent
Analyzes HTML for keyboard navigation accessibility.
Used by: Ade
"""

from playwright.sync_api import sync_playwright
import html

class KeyboardNavigationAgent:
    """Analyzes HTML for keyboard navigation accessibility issues."""

    def execute(self, html: str) -> dict:
        html_content = html
        """
        Analyzes the HTML to find all focusable elements and checks for potential
        keyboard navigation issues.
        
        Args:
            html_content: HTML string to analyze.
        
        Returns:
            A dictionary containing information about focusable elements.
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                page.set_content(html_content)
                focusable_elements = self._get_focusable_elements(page)
                return {
                    "focusable_elements": focusable_elements,
                    "focusable_elements_count": len(focusable_elements),
                    "tool_name": "KeyboardNavigationAgent"
                }
            finally:
                browser.close()

    def _get_focusable_elements(self, page):
        """
        Retrieves all focusable elements from the page, excluding those that are disabled or not visible.
        
        Returns:
            A list of dictionaries, where each dictionary represents a focusable element.
        """
        selector = """
        a[href], button:not([disabled]), input:not([disabled]), 
        textarea:not([disabled]), select:not([disabled]), details, 
        [tabindex]:not([tabindex="-1"])
        """
        elements = page.query_selector_all(selector)
        focusable_list = []
        for i, element in enumerate(elements):
            if element.is_visible():
                tag = element.evaluate('el => el.tagName.toLowerCase()')
                elem_id = element.get_attribute('id')
                elem_class = element.get_attribute('class')
                text = element.text_content()
                focusable_list.append({
                    'element_index': i,
                    'tag': tag,
                    'text': (text or "").strip(),
                    'id': elem_id or '',
                    'class': elem_class or '',
                })
        return focusable_list

# Test cases
if __name__ == "__main__":
    agent = KeyboardNavigationAgent()

    # Test 1: Simple case with common focusable elements
    print("=" * 50)
    print("TEST 1: Simple focusable elements")
    print("=" * 50)
    test_html_1 = """
    <html>
    <body>
        <h1>Test Page</h1>
        <a href="#">Link 1</a>
        <button>Button 1</button>
        <input type="text" value="Input 1"/>
        <div tabindex="0">Focusable Div</div>
    </body>
    </html>
    """
    result1 = agent.execute(test_html_1)
    print("Result:", result1)
    print(f"Expected: 4 focusable elements")
    print(f"Got: {result1['focusable_elements_count']} focusable elements")
    assert result1['focusable_elements_count'] == 4
    print("✓ PASS\n")

    # Test 2: Elements that should NOT be focusable
    print("=" * 50)
    print("TEST 2: Ignoring non-focusable elements")
    print("=" * 50)
    test_html_2 = """
    <html>
    <body>
        <a href="#">Visible Link</a>
        <button disabled>Disabled Button</button>
        <input type="text" style="display: none;" />
        <div tabindex="-1">Non-Focusable Div</div>
        <p>Just some text.</p>
    </body>
    </html>
    """
    result2 = agent.execute(test_html_2)
    print("Result:", result2)
    print(f"Expected: 1 focusable element")
    print(f"Got: {result2['focusable_elements_count']} focusable elements")
    assert result2['focusable_elements_count'] == 1
    assert result2['focusable_elements'][0]['text'] == 'Visible Link'
    print("✓ PASS\n")

    # Test 3: Empty HTML
    print("=" * 50)
    print("TEST 3: Empty HTML document")
    print("=" * 50)
    test_html_3 = "<html><body></body></html>"
    result3 = agent.execute(test_html_3)
    print("Result:", result3)
    print(f"Expected: 0 focusable elements")
    print(f"Got: {result3['focusable_elements_count']} focusable elements")
    assert result3['focusable_elements_count'] == 0
    print("✓ PASS\n")
    print("=" * 50)
    print("ALL TESTS PASSED ✓")
    print("=" * 50)
