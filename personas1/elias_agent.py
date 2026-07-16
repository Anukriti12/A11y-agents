"""
Elias Agent - Low Vision + Essential Tremor
Aligned to final 5-WCAG matrix: 1.3.5, 1.4.3, 1.4.12, 2.2.2, 2.4.8

Elias is a retired teacher with low vision who magnifies the screen to 200-300%
and also has essential tremor. His WAI persona story emphasizes:
  - Contrast strong enough to read text at high magnification
  - Layouts that reflow without clipping when text spacing is increased
  - Autoplay video and motion that trigger nausea (especially when magnified)
  - Breadcrumbs and location indicators so he knows where he is when only
    seeing a small portion of the page at a time
  - Autocomplete to reduce typing burden (tremor makes typing exhausting)

Tool-to-criterion mapping:
  - autocomplete_validator_agent      -> 1.3.5
  - Contrast_Checker_Agent (level=AA) -> 1.4.3
  - text_formatting_agent             -> 1.4.12
  - animation_detector_agent          -> 2.2.2
  - multiple_ways_checker_agent       -> 2.4.8 (breadcrumb evidence)

Contrast is set to AA (1.4.3, 4.5:1 for normal text) per the locked matrix.
The previous configuration ran at AAA (1.4.6, 7:1); that has been corrected
and the `level="AA"` argument is now passed explicitly so the behavior is
unambiguous.

The target_size and heading_structure tools from the previous Elias
configuration are removed - those criteria belong to Ade and Ian
respectively in the locked matrix.
"""

import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from personas.base_agent import BaseAgenticAgent
from tools1 import autocomplete_validator_agent
from tools1.Contrast_Checker_Agent import ContrastCheckerAgent
from tools1 import text_formatting_agent
from tools1 import animation_detector_agent
from tools1 import multiple_ways_checker_agent

load_dotenv()


ELIAS_SYSTEM_PROMPT = """
You are Elias, a retired teacher with low vision and essential tremor.

You use screen magnification (200-300% zoom). At that magnification you only
see a small portion of the page at a time, so you rely on breadcrumbs and
clear location indicators to know where you are. You cannot read pale text.
Layouts that don't reflow when you increase text spacing cut off content.
Autoplay video makes you nauseous, especially when magnified. Your tremor
makes typing tiring, so autocomplete is valuable.

Your WAI persona profile says directly:
  - "I need contrast strong enough to read text when I zoom in."
  - "When I increase line spacing, content should reflow, not clip."
  - "Autoplay videos while I'm reading make me nauseous."
  - "Breadcrumbs help me find my place when I'm zoomed in."
  - "Autocomplete saves me from typing every field by hand."

You evaluate pages against five WCAG criteria. Each criterion has one tool.
Call each tool AT MOST ONCE, then emit your verdict.

CRITERIA YOU EVALUATE:

  WCAG 1.3.5 Identify Input Purpose (Level AA)
    Form fields collecting personal data must use autocomplete attributes.
    Tool: validate_input_purpose
    FAIL signal: wcag_135_status == "FAIL"

  WCAG 1.4.3 Contrast Minimum (Level AA)
    Text must have at least 4.5:1 contrast (3:1 for large text).
    Tool: check_contrast_aa
    FAIL signal: wcag_143_status == "FAIL"

  WCAG 1.4.12 Text Spacing (Level AA)
    Content must remain visible and functional when spacing is increased
    (line-height 1.5x, letter-spacing 0.12em, word-spacing 0.16em, paragraph
    spacing 2x). No clipping, no overlap, no content loss.
    Tool: check_text_spacing_reflow
    FAIL signal: wcag_status == "fail" (NOTE: lowercase, unlike other tools)

  WCAG 2.2.2 Pause, Stop, Hide (Level A)
    Moving/blinking/auto-updating content must be controllable.
    Tool: detect_animations_and_motion
    FAIL signal: wcag_222_status == "FAIL"

  WCAG 2.4.8 Location (Level AAA)
    The user must be able to tell where they are within a set of pages.
    The primary mechanism for Elias is breadcrumbs.
    Tool: check_location_indicators
    FAIL signal: breadcrumbs list is empty AND the page is not a single-page
                 app/standalone (i.e., it has nav links suggesting it's part
                 of a larger site).
    INAPPLICABLE: page has no nav links and looks standalone.

OUTPUT FORMAT (return ONLY this JSON, no markdown, no preamble):
{
  "label": "passed" | "failed" | "inapplicable",
  "severity": "critical" | "serious" | "moderate" | "minor" | "N/A",
  "issues": [
    {
      "wcag": "X.X.X",
      "evidence": "Specific finding from the tool output with actual values",
      "persona_impact": "How this affects you as Elias",
      "recommendation": "Concrete fix"
    }
  ],
  "overall_assessment": "One-sentence summary in your voice as Elias"
}

SEVERITY CALIBRATION:
  - CRITICAL: 1.4.12 content clipping (you cannot read clipped text),
              2.2.2 autoplay video (triggers nausea immediately)
  - SERIOUS: 1.4.3 contrast violations (you cannot read pale text when zoomed),
             2.4.8 no breadcrumbs on a multi-page site (you lose your place)
  - MODERATE: 1.3.5 missing autocomplete (tiring but not blocking)

DECISION RULES:
  - If any criterion FAILs, the page label is "failed".
  - If all applicable criteria PASS, the page label is "passed".
  - If a tool returns INAPPLICABLE for a criterion, do not raise an issue
    for that criterion. The page can still pass overall.
"""


class EliasAgent(BaseAgenticAgent):
    def __init__(self, api_key):
        super().__init__(api_key, persona_name="Elias")

        self.autocomplete_agent = autocomplete_validator_agent.AutocompleteValidatorAgent()
        self.contrast_agent = ContrastCheckerAgent(level="AA")
        self.text_formatting_agent_inst = text_formatting_agent.TextFormattingAgent()
        self.animation_agent = animation_detector_agent.AnimationDetectorAgent()
        self.multiple_ways_agent = multiple_ways_checker_agent.MultipleWaysCheckerAgent()

        self.tool_dispatcher = {
            "validate_input_purpose": self.autocomplete_agent.execute,
            "check_contrast_aa": self.contrast_agent.execute,
            "check_text_spacing_reflow": self.text_formatting_agent_inst.execute,
            "detect_animations_and_motion": self.animation_agent.execute,
            "check_location_indicators": self.multiple_ways_agent.execute,
        }

    def get_system_prompt(self):
        return ELIAS_SYSTEM_PROMPT

    def get_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "validate_input_purpose",
                    "description": """
[WHAT] Static analysis of autocomplete attributes on form fields. Identifies
fields collecting personal data (name, email, phone, address, payment) that
should have autocomplete attributes, validates autocomplete values against
WCAG 1.3.5's token list, and flags autocomplete="off" on personal-data fields.

[WHEN] Call when the page has form fields (<input>, <select>, <textarea>).
INAPPLICABLE on pages with no form fields.

[COVERS] WCAG 1.3.5 Identify Input Purpose.

[RETURNS] A dict with these REAL keys:
  - fields_analyzed: integer count of relevant inputs
  - fields_with_autocomplete: integer count with valid autocomplete
  - fields_missing_autocomplete: list of {id, name, type, placeholder, label}
    for fields that need autocomplete but lack it
  - fields_with_invalid_autocomplete: list with invalid_autocomplete_value
    showing the broken value
  - fields_with_autocomplete_off: list of fields with autocomplete="off"
    on personal-data fields
  - wcag_135_status: "PASS" | "FAIL" | "INAPPLICABLE"
  - tool_name: "AutocompleteValidatorAgent"

[INTERPRETATION FOR ELIAS]
- Read wcag_135_status directly.
- Severity is MODERATE: missing autocomplete makes Elias type more, which
  is tiring with tremor, but does not block task completion.
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
                    "name": "check_contrast_aa",
                    "description": """
[WHAT] Measures the contrast ratio between text and its background for every
text element on the page. Applies WCAG's contrast math directly, including
alpha composition for transparent foregrounds and backgrounds. Compares
against the WCAG 1.4.3 AA thresholds (4.5:1 for normal text, 3:1 for large
text >= 24px or >= 19px bold).

[WHEN] Call on every page with text content.

[COVERS] WCAG 1.4.3 Contrast Minimum (Level AA).

[RETURNS] A dict with these REAL keys:
  - level: "AA"
  - threshold_normal: 4.5
  - threshold_large: 3.0
  - text_elements_analyzed: integer
  - passing_count: integer
  - violation_count: integer
  - ambiguous_count: integer (transparent backgrounds where exact ratio
    couldn't be computed)
  - exempt_count: integer (disabled controls, decorative text)
  - violations: list of {tag, text, color, background_color, ratio,
    required_ratio, is_large_text}
  - ambiguous: list of borderline cases
  - wcag_143_status: "PASS" | "FAIL" | "INAPPLICABLE"
  - tool_name: "ContrastCheckerAgent"

[INTERPRETATION FOR ELIAS]
- Read wcag_143_status directly.
- Severity is SERIOUS - pale text becomes unreadable when zoomed to 200-300%.
- Pull specific failing elements from violations for the evidence string.
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
                    "name": "check_text_spacing_reflow",
                    "description": """
[WHAT] Applies the WCAG 1.4.12 spacing overrides (line-height 1.5,
letter-spacing 0.12em, word-spacing 0.16em, paragraph margin 2em) and then
re-renders the page in a headless browser to detect text clipping, content
loss, or layout breakage.

[WHEN] Call on every page that has text content (paragraphs, list items,
table cells, headings, labels, links). INAPPLICABLE on pages with no text.

[COVERS] WCAG 1.4.12 Text Spacing.

[RETURNS] A dict with these REAL keys:
  - wcag_status: "pass" | "fail" | "inapplicable"
    NOTE: this tool uses LOWERCASE values. The other tools in your set
    use UPPERCASE. Pay attention to the case when reading the verdict.
  - spacing_applied: boolean - whether the overrides were injected
  - overflow: {status: "pass" | "fail", issues: list of clipped elements}
  - content_integrity: {status: "pass" | "fail", details: ...}

[INTERPRETATION FOR ELIAS]
- 1.4.12 FAIL: wcag_status == "fail" (lowercase)
- 1.4.12 INAPPLICABLE: wcag_status == "inapplicable" (lowercase)
- Severity is CRITICAL when overflow.issues is non-empty - Elias literally
  cannot read clipped text.
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
                    "name": "detect_animations_and_motion",
                    "description": """
[WHAT] Detects all motion on the page: CSS @keyframes animations, CSS
transitions, autoplay <video>/<audio>, animated GIFs, common JS animation
libraries. Checks for prefers-reduced-motion handling and pause/stop/hide
controls.

[WHEN] Call when the HTML contains motion-related elements: <video>,
<audio>, animated GIFs, CSS @keyframes / animation declarations, or
animation libraries.

[COVERS] WCAG 2.2.2 Pause, Stop, Hide.

[RETURNS] A dict with these REAL keys:
  - wcag_222_status: "PASS" | "FAIL" | "INAPPLICABLE" - trust this directly
  - total_motion_count: integer
  - css_animations_count: integer
  - css_transitions_count: integer
  - autoplay_count: integer - autoplay media running >5 seconds
  - animated_gifs_count: integer
  - js_animation_libs: list of detected libraries
  - reduced_motion_result: dict with honored/not-honored info
  - pause_mechanism: dict with has_pause_control etc.
  - target_size_issues: list (IGNORE for Elias - this is for other personas)

[INTERPRETATION FOR ELIAS]
- Read wcag_222_status directly.
- Severity is CRITICAL when autoplay_count > 0 - autoplay triggers nausea
  immediately.
- Ignore the target_size_issues key entirely - it's not in Elias's matrix.
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
                    "name": "check_location_indicators",
                    "description": """
[WHAT] Detects four navigation/location mechanisms: navigation links,
search, sitemap, and breadcrumbs. For Elias's 2.4.8 evaluation, the
breadcrumb list is the primary evidence - it's the WCAG-recognized way
to indicate location within a site.

[WHEN] Call on every page that appears to be part of a larger site (has
navigation links, header/footer with multiple links, etc.).

[COVERS] WCAG 2.4.8 Location.

[RETURNS] A dict with these REAL keys:
  - applicable: boolean - whether the tool considers this a multi-page site
  - applicability_reason: string explaining the verdict
  - navigation_links: list of detected nav links
  - search: list of detected search forms
  - sitemap: list of sitemap links
  - breadcrumbs: list of detected breadcrumb structures
  - methods_found: integer (sum of the four lists' presence)
  - tool_name: "MultipleWaysCheckerAgent"

[INTERPRETATION FOR ELIAS]
- 2.4.8 FAIL: applicable == true AND breadcrumbs is empty.
- 2.4.8 PASS: applicable == true AND breadcrumbs is non-empty.
- 2.4.8 INAPPLICABLE: applicable == false (the tool determined this page
  is standalone or exempt, e.g. checkout, login, error page).
- The tool reports nav, search, and sitemap too. For Elias's 2.4.8
  specifically, focus on breadcrumbs. The other methods are out of scope.
- Severity is SERIOUS - without breadcrumbs, Elias loses his place when
  zoomed in.
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
#  Smoke test: dispatches each tool directly. No LLM call.
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    # HTML designed to trip Elias's five criteria:
    #   1.3.5: form fields with no autocomplete
    #   1.4.3: pale grey text on white (well below 4.5:1)
    #   1.4.12: fixed-height container that clips text when spacing increased
    #   2.2.2: autoplay video
    #   2.4.8: nav links present but no breadcrumb trail
    test_html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <title>Pharmacy Refill - Step 2</title>
      <style>
        body { font-size: 10px; color: #c6c6c6; background: #ffffff; }
        .zoom-trap {
          height: 40px;
          overflow: hidden;
          border: 1px solid #ddd;
        }
      </style>
    </head>
    <body>
      <nav>
        <a href="/home">Home</a>
        <a href="/refills">Refills</a>
        <a href="/account">Account</a>
      </nav>

      <h1>Prescription Refill</h1>
      <p style="color:#bbbbbb;background:#ffffff;">
        Pale grey notice: your refill request will expire if not confirmed.
      </p>

      <p class="zoom-trap">
        When you enlarge text to 200% this paragraph stays in a fixed-height
        container and words get cut off at the edges, making it impossible
        to read the full warning message.
      </p>

      <video autoplay loop muted playsinline width="200" height="100"></video>

      <form>
        <label>Full name<input type="text" name="patient_name"></label>
        <label>Email<input type="email" name="email"></label>
        <label>Phone<input type="tel" name="phone"></label>
        <label>Card<input type="text" name="card_number"></label>
        <button type="submit">Submit Refill</button>
      </form>
    </body>
    </html>
    """

    agent = EliasAgent(api_key=os.environ.get("OPENAI_API_KEY", "smoke-test"))

    print("=" * 70)
    print("ELIAS AGENT SMOKE TEST (direct tool dispatch, no LLM)")
    print("=" * 70)

    print("\n--- validate_input_purpose ---")
    r = agent.execute_tool("validate_input_purpose", {"html": test_html})
    print(f"wcag_135_status: {r.get('wcag_135_status')}")
    print(f"fields_missing_autocomplete: {len(r.get('fields_missing_autocomplete', []))}")

    print("\n--- check_contrast_aa ---")
    r = agent.execute_tool("check_contrast_aa", {"html": test_html})
    print(f"wcag_143_status: {r.get('wcag_143_status')}")
    print(f"violation_count: {r.get('violation_count')}")
    print(f"passing_count: {r.get('passing_count')}")

    print("\n--- check_text_spacing_reflow ---")
    r = agent.execute_tool("check_text_spacing_reflow", {"html": test_html})
    print(f"wcag_status (lowercase): {r.get('wcag_status')}")
    print(f"overflow.status: {r.get('overflow', {}).get('status')}")
    print(f"overflow.issues: {len(r.get('overflow', {}).get('issues', []))}")

    print("\n--- detect_animations_and_motion ---")
    r = agent.execute_tool("detect_animations_and_motion", {"html": test_html})
    print(f"wcag_222_status: {r.get('wcag_222_status')}")
    print(f"autoplay_count: {r.get('autoplay_count')}")
    print(f"total_motion_count: {r.get('total_motion_count')}")

    print("\n--- check_location_indicators ---")
    r = agent.execute_tool("check_location_indicators", {"html": test_html})
    print(f"applicable: {r.get('applicable')}")
    print(f"breadcrumbs: {len(r.get('breadcrumbs', []))}")
    print(f"methods_found: {r.get('methods_found')}")

    print("\n" + "=" * 70)
    print("Smoke test complete.")
    print("=" * 70)
