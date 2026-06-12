"""
Lakshmi Agent - Blindness (NVDA Screen Reader User)
Aligned to final 5-WCAG matrix: 1.1.1, 1.3.1, 2.1.1, 2.4.1, 4.1.2

Lakshmi is a lawyer who is blind and uses NVDA. Her WAI persona story
emphasizes alt text on images, programmatic heading hierarchy for H-key
navigation, keyboard reachability of all interactive elements, skip
links and landmarks for bypassing repeated content, and correct
name/role/value semantics on every widget.

Tool-to-criterion mapping:
  - nvda_agent (run_full_analysis) -> 1.1.1, 2.4.1, 4.1.2
  - heading_structure_agent        -> 1.3.1
  - keyboard_navigation_agent      -> 2.1.1

The Contrast_Checker from the previous Lakshmi configuration is removed:
contrast is not part of Lakshmi's personal access needs (she is blind),
and the locked matrix does not include 1.4.x criteria for her.
"""

import os
import sys
import tempfile
from pathlib import Path
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from personas.base_agent import BaseAgenticAgent
from tools import heading_structure_agent
from tools import keyboard_navigation_agent
from tools.nvda_agent import run_full_analysis

load_dotenv()


class NVDAAgentWrapper:
    """
    Adapts nvda_agent.run_full_analysis (which takes a URL) to the
    tool-dispatcher contract (which passes HTML strings). Writes the
    HTML to a temp file and feeds back a file:// URI.

    NOTE: run_full_analysis launches Playwright with headless=False and
    expects NVDA + pywinauto + Tesseract on Windows. The Playwright-based
    static audits (alt, landmark, role validation) work cross-platform,
    but the actual NVDA TTS capture functions require Windows.
    """

    def execute(self, html: str) -> dict:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        )
        tmp.write(html)
        tmp.close()
        try:
            uri = Path(tmp.name).resolve().as_uri()
            return run_full_analysis(uri)
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass


LAKSHMI_SYSTEM_PROMPT = """
You are Lakshmi, a lawyer who is blind. You use NVDA screen reader and
navigate entirely by keyboard. You cannot see the screen at all.

Your WAI persona profile says directly:
  - "I navigate by pressing H to jump between headings."
  - "If an image has no alt text, NVDA just announces 'graphic' and I am stuck."
  - "Skip links let me jump past repeated navigation on every page."
  - "I need to know what every button and link does before I activate it."

You evaluate pages against five WCAG criteria. Each criterion has a tool that
produces evidence. Call each tool AT MOST ONCE, then emit your verdict.

CRITERIA YOU EVALUATE:

  WCAG 1.1.1 Non-text Content (Level A)
    Every meaningful image needs an alt attribute. Decorative images need alt="".
    Tool: run_nvda_full_audit
    FAIL signal: result["wcag_1_1_1"]["verdict"] == "FAIL"

  WCAG 1.3.1 Info and Relationships (Level A)
    Headings must form a programmatically determinable hierarchy.
    Tool: analyze_heading_structure
    FAIL signals: missing_h1=true OR multiple_h1=true OR hierarchy_issues non-empty
                  OR skipped_levels non-empty

  WCAG 2.1.1 Keyboard (Level A)
    All interactive elements must be reachable by keyboard.
    Tool: check_keyboard_navigation
    Note: this tool enumerates what IS focusable. If focusable_elements_count is
    zero but the HTML clearly has interactive elements (buttons, links, forms),
    that's a strong 2.1.1 FAIL signal. If the count looks plausible relative to
    the HTML you can see, treat as PASS for this criterion specifically.

  WCAG 2.4.1 Bypass Blocks (Level A)
    Pages with repeated content need a skip link or landmark structure.
    Tool: run_nvda_full_audit
    FAIL signal: result["wcag_2_4_1"]["verdict"] == "FAIL"

  WCAG 4.1.2 Name, Role, Value (Level A)
    Every widget must expose correct name, role, and value to assistive tech.
    Tool: run_nvda_full_audit
    FAIL signal: result["wcag_4_1_2"]["verdict"] == "FAIL"

OUTPUT FORMAT (return ONLY this JSON, no markdown, no preamble):
{
  "label": "passed" | "failed" | "inapplicable",
  "severity": "critical" | "serious" | "moderate" | "minor" | "N/A",
  "issues": [
    {
      "wcag": "X.X.X",
      "evidence": "Specific finding from the tool output",
      "persona_impact": "How this affects you as Lakshmi using NVDA",
      "recommendation": "Concrete fix"
    }
  ],
  "overall_assessment": "One-sentence summary in your voice as Lakshmi"
}

SEVERITY CALIBRATION:
  - CRITICAL: 1.1.1 violations on meaningful images, 4.1.2 violations on form
              controls, complete absence of skip mechanism for 2.4.1
  - SERIOUS: 1.3.1 hierarchy problems, 2.1.1 unreachable interactive elements
  - MODERATE: 1.3.1 generic headings, 2.4.1 with landmarks but no skip link

DECISION RULES:
  - run_nvda_full_audit returns one full report covering 1.1.1, 2.4.1, and
    4.1.2 simultaneously. ONE CALL to that tool gives you three criteria.
  - If any criterion FAILs, the page label is "failed".
  - If all applicable criteria PASS, the page label is "passed".
  - If the HTML has no images AND no headings AND no interactive elements,
    the page label is "inapplicable".
"""


class LakshmiAgent(BaseAgenticAgent):
    def __init__(self, api_key):
        super().__init__(api_key, persona_name="Lakshmi")

        self.heading_agent = heading_structure_agent.HeadingStructureAgent()
        self.keyboard_agent = keyboard_navigation_agent.KeyboardNavigationAgent()
        self.nvda_agent = NVDAAgentWrapper()

        self.tool_dispatcher = {
            "analyze_heading_structure": self.heading_agent.execute,
            "check_keyboard_navigation": self.keyboard_agent.execute,
            "run_nvda_full_audit": self.nvda_agent.execute,
        }

    def get_system_prompt(self):
        return LAKSHMI_SYSTEM_PROMPT

    def get_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "run_nvda_full_audit",
                    "description": """
[WHAT] Runs the full NVDA-grounded accessibility audit. Combines static
DOM inspection (alt attributes, landmark structure, ARIA role/required-attr
validation, redundant alt text, OCR'd text in images) with NVDA screen
reader speech capture for the same elements. Produces a verdict per
WCAG criterion.

[WHEN] Call ONCE for every page. This single call covers three of
Lakshmi's five criteria (1.1.1, 2.4.1, 4.1.2). Do not skip it unless
the page has no images, no interactive elements, and no headings at all.

[COVERS] WCAG 1.1.1 Non-text Content, WCAG 2.4.1 Bypass Blocks,
WCAG 4.1.2 Name, Role, Value.

[RETURNS] A dict with these REAL keys:
  - url: the file URI that was analyzed
  - wcag_1_1_1: dict with subkeys:
      - wcag: "1.1.1 Non-text Content"
      - verdict: "PASS" | "FAIL" | "INAPPLICABLE"
      - details: dict with reasoning and specific image findings
      - decorative_images_to_review: list of images with alt="" (need manual review)
      - raw: full nested audit data
  - wcag_1_4_5: dict (Images of Text - this is in the report but is NOT in
                your matrix, you can ignore it for Lakshmi's verdict)
  - wcag_2_4_1: dict with subkeys:
      - wcag: "2.4.1 Bypass Blocks"
      - verdict: "PASS" | "FAIL" | "INAPPLICABLE"
      - details: dict explaining landmark presence and skip-link status
      - raw: full nested audit data
  - wcag_4_1_2: dict with subkeys:
      - wcag: "4.1.2 Name, Role, Value"
      - verdict: "PASS" | "FAIL" | "INAPPLICABLE"
      - details: dict listing widgets with missing names, invalid roles, etc.
      - raw: full nested audit data

[INTERPRETATION FOR LAKSHMI]
- Read result["wcag_1_1_1"]["verdict"]. If "FAIL", emit a 1.1.1 issue.
  Pull the specific image(s) from details to build the evidence string.
- Same pattern for "wcag_2_4_1" and "wcag_4_1_2".
- IGNORE the wcag_1_4_5 block entirely - it is not in Lakshmi's matrix.
                    """,
                    "parameters": {
                        "type": "object",
                        "properties": {"html": {"type": "string"}},
                        "required": ["html"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "analyze_heading_structure",
                    "description": """
[WHAT] Inspects all <h1>-<h6> elements on the page and reports hierarchy
validity, skipped levels, multiple or missing h1s, and generic heading text.

[WHEN] Call when the page has any heading elements (<h1>-<h6>). Lakshmi
navigates by pressing the H key to jump between headings, so this is
critical evidence for her experience.

[COVERS] WCAG 1.3.1 Info and Relationships.

[RETURNS] A dict with these REAL keys:
  - headings: list of {level, tag, text, id, position} for every heading
  - total_count: integer
  - hierarchy_valid: boolean - true only if no hierarchy issues
  - hierarchy_issues: list of out-of-order or malformed sequences
  - skipped_levels: list of {from_heading, to_heading, gap}
  - generic_headings: list of headings with vague text like "More", "Click here"
  - missing_h1: boolean
  - multiple_h1: boolean
  - h1_count: integer
  - words_between_headings: list of word counts between consecutive headings
  - max_words_between_headings: integer

[INTERPRETATION FOR LAKSHMI]
- 1.3.1 FAIL if any of: missing_h1, multiple_h1, hierarchy_issues non-empty,
  skipped_levels non-empty.
- INAPPLICABLE if total_count == 0.
- Severity is SERIOUS for missing_h1 or skipped levels (she can't navigate
  by H key reliably), MODERATE for generic_headings (still navigable but
  uninformative on landing).
                    """,
                    "parameters": {
                        "type": "object",
                        "properties": {"html": {"type": "string"}},
                        "required": ["html"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "check_keyboard_navigation",
                    "description": """
[WHAT] Enumerates all keyboard-focusable elements on the page. Includes
visible <a href>, <button> (not disabled), <input>/<select>/<textarea>
(not disabled), <details>, and elements with tabindex>=0.

[WHEN] Call when the page has any interactive elements (buttons, links,
form fields, custom widgets).

[COVERS] WCAG 2.1.1 Keyboard.

[RETURNS] A dict with these REAL keys:
  - focusable_elements: list of {element_index, tag, text, id, class}
  - focusable_elements_count: integer
  - tool_name: "KeyboardNavigationAgent"

[INTERPRETATION FOR LAKSHMI]
This tool reports what IS reachable. Use it together with the HTML you
can see in your prompt:
  - If the HTML has visible <button>, <a href>, or <input> elements and
    focusable_elements_count is plausibly close to that number, the page
    likely passes 2.1.1.
  - If the HTML has many interactive-looking elements (divs with onclick,
    custom widgets, role="button" without tabindex) but the count is
    much lower than expected, that is a 2.1.1 FAIL signal.
  - If focusable_elements_count is 0 on a page that clearly has interactive
    HTML, that is a strong FAIL.
This tool has limited precision for 2.1.1 - it cannot definitively detect
keyboard traps or mouse-only event handlers without a more thorough audit.
Be conservative: only call 2.1.1 a FAIL when the mismatch with the HTML
is unambiguous.
                    """,
                    "parameters": {
                        "type": "object",
                        "properties": {"html": {"type": "string"}},
                        "required": ["html"],
                    },
                },
            },
        ]

    def execute_tool(self, tool_name, arguments):
        html = arguments.get("html", "")
        if not html:
            return {"error": "Missing 'html' parameter"}

        if tool_name in self.tool_dispatcher:
            try:
                return self.tool_dispatcher[tool_name](html=html)
            except Exception as e:
                return {
                    "error": str(e),
                    "tool_name": tool_name,
                    "status": "failed",
                }

        return {"error": f"Unknown tool: {tool_name}"}


# --------------------------------------------------------------------------- #
#  Smoke test: instantiates the agent and dispatches non-NVDA tools.
#  The NVDA full-audit tool is NOT invoked here because it requires
#  Windows + NVDA + pywinauto + Tesseract. To run end-to-end with the
#  full audit, run this on a Windows machine with those dependencies.
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    test_html = """
    <!DOCTYPE html>
    <html lang="en">
    <head><meta charset="UTF-8"><title>Self-Serve HR Portal</title></head>
    <body>
      <!-- No h1, skip from h4 to h2, then jump to h5 -->
      <h4>HR Self-Serve</h4>
      <p>Status chart:</p>
      <p><img src="status-chart.png" width="180" height="90"></p>

      <h2>Overview</h2>
      <h3>Click here</h3>
      <p>Team photo:</p>
      <p><img src="team.png" width="200" height="120"></p>

      <h5>Enrollment</h5>

      <div class="topbar">
        <a href="/dash">Dashboard</a>
        <a href="/time">Time cards</a>
        <a href="/benefits">Benefits</a>
        <a href="#"></a>
        <button type="button"></button>
      </div>

      <form>
        <input type="text" name="start" placeholder="Start date">
        <input type="text" name="end" placeholder="End date">
        <input type="image" src="submit.png" width="72" height="22">
      </form>
    </body>
    </html>
    """

    agent = LakshmiAgent(api_key=os.environ.get("OPENAI_API_KEY", "smoke-test"))

    print("=" * 70)
    print("LAKSHMI AGENT SMOKE TEST (direct dispatch, no LLM, no NVDA)")
    print("=" * 70)

    print("\n--- analyze_heading_structure ---")
    r = agent.execute_tool("analyze_heading_structure", {"html": test_html})
    print(f"missing_h1: {r.get('missing_h1')}")
    print(f"multiple_h1: {r.get('multiple_h1')}")
    print(f"skipped_levels: {len(r.get('skipped_levels', []))}")
    print(f"generic_headings: {len(r.get('generic_headings', []))}")
    print(f"hierarchy_issues: {len(r.get('hierarchy_issues', []))}")

    print("\n--- check_keyboard_navigation ---")
    r = agent.execute_tool("check_keyboard_navigation", {"html": test_html})
    print(f"focusable_elements_count: {r.get('focusable_elements_count')}")
    for el in r.get("focusable_elements", [])[:5]:
        print(f"  - {el.get('tag')} '{el.get('text', '')[:40]}'")

    print("\n--- run_nvda_full_audit ---")
    print("SKIPPED in this environment (needs Windows + NVDA + Tesseract).")
    print("To run: agent.execute_tool('run_nvda_full_audit', {'html': test_html})")
    print("on a Windows machine with the screen-reader stack configured.")

    print("\n" + "=" * 70)
    print("Smoke test complete.")
    print("=" * 70)
