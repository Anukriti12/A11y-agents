"""
Lakshmi Agent - Blindness (Screen Reader User)
Refactored to class-based architecture with BaseAgenticAgent
"""

import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from personas.base_agent import BaseAgenticAgent
from tools.Contrast_Checker_Agent import ContrastAAA_HTML_Agent as ContrastCheckerAgent
from tools import heading_structure_agent
from tools import keyboard_navigation_agent

load_dotenv()

# NVDA Agent wrapper
class NVDAAgent:
    """Delegates to tools.nvda_agent.run_full_analysis using temp HTML file."""
    def execute(self, html: str) -> dict:
        import tempfile
        from pathlib import Path
        from tools.nvda_agent import run_full_analysis
        
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8")
        tmp.write(html)
        tmp.close()
        path = tmp.name
        try:
            uri = Path(path).resolve().as_uri()
            return run_full_analysis(uri)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

LAKSHMI_SYSTEM_PROMPT = """
You are Lakshmi, a lawyer who is blind and uses NVDA screen reader.

You navigate entirely by keyboard and rely on screen reader announcements. You cannot see the screen at all.

Critical barriers:
- Images without alt text (screen reader says "graphic" with no description)
- Empty links or buttons (screen reader announces nothing useful)
- Missing or illogical heading structure (you navigate by pressing H key to jump between headings)
- Elements missing proper ARIA roles (screen reader doesn't announce their purpose)
- Keyboard traps (you get stuck and can't navigate away)

Output ONLY valid JSON (no preamble):
{
  "label": "passed" | "failed" | "inapplicable",
  "severity": "critical" | "serious" | "moderate" | "minor" | "N/A",
  "issues": [
    {
      "wcag": "X.X.X",
      "evidence": "What the tool found",
      "persona_impact": "Why this affects YOU as Lakshmi using a screen reader",
      "recommendation": "How to fix it"
    }
  ],
  "overall_assessment": "Brief summary"
}

DECISION CRITERIA:
- FAILED = Content is not accessible via screen reader
- PASSED = Screen reader can access and understand all content
- Severity:
  - CRITICAL: Complete barrier (no alt text on critical image, empty button, keyboard trap)
  - SERIOUS: Major usability issue (poor headings, missing ARIA)
  - MODERATE: Inconvenient but workable

TOOL USAGE:
- If <img> tags present → Call run_nvda_accessibility_analysis (checks alt text)
- If headings present or complex structure → Call analyze_heading_structure
- If interactive elements → Call check_keyboard_navigation
- Color contrast less critical for Lakshmi (she's blind) but run check_aaa_color_contrast for team QA

INTERPRETING RESULTS:
- run_nvda_accessibility_analysis: If missing_alt_text found → FAILED critical
- analyze_heading_structure: If skipped_levels or generic_headings → FAILED serious
- check_keyboard_navigation: If keyboard_traps found → FAILED critical
"""

class LakshmiAgent(BaseAgenticAgent):
    def __init__(self, api_key):
        super().__init__(api_key, persona_name="Lakshmi")
        
        self.contrast_agent = ContrastCheckerAgent()
        self.heading_agent = heading_structure_agent.HeadingStructureAgent()
        self.keyboard_agent = keyboard_navigation_agent.KeyboardNavigationAgent()
        self.nvda_agent = NVDAAgent()
        
        self.tool_dispatcher = {
            "check_aaa_color_contrast": self.contrast_agent.execute,
            "analyze_heading_structure": self.heading_agent.execute,
            "check_keyboard_navigation": self.keyboard_agent.execute,
            "run_nvda_accessibility_analysis": self.nvda_agent.execute
        }
    
    def get_system_prompt(self):
        return LAKSHMI_SYSTEM_PROMPT
    
    def get_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "check_aaa_color_contrast",
                    "description": """
[WHAT] Runs axe-core color contrast checks at WCAG AAA (enhanced 7:1 ratio).

[WHEN] Use when evaluating for sighted team members or low vision users.

[WHO] Less critical for Lakshmi (she's blind) but helps sighted collaborators
- Included for comprehensive QA when Lakshmi reviews with sighted colleagues

[RETURNS]
- contrast_violations: List of elements failing AAA (7:1)
- If found → note for team but not critical for Lakshmi personally

[DON'T USE]
- Not a priority check for Lakshmi's personal usage
                    """,
                    "parameters": {
                        "type": "object",
                        "properties": {"html": {"type": "string"}},
                        "required": ["html"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "analyze_heading_structure",
                    "description": """
[WHAT] Analyzes heading hierarchy, skipped levels, generic headings, text density (WCAG 1.3.1, 2.4.6).

[WHEN] Use this when:
- Page has heading tags (<h1> through <h6>)
- Checking document structure for screen reader navigation
- Evaluating if content is organized logically

[WHO] CRITICAL for Lakshmi (blind - navigates by pressing H key to jump between headings)
- Lakshmi: Uses H key to scan page structure - skipped levels break navigation flow
- Generic headings like "Click here" or "More" provide no context when announced
- Needs logical h1 → h2 → h3 progression to understand document hierarchy

[RETURNS]
- heading_hierarchy: Ordered list of headings
- skipped_levels: E.g., h1 → h4 (missing h2, h3) → FAILED serious
- multiple_h1s: More than one h1 confuses page purpose
- generic_headings: "More", "Click here" → FAILED moderate
- text_density: Large blocks between headings make scanning hard

[DON'T USE]
- Page has no headings (single paragraph page)
                    """,
                    "parameters": {
                        "type": "object",
                        "properties": {"html": {"type": "string"}},
                        "required": ["html"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_keyboard_navigation",
                    "description": """
[WHAT] Analyzes focusable elements, keyboard traps, tab order (WCAG 2.1.1, 2.4.3).

[WHEN] Use this when:
- Page has interactive elements (links, buttons, forms)
- Checking if screen reader user can navigate without mouse
- Evaluating focus management

[WHO] CRITICAL for Lakshmi (blind - navigates 100% by keyboard with screen reader)
- Lakshmi: Any keyboard trap completely blocks her navigation - can't escape without mouse
- Illogical tab order breaks her mental model of page layout

[RETURNS]
- keyboard_traps: Elements where Tab gets stuck → FAILED critical
- missing_keyboard_access: Interactive elements unreachable by keyboard → FAILED critical
- tab_order_issues: Focus jumps illogically
- If keyboard_traps NOT EMPTY → FAILED critical (complete blocker)

[DON'T USE]
- Page is purely static text with no interactive elements
                    """,
                    "parameters": {
                        "type": "object",
                        "properties": {"html": {"type": "string"}},
                        "required": ["html"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "run_nvda_accessibility_analysis",
                    "description": """
[WHAT] Runs NVDA screen reader checks for alt text, bypass blocks, name/role/value (WCAG 1.1.1, 2.4.1, 4.1.2).

[WHEN] Use this when:
- Page has images, forms, or custom widgets
- Checking what screen reader actually announces
- Verifying semantic HTML and ARIA

[WHO] CRITICAL for Lakshmi (blind NVDA user - this simulates her actual experience)
- Lakshmi: If image has no alt, NVDA says "graphic" - she has no idea what it shows
- Empty buttons/links: NVDA announces nothing - she doesn't know their purpose
- Missing ARIA: Custom widgets don't announce role/state

[RETURNS]
- missing_alt_text: Images without alt attributes → FAILED critical
- empty_links_buttons: Links/buttons with no accessible name → FAILED serious
- invalid_aria: Broken ARIA attributes → FAILED serious
- missing_bypass: No skip link to main content → FAILED moderate
- If missing_alt_text on critical images → FAILED critical

[DON'T USE]
- Page has no images, forms, or interactive elements
- Simple text-only content
                    """,
                    "parameters": {
                        "type": "object",
                        "properties": {"html": {"type": "string"}},
                        "required": ["html"]
                    }
                }
            }
        ]
    
    def execute_tool(self, tool_name, arguments):
        html = arguments.get("html", "")
        
        if not html:
            return {"error": "Missing 'html' parameter"}
        
        if tool_name in self.tool_dispatcher:
            try:
                return self.tool_dispatcher[tool_name](html=html)
            except Exception as e:
                return {"error": str(e), "tool_name": tool_name, "status": "failed"}
        
        return {"error": f"Unknown tool: {tool_name}"}

# Test code - ONLY runs when you execute this file directly
if __name__ == "__main__":
    import json
    
    test_html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <title>HR self‑serve — broken SR demo</title>
      <style>
        body { font-family: sans-serif; }
        .topbar a { margin-right: 6px; }
        .fake-toggle { border: 1px solid #333; padding: 6px; cursor: default; }
      </style>
    </head>
    <body>
      <!-- Intentionally no skip link and no landmark regions -->
      <div class="topbar">
        <a href="/dash">Dashboard</a>
        <a href="/time">Time cards</a>
        <a href="/benefits">Benefits</a>
        <!-- Empty link -->
        <a href="#"></a>
        <!-- Empty button -->
        <button type="button"></button>
        <!-- Button with image but no alt -->
        <button type="button"><img src="https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/img/dummy.png" width="14" height="14"></button>
      </div>
      <!-- Illogical heading order: no h1; start with h4; skip to h2; generic h3; jump to h5 -->
      <h4>Self‑serve</h4>
      <p>Status chart (no text alternative):</p>
      <p><img src="https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/img/dummy.png" width="180" height="90"></p>
      
      <h2>Overview</h2>
      <h3>Click here</h3>
      <p>Team photo:</p>
      <p><img src="https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/img/dummy.png" width="200" height="120"></p>
      
      <h5>Enrollment</h5>
      
      <!-- Interactive elements with no appropriate ARIA roles -->
      <p><span onclick="void(0)" style="text-decoration:underline;color:#00c;">Apply for leave</span></p>
      <div tabindex="0" onclick="void(0)" class="fake-toggle">Submit request</div>
      
      <form id="pto" action="#" method="post">
        <p>Request PTO</p>
        <!-- Native checkbox hidden from tab order -->
        <input type="checkbox" id="halfday" name="halfday" tabindex="-1" style="position:absolute;opacity:0;width:1px;height:1px;">
        <div tabindex="0" onclick="document.getElementById('halfday').click();">
          Half day only <span id="halfday-label">(off)</span>
        </div>
        <p>No aria-checked, role, or live region — screen reader state does not track the real checkbox.</p>
        
        <input type="text" name="start" placeholder="Start date">
        <input type="text" name="end" placeholder="End date">
        
        <input type="image" src="https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/img/dummy.png" width="72" height="22">
      </form>
    </body>
    </html>
    """
    
    agent = LakshmiAgent(os.environ["OPENAI_API_KEY"])
    result = agent.evaluate(test_html)
    
    print("=" * 70)
    print("LAKSHMI AGENT TEST")
    print("=" * 70)
    print(json.dumps(result, indent=2))