"""
Condition E: Vanilla-Agent

Generic accessibility-expert agent with access to ALL 18 specialized
accessibility tools, but WITHOUT persona backstory. The LLM must decide
which tools to call based on the WCAG criteria alone, not persona-specific
guidance.

This completes Lucy's 2x2 ablation design:

                        no tools               with tools
    no persona    Vanilla-LLM  (D)      Vanilla-Agent  (E)
    with persona  Persona-LLM  (B)      Persona-Agent  (C)

  Main effect of persona = (B - D) + (C - E), averaged
  Main effect of tools   = (E - D) + (C - B), averaged
  Interaction            = (C - B) - (E - D)

Reuses BaseAgenticAgent for the loop, timeout, tool_trace, and structured
logging. The only overrides are:
  - get_system_prompt(): generic accessibility expert, no persona backstory
  - get_tools(): fresh generic tool schemas (persona-specific interpretation
                 stripped) for all 18 tools
  - tool_dispatcher: all 18 tools registered

Same public interface (evaluate(html, persona)) so run_experiment.py can
treat all conditions interchangeably. The `persona` argument is used ONLY
to look up which 5 WCAG criteria to evaluate. The LLM never sees any
persona reference.
"""

import os
import sys
import tempfile

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from personas.base_agent import BaseAgenticAgent

# Import all tool modules used across personas
from tools1 import animation_detector_agent
from tools1 import autocomplete_validator_agent
from tools1 import custom_widget_keyboard_agent
from tools1 import focus_order_validator_agent
from tools1 import focus_visible_validator_agent
from tools1 import form_validator_agent
from tools1 import heading_structure_agent
from tools1 import keyboard_navigation_agent
from tools1 import multiple_ways_checker_agent
from tools1 import readability_analyzer_agent
from tools1 import target_size_validator_agent
from tools1 import text_formatting_agent
from tools1 import timing_checker_agent
from tools1.Contrast_Checker_Agent import ContrastCheckerAgent
from tools1.nvda_agent import run_full_analysis


DEFAULT_MODEL = "gpt-4o"


# Same criterion assignments used in condition_d_vanilla_llm.py — kept in
# sync so both vanilla conditions cover the SAME criterion set per persona.
PERSONA_CRITERIA = {
    "ade":     ["2.1.1", "2.2.1", "2.4.3", "2.4.7", "2.5.5"],
    "elias":   ["1.3.5", "1.4.3", "1.4.12", "2.2.2", "2.4.8"],
    "ian":     ["1.3.1", "2.2.2", "2.4.6", "3.1.4", "3.1.5"],
    "lakshmi": ["1.1.1", "1.3.1", "2.1.1", "2.4.1", "4.1.2"],
    "sophie":  ["2.2.1", "2.4.8", "3.1.4", "3.3.1", "3.3.2"],
    "stefan":  ["1.4.12", "2.2.2", "2.4.5", "2.4.6", "3.1.4"],
}

WCAG_TITLES = {
    "1.1.1":  "Non-text Content (Level A)",
    "1.3.1":  "Info and Relationships (Level A)",
    "1.3.5":  "Identify Input Purpose (Level AA)",
    "1.4.3":  "Contrast Minimum (Level AA)",
    "1.4.12": "Text Spacing (Level AA)",
    "2.1.1":  "Keyboard (Level A)",
    "2.2.1":  "Timing Adjustable (Level A)",
    "2.2.2":  "Pause, Stop, Hide (Level A)",
    "2.4.1":  "Bypass Blocks (Level A)",
    "2.4.3":  "Focus Order (Level A)",
    "2.4.5":  "Multiple Ways (Level AA)",
    "2.4.6":  "Headings and Labels (Level AA)",
    "2.4.7":  "Focus Visible (Level AA)",
    "2.4.8":  "Location (Level AAA)",
    "2.5.5":  "Target Size (Level AAA)",
    "3.1.4":  "Abbreviations (Level AAA)",
    "3.1.5":  "Reading Level (Level AAA)",
    "3.3.1":  "Error Identification (Level A)",
    "3.3.2":  "Labels or Instructions (Level A)",
    "4.1.2":  "Name, Role, Value (Level A)",
}


def build_vanilla_agent_system_prompt(criteria):
    """
    Generic accessibility-expert prompt for the agent condition. Same as
    Vanilla-LLM but includes tool usage guidance.
    """
    criteria_lines = "\n".join(
        f"  - WCAG {c} {WCAG_TITLES.get(c, '')}" for c in criteria
    )
    return f"""You are an accessibility expert evaluating a web page against a specific set of WCAG 2.1 success criteria.

Your task: examine the HTML and produce a single verdict for the page against these criteria:
{criteria_lines}

You have access to 18 specialized accessibility tools. Each tool inspects one aspect of the HTML (contrast, keyboard navigation, form structure, readability, etc.). Call the tools that are relevant to the criteria above.

Guidelines for tool use:
  1. Call each tool at most once per evaluation.
  2. Only call tools whose output is relevant to the target criteria.
  3. Prefer tools whose scope directly matches a criterion over tools that provide indirect evidence.
  4. If a tool returns "inapplicable" or "not applicable" for its criterion, do not treat that as a failure.
  5. If the HTML clearly does not contain the elements a criterion targets (e.g., no forms, no images, no interactive elements), you may return "inapplicable" without calling every tool.

After gathering tool evidence, decide whether the page:
  - "passed" — the page complies with the criteria
  - "failed" — the page violates one or more criteria
  - "inapplicable" — the criteria do not apply to this page

Return a single JSON object with these fields:
{{
  "label": "passed" | "failed" | "inapplicable",
  "severity": "critical" | "serious" | "moderate" | "minor" | "N/A",
  "issues": [
    {{
      "wcag": "<criterion number>",
      "description": "<short description of the issue>",
      "evidence": "<specific HTML fragment or tool finding>",
      "recommendation": "<how to fix>"
    }},
    ...
  ],
  "overall_assessment": "<one-paragraph summary of the verdict and reasoning>"
}}

The "label" field is the overall verdict for the target criterion (each snippet targets ONE criterion, though it may test other criteria too). Return ONLY the JSON object. No markdown fences. No preamble.
"""


# --------------------------------------------------------------------------- #
#  Generic tool schemas — persona-agnostic descriptions                        #
# --------------------------------------------------------------------------- #

# Every tool takes the same {html: string} argument shape.
_HTML_PARAMS = {
    "type": "object",
    "properties": {"html": {"type": "string"}},
    "required": ["html"],
}

# Persona-neutral descriptions. Structure: [WHAT] [COVERS WCAG] [RETURNS].
# Kept short so tool selection is driven by criterion match, not narrative.
GENERIC_TOOL_DESCRIPTIONS = {
    "check_keyboard_focusables": (
        "[WHAT] Enumerates all keyboard-focusable elements on the page. "
        "[COVERS] WCAG 2.1.1 Keyboard (evidence). "
        "[RETURNS] focusable_elements list, count, tool_name."
    ),
    "detect_keyboard_violations": (
        "[WHAT] Detects mouse-only interactives, hover-only behaviors, and "
        "ARIA widget issues. [COVERS] WCAG 2.1.1 Keyboard (violation detection). "
        "[RETURNS] wcag_211_status (PASS/FAIL/INAPPLICABLE), mouse_only_interactives, "
        "hover_only_behaviors, aria_widget_issues, total_issues."
    ),
    "check_timing_and_timeouts": (
        "[WHAT] Detects meta-refresh, setTimeout/setInterval, and time-limit "
        "controls. [COVERS] WCAG 2.2.1 Timing Adjustable. "
        "[RETURNS] wcag_221_status, meta_refresh_detected, settimeout_calls, "
        "extend_session_control_found."
    ),
    "validate_focus_order": (
        "[WHAT] Analyzes tab order versus visual reading order; detects positive "
        "tabindex. [COVERS] WCAG 2.4.3 Focus Order. "
        "[RETURNS] wcag_243_status, tab_sequence, positive_tabindex_elements, issues."
    ),
    "validate_focus_visible": (
        "[WHAT] Detects removed focus outlines without replacement. "
        "[COVERS] WCAG 2.4.7 Focus Visible. "
        "[RETURNS] wcag_247_status, elements_without_focus_indicator."
    ),
    "validate_target_size": (
        "[WHAT] Measures the bounding rectangle of interactive elements; "
        "compares against WCAG target-size thresholds. "
        "[COVERS] WCAG 2.5.5 Target Size (AAA, 44x44) and 2.5.8 (AA, 24x24). "
        "[RETURNS] wcag_255_status, elements_below_threshold, worst_measured_size."
    ),
    "validate_input_purpose": (
        "[WHAT] Checks form input autocomplete attributes against the WCAG "
        "list of 53 valid input purposes. [COVERS] WCAG 1.3.5 Identify Input Purpose. "
        "[RETURNS] wcag_135_status, fields_analyzed, fields_missing_autocomplete, "
        "fields_with_invalid_autocomplete."
    ),
    "check_contrast_aa": (
        "[WHAT] Computes WCAG contrast ratios for every text-bearing element; "
        "compares against 4.5:1 (normal) or 3:1 (large text). "
        "[COVERS] WCAG 1.4.3 Contrast Minimum. "
        "[RETURNS] wcag_143_status, elements_analyzed, elements_failing, worst_ratio."
    ),
    "check_text_spacing_reflow": (
        "[WHAT] Applies WCAG text-spacing overrides and detects layout breaks "
        "(clipping, overlap, disappearing controls). "
        "[COVERS] WCAG 1.4.12 Text Spacing. "
        "[RETURNS] wcag_1412_status, layout_broken, blocked_by_important."
    ),
    "detect_animations_and_motion": (
        "[WHAT] Detects CSS animations, autoplay video/audio, animated GIFs, "
        "marquee/blink; checks pause controls and prefers-reduced-motion respect. "
        "[COVERS] WCAG 2.2.2 Pause Stop Hide. "
        "[RETURNS] wcag_222_status, animations_detected, pause_control_present, "
        "reduced_motion_respected."
    ),
    "check_location_indicators": (
        "[WHAT] Detects breadcrumbs, aria-current='page', nav active-class, "
        "page title, and H1 heading. [COVERS] WCAG 2.4.8 Location. "
        "[RETURNS] wcag_248_status, signals_present, evidence."
    ),
    "check_navigation_methods": (
        "[WHAT] Detects site navigation, search, sitemap, breadcrumb, TOC. "
        "[COVERS] WCAG 2.4.5 Multiple Ways. "
        "[RETURNS] wcag_245_status, distinct_mechanisms_found, mechanisms."
    ),
    "analyze_heading_structure": (
        "[WHAT] Analyzes heading hierarchy, detects skipped levels, empty and "
        "generic headings. [COVERS] WCAG 1.3.1 Info and Relationships and 2.4.6 "
        "Headings and Labels. [RETURNS] headings, hierarchy_valid, hierarchy_issues, "
        "generic_headings."
    ),
    "analyze_readability": (
        "[WHAT] Computes readability formulas (Flesch-Kincaid, SMOG, etc.), "
        "detects abbreviations via three mechanisms (abbr element, first-use "
        "expansion, glossary link), checks supplemental content. "
        "[COVERS] WCAG 3.1.4 Abbreviations and 3.1.5 Reading Level. "
        "[RETURNS] readability metrics, wcag_314_status, wcag_315_status."
    ),
    "analyze_readability_and_abbreviations": (
        "[WHAT] Same tool as analyze_readability; alternate name registered for "
        "personas with a distinct focus on abbreviation mechanisms. "
        "[COVERS] WCAG 3.1.4 Abbreviations. "
        "[RETURNS] readability metrics, wcag_314_status, abbreviation mechanisms."
    ),
    "validate_form_errors_and_labels": (
        "[WHAT] Checks form labels, placeholder-as-label, required indicators, "
        "format hints, fieldset grouping; SUBMITS the form and captures error "
        "behavior (HTML5 validation, aria-live regions, visible error elements). "
        "[COVERS] WCAG 3.3.1 Error Identification and 3.3.2 Labels or Instructions. "
        "[RETURNS] wcag_331_status, wcag_332_status, submission_test, issues."
    ),
    "check_keyboard_navigation": (
        "[WHAT] Tabs through the page and tests Enter/Space activation on each "
        "focus stop; detects dead focus stops, keyboard traps, and modal Escape "
        "behavior. [COVERS] WCAG 2.1.1 Keyboard (interactive verification). "
        "[RETURNS] wcag_211_status, activation_test_results, dead_focus_stops, "
        "keyboard_traps, modal_test."
    ),
    "run_nvda_full_audit": (
        "[WHAT] Launches the NVDA screen reader and captures announcements for "
        "images (alt text), landmarks (skip links), and interactive elements "
        "(name/role/value). Requires Windows + NVDA + Tesseract. "
        "[COVERS] WCAG 1.1.1 Non-text Content, 2.4.1 Bypass Blocks, 4.1.2 Name Role Value. "
        "[RETURNS] wcag_111_status, wcag_241_status, wcag_412_status, per-element details."
    ),
}


def _tool_schema(name):
    """Build an OpenAI function-calling tool schema for a given tool name."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": GENERIC_TOOL_DESCRIPTIONS[name],
            "parameters": _HTML_PARAMS,
        },
    }


# --------------------------------------------------------------------------- #
#  NVDA adapter (mirrors lakshmi_agent's HTML->URI shim)                       #
# --------------------------------------------------------------------------- #

def _nvda_execute(html):
    """
    nvda_agent.run_full_analysis takes a URL. Adapt to the tool-dispatcher
    contract by writing HTML to a temp file and passing file:// URI.
    """
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(html)
        tmp_path = tmp.name
    try:
        uri = f"file://{tmp_path}"
        return run_full_analysis(uri)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# --------------------------------------------------------------------------- #
#  Vanilla-Agent inner class (one instance, no persona)                        #
# --------------------------------------------------------------------------- #

class _VanillaAgent(BaseAgenticAgent):
    """Persona-agnostic agent with all 18 tools registered."""

    def __init__(self, api_key):
        super().__init__(api_key, persona_name="Vanilla")

        # Instantiate every tool once
        self.keyboard_agent = keyboard_navigation_agent.KeyboardNavigationAgent()
        self.custom_widget_agent = custom_widget_keyboard_agent.CustomWidgetKeyboardAgent()
        self.timing_agent = timing_checker_agent.TimingCheckerAgent()
        self.focus_order_agent = focus_order_validator_agent.FocusOrderValidatorAgent()
        self.focus_visible_agent = focus_visible_validator_agent.FocusVisibleValidatorAgent()
        self.target_size_agent = target_size_validator_agent.TargetSizeValidatorAgent(level="AAA")
        self.autocomplete_agent = autocomplete_validator_agent.AutocompleteValidatorAgent()
        self.contrast_agent = ContrastCheckerAgent()
        self.text_formatting_agent = text_formatting_agent.TextFormattingAgent()
        self.animation_agent = animation_detector_agent.AnimationDetectorAgent()
        self.multiple_ways_agent = multiple_ways_checker_agent.MultipleWaysCheckerAgent()
        self.heading_agent = heading_structure_agent.HeadingStructureAgent()
        self.readability_agent = readability_analyzer_agent.ReadabilityAnalyzerAgent()
        self.form_agent = form_validator_agent.FormValidatorAgent()

        # Register all 18 tool names
        self.tool_dispatcher = {
            "check_keyboard_focusables": self.keyboard_agent.execute,
            "detect_keyboard_violations": self.custom_widget_agent.execute,
            "check_timing_and_timeouts": self.timing_agent.execute,
            "validate_focus_order": self.focus_order_agent.execute,
            "validate_focus_visible": self.focus_visible_agent.execute,
            "validate_target_size": self.target_size_agent.execute,
            "validate_input_purpose": self.autocomplete_agent.execute,
            "check_contrast_aa": self.contrast_agent.execute,
            "check_text_spacing_reflow": self.text_formatting_agent.execute,
            "detect_animations_and_motion": self.animation_agent.execute,
            "check_location_indicators": self.multiple_ways_agent.execute,
            "check_navigation_methods": self.multiple_ways_agent.execute,
            "analyze_heading_structure": self.heading_agent.execute,
            "analyze_readability": self.readability_agent.execute,
            "analyze_readability_and_abbreviations": self.readability_agent.execute,
            "validate_form_errors_and_labels": self.form_agent.execute,
            "check_keyboard_navigation": self.keyboard_agent.execute,
            "run_nvda_full_audit": _nvda_execute,
        }

        # Per-evaluation state; get_system_prompt() reads this
        self._current_criteria = []

    def set_criteria(self, criteria):
        """Called by VanillaAgentCondition.evaluate() before running the loop."""
        self._current_criteria = criteria

    def get_system_prompt(self):
        return build_vanilla_agent_system_prompt(self._current_criteria)

    def get_tools(self):
        return [_tool_schema(name) for name in self.tool_dispatcher.keys()]


# --------------------------------------------------------------------------- #
#  Public condition class                                                      #
# --------------------------------------------------------------------------- #

class VanillaAgentCondition:
    """Generic accessibility-expert prompt + all 18 tools. No persona."""

    def __init__(self, api_key, model=None):
        self.model = model or os.environ.get("A11Y_MODEL") or DEFAULT_MODEL
        # Must be set BEFORE the agent is constructed, since BaseAgenticAgent
        # reads it in __init__ to pick its provider adapter.
        os.environ["A11Y_MODEL"] = self.model

        # One vanilla agent, reused for every persona. Persona affects only
        # which criteria are passed via set_criteria().
        self.agent = _VanillaAgent(api_key)

        if self.agent.model != self.model:
            raise RuntimeError(
                f"Model mismatch: agent resolved {self.agent.model!r}, "
                f"expected {self.model!r}. Check A11Y_MODEL handling."
            )

    def evaluate(self, html, persona):
        """
        Evaluate the HTML using the 5 WCAG criteria that this persona would
        have targeted. The agent has access to all 18 tools; the LLM decides
        which to call. No persona backstory reaches the LLM.
        """
        criteria = PERSONA_CRITERIA.get(persona, [])
        if not criteria:
            return {
                "evaluation": {
                    "label": "error",
                    "severity": "N/A",
                    "issues": [],
                    "overall_assessment": (
                        f"Unknown persona '{persona}'. Known: "
                        f"{sorted(PERSONA_CRITERIA)}"
                    ),
                },
                "metadata": {
                    "tools_called": [],
                    "iteration_count": 0,
                    "total_time_seconds": 0.0,
                    "persona": persona,
                    "model": self.model,
                    "condition_variant": "vanilla_agent",
                    "error": f"Unknown persona: {persona}",
                },
            }

        # Pass criteria into the agent so get_system_prompt() sees them
        self.agent.set_criteria(criteria)

        # BaseAgenticAgent.evaluate() returns {evaluation, metadata}
        result = self.agent.evaluate(html)

        # Add condition-level metadata
        md = result.setdefault("metadata", {})
        md["persona"] = persona
        md["criteria_evaluated"] = criteria
        md["condition_variant"] = "vanilla_agent"
        md.setdefault("model", self.model)

        return result


if __name__ == "__main__":
    import json
    from dotenv import load_dotenv
    from llm_client1 import key_env_var

    load_dotenv()
    model = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL
    api_key = os.environ.get(key_env_var(model))
    if not api_key or api_key == "smoke-test":
        print(f"Set {key_env_var(model)} to run this test.")
    else:
        cond = VanillaAgentCondition(api_key, model=model)
        result = cond.evaluate(
            "<html><body><img src='x.jpg'><button></button></body></html>",
            persona="lakshmi",
        )
        print(json.dumps(result, indent=2, default=str))
