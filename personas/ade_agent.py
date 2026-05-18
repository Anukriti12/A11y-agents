"""
Ade Agent - Limited Mobility (Keyboard-Only Navigation)
Refactored to use BaseAgenticAgent
"""

import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from personas.base_agent import BaseAgenticAgent
from tools import keyboard_navigation_agent
from tools import target_size_validator_agent
from tools import timing_checker_agent
from tools import form_validator_agent

load_dotenv()

ADE_SYSTEM_PROMPT = """
You are Ade, a project manager with limited mobility who uses keyboard and voice control exclusively.

You cannot use a mouse. Every interaction must be keyboard-accessible or voice-controllable.

Critical barriers for you:
- Elements unreachable by keyboard → BLOCKS YOU COMPLETELY
- Time limits that expire before you complete tasks → VOICE IS SLOWER
- Tiny click targets your adaptive devices can't hit → FRUSTRATING MISCLICKS
- Forms without labels → VOICE CAN'T IDENTIFY FIELDS
- Keyboard traps where Tab gets stuck → YOU'RE STUCK

Your needs:
- All interactive elements keyboard accessible (WCAG 2.1.1)
- Logical tab order (WCAG 2.4.3)
- Targets ≥44x44px (WCAG 2.5.5)
- No time limits or ability to extend (WCAG 2.2.1)
- Proper form labels (WCAG 3.3.2)

Output ONLY valid JSON (no preamble, no markdown):
{
  "label": "passed" | "failed" | "inapplicable",
  "severity": "critical" | "serious" | "moderate" | "minor" | "N/A",
  "issues": [
    {
      "wcag": "X.X.X",
      "evidence": "What the tool found",
      "persona_impact": "Why this affects YOU as Ade",
      "recommendation": "How to fix"
    }
  ],
  "overall_assessment": "Brief summary"
}

SEVERITY CALIBRATION:
- CRITICAL: Completely blocks you (keyboard trap, no keyboard access)
- SERIOUS: Major barrier (tiny targets, missing labels, time limits)
- MODERATE: Inconvenient (poor tab order)
- MINOR: Best practice issue

DECISION CRITERIA:
- FAILED = Found ≥1 violation
- PASSED = All checks passed
- Call each tool AT MOST ONCE
- Stop when you have enough evidence

INTERPRETING TOOL RESULTS:
- If keyboard_traps is NOT EMPTY → FAILED (critical)
- If missing_keyboard_access is NOT EMPTY → FAILED (critical)
- If undersized_targets is NOT EMPTY → FAILED (serious)
- If time_limits_found > 0 AND user_control_available = false → FAILED (serious)
- If unlabeled_inputs is NOT EMPTY → FAILED (serious)
"""


class AdeAgent(BaseAgenticAgent):
    def __init__(self, api_key):
        super().__init__(api_key, persona_name="Ade")
        
        self.keyboard_agent = keyboard_navigation_agent.KeyboardNavigationAgent()
        self.target_size_agent = target_size_validator_agent.TargetSizeValidatorAgent()
        self.timing_agent = timing_checker_agent.TimingCheckerAgent()
        self.form_agent = form_validator_agent.FormValidationAgent()
        
        self.tool_dispatcher = {
            "check_keyboard_navigation": self.keyboard_agent.execute,
            "validate_target_size": self.target_size_agent.execute,
            "check_timing_and_timeouts": self.timing_agent.execute,
            "validate_form_errors_and_labels": self.form_agent.execute
        }
    
    def get_system_prompt(self):
        return ADE_SYSTEM_PROMPT
    
    def get_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "check_keyboard_navigation",
                    "description": """
[WHAT] Analyzes HTML for keyboard navigation barriers.

[WHEN] Use when:
- HTML has ANY interactive elements (buttons, links, inputs, divs with onclick)
- Checking if page is navigable without mouse
- HTML has modal dialogs, popups, or complex UI
- Evaluating focus order and keyboard traps

[WHO] CRITICAL for Ade (keyboard-only, limited mobility)
- Ade: Cannot use mouse, 100% keyboard/voice dependent
- Also helps: Lakshmi (blind screen reader user)

[RETURNS]
- keyboard_traps: List of elements where Tab gets stuck (if NOT EMPTY → FAILED critical)
- missing_keyboard_access: Interactive elements with no keyboard handler (if NOT EMPTY → FAILED critical)
- tab_order_issues: Illogical focus sequence (if present → FAILED moderate)
- focusable_elements: All keyboard-accessible elements

[DON'T USE] Skip when:
- Page is text-only with no interactive elements
- Already confirmed no interactive elements from other checks
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
                    "name": "validate_target_size",
                    "description": """
[WHAT] Checks for interactive elements smaller than 44x44 pixels.

[WHEN] Use when:
- HTML has buttons, links, form controls, clickable elements
- Page has icon buttons, close buttons, small UI controls
- Elements have explicit width/height styling
- Evaluating mobile/touch interfaces

[WHO] CRITICAL for Ade (limited dexterity with adaptive devices)
- Ade: Adaptive pointing devices lack precision - tiny targets impossible to hit
- Also helps: Elias (low vision + tremor)

[RETURNS]
- undersized_targets: List of elements < 44x44px (if NOT EMPTY → FAILED serious)
- target_dimensions: Width × height for each element
- spacing_violations: Targets too close together

[DON'T USE] Skip when:
- No clickable elements on page
- Elements have no custom sizing (default browser styles usually OK)
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
                    "name": "check_timing_and_timeouts",
                    "description": """
[WHAT] Identifies time limits, session timeouts, auto-refresh.

[WHEN] Use when:
- HTML contains <meta http-equiv="refresh"> (AUTOMATIC TRIGGER)
- Text mentions "expires", "timeout", "seconds", "minutes"
- Checking forms with session limits
- Login/checkout pages (often have timeouts)
- Page has countdown timers

[WHO] CRITICAL for Ade (voice control is SLOWER than mouse)
- Ade: Voice control takes 2-3x longer - time limits block completely
- Also helps: Sophie (IDD - needs extra time), Elias (tremor - slower)

[RETURNS]
- time_limits_found: Count of timeouts/refreshes detected
- timeout_duration: How long before expiration
- user_control_available: Can user turn off/adjust/extend? (if false → FAILED serious)

[DON'T USE] Skip when:
- No meta refresh, no timeout text visible
- Static content page with no dynamic behavior
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
                    "name": "validate_form_errors_and_labels",
                    "description": """
[WHAT] Checks forms for proper labels, error identification, and input purpose.

[WHEN] Use when:
- HTML contains <form>, <input>, <select>, <textarea> (AUTOMATIC TRIGGER)
- Checking if voice control can identify fields
- Evaluating error messages and validation
- Page has text inputs, checkboxes, radio buttons

[WHO] CRITICAL for Ade (voice needs labels to identify fields)
- Ade: Uses voice commands like "Click Email field" - requires programmatic labels
- Also helps: Lakshmi (screen reader), Sophie (needs clear errors)

[RETURNS]
- unlabeled_inputs: Fields missing <label> or aria-label (if NOT EMPTY → FAILED serious)
- vague_errors: Error messages like "Invalid" without specifics
- missing_autocomplete: Fields missing autocomplete attributes
- label_name_mismatch: Visual ≠ accessible name (breaks voice)

[DON'T USE] Skip when:
- No forms or input fields on page
- Already confirmed no forms from HTML scan
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
                return {
                    "error": str(e),
                    "tool_name": tool_name,
                    "status": "failed"
                }
        
        return {"error": f"Unknown tool: {tool_name}"}


# Test code - ONLY runs when you execute this file directly
if __name__ == "__main__":
    import json
    
    test_html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <meta http-equiv="refresh" content="30">
      <title>Checkout - Step 1</title>
      <style>
        .tiny-btn { width: 20px; height: 20px; }
      </style>
    </head>
    <body>
      <header>
        <h1>Fast Checkout</h1>
      </header>
      <main>
        <section>
          <h2>Billing Information</h2>
          <p>Please complete your checkout in the next 30 seconds.</p>
          <form id="billing-form">
            <input type="text" name="address" placeholder="Address">
            <input type="text" name="city" placeholder="City">
            <button type="submit">Submit</button>
          </form>
        </section>
        <section>
          <h2>Add a tip?</h2>
          <button class="tiny-btn">+</button>
          <button class="tiny-btn">-</button>
        </section>
      </main>
    </body>
    </html>
    """
    
    agent = AdeAgent(os.environ["OPENAI_API_KEY"])
    result = agent.evaluate(test_html)
    
    print("=" * 70)
    print("ADE AGENT TEST")
    print("=" * 70)
    print(json.dumps(result, indent=2))