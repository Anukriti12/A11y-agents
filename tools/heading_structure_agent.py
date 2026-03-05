"""
Heading Structure Agent
Detects issues with heading hierarchy, headings in generic containers, and "fake" headings.
Used by: Ian
"""

import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from axe_selenium_python import Axe

class HeadingStructureAgent:
    """Analyzes heading structure for common accessibility issues."""

    def __init__(self):
        # The JavaScript that includes custom rules (div) for axe-core to be injected into the page.
        self.axe_run_script = """
        const headingInDivRule = {
          id: 'heading-inside-div',
          selector: 'h1, h2, h3, h4, h5, h6, [role="heading"]',
          enabled: true,
          tags: ['custom', 'structure'],
          any: ['check-heading-context'],
          metadata: {
            description: 'Ensures headings are not placed directly inside generic <div> elements, which can disrupt document structure and navigation for screen readers.',
            help: 'Place headings within semantic landmark elements like <main>, <section>, <article>, <aside>, <nav>, or <header> instead of generic <div>s.'
          }
        };
        const headingContextCheck = {
          id: 'check-heading-context',
          evaluate: function(node, options) {
            const parent = node.parentElement;
            // FAIL if parent is a generic div
            if (parent && parent.tagName.toLowerCase() === 'div' && !parent.hasAttribute('role')) {
              return false;
            }
            // PASS otherwise
            return true;
          },
          metadata: {
            messages: {
              fail: 'Heading is nested inside a generic <div>. This can make it difficult for assistive technologies to understand the document structure.'
            }
          }
        };

        const fakeHeadingCheck = {
            id: 'check-fake-heading',
            evaluate: function(node, options) {
                // PASS if the element is empty or just contains whitespace.
                if (!node.textContent.trim()) {
                    return true;
                }
                // PASS if the element contains a real heading tag.
                if (node.querySelector('h1, h2, h3, h4, h5, h6, [role="heading"]')) {
                    return true;
                }

                const style = window.getComputedStyle(node);
                const fontWeight = style.fontWeight;
                const fontSize = parseFloat(style.fontSize);

                const bodyStyle = window.getComputedStyle(document.body);
                const bodyFontSize = parseFloat(bodyStyle.fontSize) || 16;

                const isBold = parseInt(fontWeight, 10) >= 700 || ['bold', 'bolder'].includes(fontWeight);
                const isLarge = fontSize >= (bodyFontSize * 1.25);

                if (isBold && isLarge) {
                    let parent = node.parentElement;
                    while(parent) {
                        const role = parent.getAttribute('role');
                        const tag = parent.tagName.toLowerCase();
                        if (tag === 'a' || tag === 'button' || role === 'link' || role === 'button') {
                            // It's inside a link or button, probably not a heading. PASS.
                            return true;
                        }
                        if (parent === document.body) break;
                        parent = parent.parentElement;
                    }
                    // It is bold and large, and not inside a link/button. This is a FAKE HEADING. FAIL.
                    return false;
                }
                // It's not styled like a heading. PASS.
                return true;
            },
            metadata: {
                messages: {
                    fail: 'This element may be a "fake" heading. It is styled to look like a heading but does not use a heading tag (<h1>-<h6>) or role="heading". Screen readers will not recognize it as a heading.'
                }
            }
        };
        const fakeHeadingRule = {
            id: 'fake-heading',
            selector: 'p, span, div, b, i, em, strong',
            enabled: true,
            tags: ['custom', 'structure'],
            any: ['check-fake-heading'],
            metadata: {
                description: 'Detects elements that are styled to look like headings but are not semantically marked as such.',
                help: 'Use <h1>-<h6> elements or role="heading" for all headings to ensure they are accessible to screen readers.'
            }
        };

        axe.configure({
          rules: [headingInDivRule, fakeHeadingRule],
          checks: [headingContextCheck, fakeHeadingCheck]
        });
        """

    def execute(self, html: str) -> dict:
        """
        Analyzes the given HTML for heading structure accessibility issues.
        
        Args:
            html: A string containing the HTML to be analyzed.
        
        Returns:
            A dictionary containing the analysis results, including lists of
            violations for heading order, headings inside divs, and fake headings.
        """
        driver = self._start_browser()
        try:
            driver.get(f"data:text/html;charset=utf-8,{html}")
            
            # Inject the axe-core script into the page
            axe = Axe(driver)
            axe.inject()
            
            # Configure Axe with custom rules by executing a script
            driver.execute_script(self.axe_run_script)
            
            # Run axe with options to only check for specific rules
            results = axe.run(options={
                "runOnly": {
                    "type": "rule",
                    "values": ['heading-order', 'heading-inside-div', 'fake-heading']
                }
            })
            
            violations = results.get('violations', [])
            
            heading_order_violations = [v for v in violations if v['id'] == 'heading-order']
            headings_in_divs = [v for v in violations if v['id'] == 'heading-inside-div']
            fake_headings = [v for v in violations if v['id'] == 'fake-heading']
            
            return {
                "heading_order_violations": heading_order_violations,
                "headings_in_divs": headings_in_divs,
                "fake_headings": fake_headings,
                "heading_order_violations_count": len(heading_order_violations),
                "headings_in_divs_count": len(headings_in_divs),
                "fake_headings_count": len(fake_headings),
                "total_violations": len(violations),
                "tool_name": "HeadingStructureAgent"
            }
        finally:
            driver.quit()

    def _start_browser(self):
        """Initializes and returns a headless Chrome browser instance."""
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        return webdriver.Chrome(options=options)

if __name__ == '__main__':
    agent = HeadingStructureAgent()

    # Test 1: Improper heading order
    print("=" * 50)
    print("TEST 1: Improper heading order")
    print("=" * 50)
    test_html_1 = """
    <h1>Main Title</h1>
    <h3>Subtitle</h3> <!-- Incorrect: should be h2 -->
    <h2>Section 1</h2>
    """
    result_1 = agent.execute(test_html_1)
    print("Result:", json.dumps(result_1, indent=2))
    assert result_1['heading_order_violations_count'] > 0, "Should detect heading order violation"
    print("✓ PASS")
    print()

    # Test 2: Heading inside a generic div
    print("=" * 50)
    print("TEST 2: Heading inside a generic div")
    print("=" * 50)
    test_html_2 = """
    <main>
      <h1>Main Content</h1>
      <div>
        <h2>A heading in a div</h2>
      </div>
    </main>
    """
    result_2 = agent.execute(test_html_2)
    print("Result:", json.dumps(result_2, indent=2))
    assert result_2['headings_in_divs_count'] > 0, "Should detect heading inside div"
    print("✓ PASS")
    print()

    # Test 3: "Fake" heading
    print("=" * 50)
    print("TEST 3: 'Fake' heading")
    print("=" * 50)
    test_html_3 = """
    <h1>Real Heading</h1>
    <p style="font-size: 2em; font-weight: bold;">This is a fake heading.</p>
    """
    result_3 = agent.execute(test_html_3)
    print("Result:", json.dumps(result_3, indent=2))
    assert result_3['fake_headings_count'] > 0, "Should detect a fake heading"
    print("✓ PASS")
    print()

    # Test 4: Good structure (control)
    print("=" * 50)
    print("TEST 4: Good heading structure")
    print("=" * 50)
    test_html_4 = """
    <article>
      <h1>Article Title</h1>
      <section>
        <h2>Section 1</h2>
        <p>Some text.</p>
      </section>
    </article>
    """
    result_4 = agent.execute(test_html_4)
    print("Result:", json.dumps(result_4, indent=2))
    assert result_4['total_violations'] == 0, "Should find no violations"
    print("✓ PASS")
    print()
    print("=" * 50)
    print("ALL TESTS PASSED ✓")
    print("=" * 50)
