"""
Ade Agent - Limited Mobility (Keyboard + Voice Control)
Aligned to final 5-WCAG matrix: 2.1.1, 2.2.1, 2.4.3, 2.4.7, 2.5.5

Ade is a project manager who cannot use a mouse. Her WAI persona story
emphasizes keyboard-only operation, voice control as a slower alternative,
adaptive pointing devices that lack mouse precision, and a need to see
where focus is at all times. Her five criteria correspond to those needs.

Tool-to-criterion mapping:
  - keyboard_navigation_agent   -> 2.1.1 (enumeration)
  - custom_widget_keyboard_agent -> 2.1.1 (violation detection: mouse-only,
                                          hover-only, ARIA widget issues)
  - timing_checker_agent        -> 2.2.1
  - focus_order_validator_agent -> 2.4.3
  - focus_visible_validator_agent -> 2.4.7
  - target_size_validator_agent (level="AAA") -> 2.5.5

Target size is instantiated at AAA (44x44px) because 2.5.5 is the AAA SC.
The form_validator tool from the previous Ade configuration is removed -
3.3.2 is not in the final matrix and was replaced with 2.4.3 / 2.4.7 / 2.5.5.
"""

import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from personas.base_agent import BaseAgenticAgent
from tools import keyboard_navigation_agent
from tools import custom_widget_keyboard_agent
from tools import timing_checker_agent
from tools import focus_order_validator_agent
from tools import focus_visible_validator_agent
from tools import target_size_validator_agent

load_dotenv()


ADE_SYSTEM_PROMPT = """
You are Ade, a project manager with limited mobility. You cannot use a mouse.
You navigate by keyboard and voice control.

Your WAI persona profile says directly:
  - "I use the keyboard for everything. If I can't reach something with Tab,
     it doesn't exist for me."
  - "Voice control works but it is slow. Time limits are a real barrier."
  - "I need to see where the keyboard focus is at all times - if it disappears,
     I lose my place."
  - "Small buttons are hard for my adaptive pointing device to land on."
  - "When Tab jumps around the page randomly, I get disoriented."

You evaluate pages against five WCAG criteria. Each criterion has one or two
tools that produce evidence. Call each relevant tool AT MOST ONCE, then
emit your verdict.

CRITERIA YOU EVALUATE:

  WCAG 2.1.1 Keyboard (Level A)
    All interactive elements must be operable by keyboard.
    Tools: check_keyboard_focusables (enumeration) +
           detect_keyboard_violations (mouse-only, hover-only, ARIA issues)
    FAIL signals: detect_keyboard_violations -> wcag_211_status == "FAIL"
                  OR check_keyboard_focusables -> focusable_elements_count == 0
                  on a page with visible interactive HTML.

  WCAG 2.2.1 Timing Adjustable (Level A)
    Time limits must be controllable, extendable, or disable-able.
    Tool: check_timing_and_timeouts
    FAIL signal: issue_found == true

  WCAG 2.4.3 Focus Order (Level A)
    Tab order must follow a logical, predictable sequence.
    Tool: validate_focus_order
    FAIL signal: wcag_243_status == "FAIL"

  WCAG 2.4.7 Focus Visible (Level AA)
    Keyboard focus must have a visible indicator at all times.
    Tool: validate_focus_visible
    FAIL signal: wcag_247_status == "FAIL"

  WCAG 2.5.5 Target Size (Level AAA)
    Interactive targets must be at least 44x44 CSS pixels (with exceptions
    for inline text links and native user-agent controls).
    Tool: validate_target_size
    FAIL signal: wcag_255_status == "FAIL"

OUTPUT FORMAT (return ONLY this JSON, no markdown, no preamble):
{
  "label": "passed" | "failed" | "inapplicable",
  "severity": "critical" | "serious" | "moderate" | "minor" | "N/A",
  "issues": [
    {
      "wcag": "X.X.X",
      "evidence": "Specific finding from the tool output with actual values",
      "persona_impact": "How this affects you as Ade",
      "recommendation": "Concrete fix"
    }
  ],
  "overall_assessment": "One-sentence summary in your voice as Ade"
}

SEVERITY CALIBRATION:
  - CRITICAL: 2.1.1 mouse-only interactives (you cannot reach them at all),
              2.2.1 time limit with no control (voice is too slow to beat it),
              2.4.7 focus not visible (you lose your place completely)
  - SERIOUS: 2.4.3 illogical tab order (you get disoriented),
             2.5.5 undersized targets (your adaptive device misses them)
  - MODERATE: 2.5.5 borderline targets (close to 44px),
              2.4.3 minor ordering issues

DECISION RULES:
  - If any criterion FAILs, the page label is "failed".
  - If all applicable criteria PASS, the page label is "passed".
  - If the HTML has no interactive elements at all, the page label is "inapplicable".
  - For 2.1.1: trust detect_keyboard_violations -> wcag_211_status. The
    check_keyboard_focusables tool is supplemental evidence, not a verdict.
"""


class AdeAgent(BaseAgenticAgent):
    def __init__(self, api_key):
        super().__init__(api_key, persona_name="Ade")

        self.keyboard_agent = keyboard_navigation_agent.KeyboardNavigationAgent()
        self.custom_widget_agent = custom_widget_keyboard_agent.CustomWidgetKeyboardAgent()
        self.timing_agent = timing_checker_agent.TimingCheckerAgent()
        self.focus_order_agent = focus_order_validator_agent.FocusOrderValidatorAgent()
        self.focus_visible_agent = focus_visible_validator_agent.FocusVisibleValidatorAgent()
        self.target_size_agent = target_size_validator_agent.TargetSizeValidatorAgent(level="AAA")

        self.tool_dispatcher = {
            "check_keyboard_focusables": self.keyboard_agent.execute,
            "detect_keyboard_violations": self.custom_widget_agent.execute,
            "check_timing_and_timeouts": self.timing_agent.execute,
            "validate_focus_order": self.focus_order_agent.execute,
            "validate_focus_visible": self.focus_visible_agent.execute,
            "validate_target_size": self.target_size_agent.execute,
        }

    def get_system_prompt(self):
        return ADE_SYSTEM_PROMPT

    def get_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "check_keyboard_focusables",
                    "description": """
[WHAT] Enumerates all keyboard-focusable elements on the page (visible
<a href>, non-disabled <button>/<input>/<select>/<textarea>, <details>,
elements with tabindex>=0).

[WHEN] Call once when the page has any interactive HTML.

[COVERS] Supplemental evidence for WCAG 2.1.1 Keyboard. Pair this with
detect_keyboard_violations - this tool tells you what IS focusable;
that one tells you what SHOULD BE focusable but isn't.

[RETURNS] A dict with these REAL keys:
  - focusable_elements: list of {element_index, tag, text, id, class}
  - focusable_elements_count: integer
  - tool_name: "KeyboardNavigationAgent"

[INTERPRETATION FOR ADE]
- This tool alone does not produce a verdict. It produces evidence that
  the LLM combines with detect_keyboard_violations.
- A focusable_elements_count of 0 on a page with obvious interactive
  HTML is a strong FAIL signal.
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
                    "name": "detect_keyboard_violations",
                    "description": """
[WHAT] Detects three classes of 2.1.1 violations: (1) mouse-only
interactives (divs/spans with onclick but no role+tabindex+keyboard
handler), (2) hover-only behaviors (CSS that activates content on :hover
with no :focus equivalent), (3) ARIA widget issues (elements with role=
"button"/"link"/etc. lacking the required keyboard-accessible attributes).

[WHEN] Call once on every page with interactive elements.

[COVERS] WCAG 2.1.1 Keyboard (violation detection).

[RETURNS] A dict with these REAL keys:
  - applicable: boolean - false if no interactive elements present
  - mouse_only_interactives: list of elements with click handlers but
    no keyboard path
  - hover_only_behaviors: list of CSS selectors that show content on
    :hover without a matching :focus rule
  - aria_widget_issues: list of widgets with bad ARIA (e.g., role="button"
    missing tabindex, role="checkbox" missing aria-checked)
  - total_issues: integer - sum of the three lists
  - wcag_211_status: "PASS" | "FAIL" | "INAPPLICABLE"
  - tool_name: "CustomWidgetKeyboardAgent"

[INTERPRETATION FOR ADE]
- Read wcag_211_status. If FAIL, emit a 2.1.1 issue.
- Severity is CRITICAL when mouse_only_interactives is non-empty
  (Ade literally cannot reach those elements).
- Use the specific finding (e.g., "3 divs with onclick but no role")
  as the evidence string.
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
                    "name": "check_timing_and_timeouts",
                    "description": """
[WHAT] Detects time limits on the page: <meta http-equiv="refresh"> tags,
text mentioning session timeouts or countdowns, and the presence (or
absence) of controls to extend, adjust, or disable the time limit.

[WHEN] Call when the HTML contains meta refresh, the words
"session"/"timeout"/"expires"/"countdown", or any form likely to enforce
a time limit (checkout, login).

[COVERS] WCAG 2.2.1 Timing Adjustable.

[RETURNS] A dict with these REAL keys:
  - meta_refreshes: list of detected meta refresh declarations
  - meta_refreshes_count: integer
  - timeout_ui_elements: list of elements whose text suggests a time limit
  - timeout_ui_elements_count: integer
  - timeout_controls: list of elements that extend/adjust time
    (buttons like "Extend session", "Stay signed in")
  - timeout_controls_count: integer
  - issue_found: boolean - true if a time limit is detected with no controls
  - summary: human-readable string
  - tool_name: "TimingCheckerAgent"

[INTERPRETATION FOR ADE]
- 2.2.1 FAIL: issue_found == true
- INAPPLICABLE: all four counts are zero
- Severity is CRITICAL - voice control is too slow to beat a hard timeout.
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
                    "name": "validate_focus_order",
                    "description": """
[WHAT] Walks the page's tab sequence by simulating Tab key presses and
records the actual focus order. Compares against DOM source order and
visual reading order (top-to-bottom, left-to-right). Also flags positive
tabindex values (which break natural order) and modal dialogs without
aria-modal.

[WHEN] Call when the page has 2+ focusable elements.

[COVERS] WCAG 2.4.3 Focus Order.

[RETURNS] A dict with these REAL keys:
  - applicable: boolean
  - applicability_reason: string
  - focusables_in_dom: integer
  - tab_sequence_length: integer
  - tab_sequence: list of elements in the order Tab visits them
  - positive_tabindex_elements: list of elements with tabindex > 0
    (these break natural tab order)
  - dom_order_mismatches: list of cases where tab order != DOM order
  - visual_order_mismatches: list of cases where tab order != visual order
  - unreachable_elements: list of focusable elements never visited by Tab
  - modal_issues: list of modal dialogs missing aria-modal or focus trapping
  - wcag_243_status: "PASS" | "FAIL" | "INAPPLICABLE"
  - tool_name: "FocusOrderValidatorAgent"

[INTERPRETATION FOR ADE]
- Read wcag_243_status directly. The tool already encodes the verdict.
- Severity: SERIOUS for mismatches, MODERATE for positive tabindex alone.
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
                    "name": "validate_focus_visible",
                    "description": """
[WHAT] For each focusable element, compares its computed style in the
unfocused vs focused state. Flags elements with no visible change,
elements that rely on color-only changes (a 4.1 contrast issue), elements
with weak indicators (less than 2px outline), and CSS rules using
outline:none without a compensating alternative indicator.

[WHEN] Call on every page that has focusable elements.

[COVERS] WCAG 2.4.7 Focus Visible.

[RETURNS] A dict with these REAL keys:
  - applicable: boolean
  - applicability_reason: string
  - elements_tested: integer
  - elements_with_visible_focus: integer
  - elements_without_visible_focus: list of elements with no style diff
  - color_only_indicators: list of elements where only color changes
    (concerning for contrast but not a hard FAIL)
  - weak_indicators: list of elements with thin outlines
  - outline_none_violations: list of CSS rules that strip focus styling
    without replacement
  - wcag_247_status: "PASS" | "FAIL" | "INAPPLICABLE"
  - tool_name: "FocusVisibleValidatorAgent"

[INTERPRETATION FOR ADE]
- Read wcag_247_status directly.
- FAIL means at least one focusable element has no visible focus state.
- Severity is CRITICAL for elements_without_visible_focus (Ade cannot
  see where focus is), SERIOUS for outline_none_violations.
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
                    "name": "validate_target_size",
                    "description": """
[WHAT] Measures every interactive element's bounding box and checks
against the WCAG 2.5.5 AAA threshold (44x44 CSS pixels). Applies WCAG's
exceptions: native user-agent controls (checkbox, radio, select with no
author dimensions) and inline text links inside running text are exempt.

[WHEN] Call once on every page with interactive elements.

[COVERS] WCAG 2.5.5 Target Size (Enhanced, AAA, 44px).

[RETURNS] A dict with these REAL keys:
  - level: "AAA"
  - wcag_sc: "2.5.5"
  - threshold_px: 44
  - targets_analyzed: integer
  - passing_count: integer
  - violation_count: integer - true 2.5.5 violations after exceptions
  - exempt_inline_count: integer - inline text links (don't count as fails)
  - exempt_ua_control_count: integer - native checkbox/radio/select
  - violations: list of {tag, text, width_px, height_px, x, y, shortfall, ...}
  - exempt_inline_samples: list of inline exemptions
  - exempt_ua_samples: list of UA control exemptions
  - wcag_255_status: "PASS" | "FAIL" | "INAPPLICABLE"
  - small_targets, small_targets_count, issue_found: backward-compat keys
  - tool_name: "TargetSizeValidatorAgent"

[INTERPRETATION FOR ADE]
- Read wcag_255_status directly.
- The violation_count already excludes exemptions, so it is the number
  of true 2.5.5 violations.
- Severity: SERIOUS if violation_count >= 3, MODERATE if 1-2.
- INAPPLICABLE means no interactive elements.
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
#  Smoke test: dispatches each tool directly, prints high-signal keys.
#  No LLM, no OPENAI_API_KEY needed.
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    # HTML designed to trip each of Ade's five criteria:
    #   2.1.1: div with onclick, no role/tabindex (mouse-only)
    #   2.2.1: meta refresh, no extend control
    #   2.4.3: positive tabindex values out of DOM order
    #   2.4.7: outline:none on focusable elements
    #   2.5.5: tiny buttons below 44x44
    test_html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <meta http-equiv="refresh" content="30">
      <title>Quick Checkout</title>
      <style>
        button:focus, a:focus, input:focus { outline: none; }
        .tiny { width: 20px; height: 20px; padding: 0; border: 0; }
        .clickable { cursor: pointer; background: #eee; padding: 4px; }
      </style>
    </head>
    <body>
      <h1>Checkout</h1>
      <p>Your session will expire in 30 seconds.</p>

      <div class="clickable" onclick="alert('clicked')">Add to cart</div>

      <form>
        <input type="text" tabindex="3" name="city" placeholder="City">
        <input type="text" tabindex="1" name="address" placeholder="Address">
        <input type="text" tabindex="2" name="zip" placeholder="ZIP">

        <button class="tiny">+</button>
        <button class="tiny">-</button>
        <button type="submit">Submit</button>
      </form>
    </body>
    </html>
    """

    agent = AdeAgent(api_key=os.environ.get("OPENAI_API_KEY", "smoke-test"))

    print("=" * 70)
    print("ADE AGENT SMOKE TEST (direct tool dispatch, no LLM)")
    print("=" * 70)

    print("\n--- check_keyboard_focusables ---")
    r = agent.execute_tool("check_keyboard_focusables", {"html": test_html})
    print(f"focusable_elements_count: {r.get('focusable_elements_count')}")

    print("\n--- detect_keyboard_violations ---")
    r = agent.execute_tool("detect_keyboard_violations", {"html": test_html})
    print(f"wcag_211_status: {r.get('wcag_211_status')}")
    print(f"mouse_only_interactives: {len(r.get('mouse_only_interactives', []))}")
    print(f"hover_only_behaviors: {len(r.get('hover_only_behaviors', []))}")
    print(f"aria_widget_issues: {len(r.get('aria_widget_issues', []))}")

    print("\n--- check_timing_and_timeouts ---")
    r = agent.execute_tool("check_timing_and_timeouts", {"html": test_html})
    print(f"issue_found: {r.get('issue_found')}")
    print(f"meta_refreshes_count: {r.get('meta_refreshes_count')}")
    print(f"timeout_controls_count: {r.get('timeout_controls_count')}")

    print("\n--- validate_focus_order ---")
    r = agent.execute_tool("validate_focus_order", {"html": test_html})
    print(f"wcag_243_status: {r.get('wcag_243_status')}")
    print(f"positive_tabindex_elements: {len(r.get('positive_tabindex_elements', []))}")
    print(f"dom_order_mismatches: {len(r.get('dom_order_mismatches', []))}")

    print("\n--- validate_focus_visible ---")
    r = agent.execute_tool("validate_focus_visible", {"html": test_html})
    print(f"wcag_247_status: {r.get('wcag_247_status')}")
    print(f"elements_without_visible_focus: {len(r.get('elements_without_visible_focus', []))}")
    print(f"outline_none_violations: {len(r.get('outline_none_violations', []))}")

    print("\n--- validate_target_size ---")
    r = agent.execute_tool("validate_target_size", {"html": test_html})
    print(f"wcag_255_status: {r.get('wcag_255_status')}")
    print(f"violation_count: {r.get('violation_count')}")
    print(f"passing_count: {r.get('passing_count')}")

    print("\n" + "=" * 70)
    print("Smoke test complete.")
    print("=" * 70)
