"""
How the agent conditions (C, E) see their tools in the barrier task.

Three arms, chosen with run_barrier_experiment.py --tool-framing:

  original      The tool names, descriptions and outputs used in the WCAG
                run, unchanged. Descriptions name WCAG criteria ("[COVERS]
                WCAG 1.4.3") and persona descriptions include verdict rules
                ("If FAIL, emit a 1.1.1 issue"). Outputs carry WCAG verdicts
                (wcag_143_status: "PASS").

  neutral       Neutral names and descriptions (NEUTRAL_TOOLS below): what
                the tool measures and what it returns, no WCAG criteria, no
                pass/fail rules. C and E get the SAME description for the
                same tool. Outputs are unchanged, so WCAG verdicts are still
                in them.

  measurements  Neutral names and descriptions, and outputs passed through
                strip_verdicts(): WCAG verdict/status fields and criterion
                references are removed and WCAG-numbered keys are renamed,
                leaving the measurements (ratios, sizes, element lists,
                counts) for the model to interpret for the person.

Comparing the three arms measures how much the WCAG framing carried by the
tools pulls the agent's judgment toward conformance.

The tools themselves (tools1/) and the agent classes (personas1/,
conditions/) are not modified; the arms only change what the model is shown.
"""

import re

FRAMINGS = ("original", "neutral", "measurements")

HTML_PARAMS = {
    "type": "object",
    "properties": {
        "html": {
            "type": "string",
            "description": "The full HTML source of the page being evaluated.",
        },
    },
    "required": ["html"],
}

# original tool name -> (neutral name, neutral description)
# Descriptions say what is measured and what comes back, nothing about
# which standard it relates to or what counts as passing.
NEUTRAL_TOOLS = {
    "check_keyboard_focusables": (
        "list_keyboard_focus_stops",
        "Tabs through the page in a headless browser and lists every element that "
        "receives keyboard focus, then presses Enter/Space on each one. Returns the "
        "focus stops found, whether each responded to activation, focus stops that "
        "do nothing, keyboard traps, and clickable elements that cannot be reached "
        "by keyboard.",
    ),
    "check_keyboard_navigation": (
        "walk_keyboard_navigation",
        "Tabs through the page in a headless browser and presses Enter/Space on each "
        "focus stop. Returns the focus stops found, whether each responded to "
        "activation, focus stops that do nothing, keyboard traps, clickable elements "
        "that cannot be reached by keyboard, and whether open dialogs close with Escape.",
    ),
    "detect_keyboard_violations": (
        "find_mouse_only_controls",
        "Inspects the markup for controls that only respond to the mouse: elements with "
        "click or hover handlers but no keyboard focus, hover-only menus, and custom "
        "widgets (ARIA roles) that are not focusable. Returns each such element with "
        "an HTML snippet.",
    ),
    "check_timing_and_timeouts": (
        "find_time_limits",
        "Looks for time limits on the page: meta refresh/redirects, session-timeout "
        "messages, countdowns, and any controls to extend or turn off a time limit. "
        "Returns what was found.",
    ),
    "validate_focus_order": (
        "compare_focus_order",
        "Records the order in which elements receive keyboard focus and compares it "
        "with their visual reading order. Returns the focus sequence, positive "
        "tabindex values, and places where focus jumps out of reading order.",
    ),
    "validate_focus_visible": (
        "test_focus_visibility",
        "Focuses each focusable element in a headless browser and compares its "
        "appearance with and without focus. Returns elements that show no visible "
        "change when focused, elements whose focus is shown only by a color change, "
        "and elements with weak focus indicators.",
    ),
    "validate_target_size": (
        "measure_target_sizes",
        "Measures the on-screen width and height in CSS pixels of every clickable "
        "element and the spacing around it. Returns the measurements and lists the "
        "smallest targets.",
    ),
    "validate_input_purpose": (
        "check_autocomplete_attributes",
        "Inspects form fields that ask for personal information (name, email, address, "
        "phone, ...) and reports which have an autocomplete attribute the browser can "
        "use to fill them in, which have none, which have an unrecognized value, and "
        "which turn autocomplete off.",
    ),
    "check_contrast_aa": (
        "measure_text_contrast",
        "Computes the foreground/background color contrast ratio of each text element "
        "as rendered. Returns, per element, the text, the ratio, font size and weight, "
        "plus elements whose colors could not be determined.",
    ),
    "check_text_spacing_reflow": (
        "test_text_spacing",
        "Increases line height, letter spacing, word spacing and paragraph spacing "
        "(as a user stylesheet would) and re-renders the page. Returns whether any "
        "text was clipped, overlapped or hidden afterwards, with details.",
    ),
    "detect_animations_and_motion": (
        "find_moving_content",
        "Detects content that moves, blinks, scrolls or updates by itself: CSS "
        "animations and transitions, autoplay audio/video, animated GIFs, marquees, "
        "and script-driven updates. Returns what was found, whether it stops under a "
        "reduced-motion preference, and any pause/stop controls.",
    ),
    "check_location_indicators": (
        "find_location_indicators",
        "Looks for signs of where the user is within the site: breadcrumbs, the "
        "current page marked in navigation (aria-current or an active class), a "
        "descriptive page title, and a main heading. Also lists the ways offered to "
        "find other pages (navigation menu, search, sitemap, table of contents). "
        "Returns which are present.",
    ),
    "check_navigation_methods": (
        "find_navigation_methods",
        "Lists the ways the page offers to find other pages (navigation menu, search, "
        "sitemap, breadcrumb, table of contents) and the location indicators present "
        "(breadcrumb, current page marked in navigation, page title, main heading). "
        "Returns which are present.",
    ),
    "analyze_heading_structure": (
        "outline_headings",
        "Extracts every heading with its level and text. Returns the heading outline, "
        "skipped levels, empty or generic heading text, and the number of words "
        "between headings.",
    ),
    "analyze_readability": (
        "analyze_text_readability",
        "Analyzes the page text: word and sentence counts, sentence length, readability "
        "formulas (e.g. Flesch reading ease, grade level), uncommon words, and "
        "abbreviations or acronyms with and without an expansion on the page.",
    ),
    "analyze_readability_and_abbreviations": (
        "analyze_text_and_abbreviations",
        "Analyzes the page text: word and sentence counts, sentence length, readability "
        "formulas, uncommon words, and abbreviations or acronyms with and without an "
        "expansion on the page.",
    ),
    "validate_form_errors_and_labels": (
        "inspect_forms",
        "Inspects each form: whether fields have visible labels or instructions, "
        "required-field and format hints, then submits the form empty in a headless "
        "browser and captures the error messages shown and how they are connected to "
        "the fields.",
    ),
    "run_nvda_full_audit": (
        "run_screen_reader_audit",
        "Opens the page with the NVDA screen reader and records what it announces for "
        "images, landmarks, headings and interactive elements, alongside a markup "
        "inspection of alt text, landmark regions, skip links, and the names and roles "
        "of controls.",
    ),
}

NEUTRAL_TO_ORIGINAL = {neutral: orig for orig, (neutral, _) in NEUTRAL_TOOLS.items()}


def neutral_schemas(original_names):
    """Function schemas for the given original tool names, in neutral form."""
    schemas = []
    for name in original_names:
        neutral, desc = NEUTRAL_TOOLS[name]
        schemas.append({
            "type": "function",
            "function": {"name": neutral, "description": desc, "parameters": HTML_PARAMS},
        })
    return schemas


# --------------------------------------------------------------------------- #
#  Output filter for the "measurements" arm                                     #
# --------------------------------------------------------------------------- #

# WCAG-numbered containers in tool outputs -> plain names.
RENAME_KEYS = {
    "wcag_1_1_1": "images_and_alt_text",
    "wcag_1_4_5": "images_of_text",
    "wcag_2_4_1": "repeated_blocks_and_landmarks",
    "wcag_4_1_2": "control_names_and_roles",
    "wcag_245": "navigation_methods",
    "wcag_248": "location_indicators",
    "wcag_314": "abbreviations",
    "wcag_315": "reading_level",
    "wcag_331_evidence": "error_message_evidence",
    "wcag_332_issues_count": "label_or_instruction_issue_count",
    "violations": "flagged_elements",
    "violation_count": "flagged_count",
    "outline_none_violations": "outline_removed_elements",
}

# Keys removed wherever they appear: verdicts, criterion ids, pass counts,
# the standard's thresholds, and judgments the tool made on the model's behalf.
DROP_KEY = re.compile(
    r"^(wcag(_\w+)?_status|wcag_status|status|verdict|wcag|wcag_sc|wcag_criterion|"
    r"passing_count|threshold\w*|persona|issue_found|wcag_\d+)$",
    re.IGNORECASE,
)

# Conformance levels ("A", "AA", "AAA") are dropped from "level" keys only;
# a heading's numeric level is a measurement and is kept.
CONFORMANCE_LEVELS = {"A", "AA", "AAA"}

VERDICT_VALUES = {"pass", "passed", "fail", "failed", "inapplicable", "n/a", "na"}

# Tool-authored prose. Sentences in these that cite a WCAG criterion are
# removed. Text copied from the page (heading text, titles, snippets) is
# never edited, even if the page itself mentions WCAG.
PROSE_KEYS = {"reason", "details", "evidence", "summary", "note", "message",
              "applicability_reason", "description", "issues", "explanation"}

WCAG_REF = re.compile(r"\b(WCAG|SC)\s*\d+(\.\d+)+", re.IGNORECASE)


def _clean_prose(s):
    parts = re.split(r"(?<=[.;])\s+", s)
    return " ".join(p for p in parts if not WCAG_REF.search(p)).strip()


def strip_verdicts(obj, key=None):
    """Recursively remove WCAG verdicts and criterion references from a tool output."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            new_key = RENAME_KEYS.get(k, k)
            if new_key == k and DROP_KEY.match(k):
                continue
            if k == "level" and isinstance(v, str) and v.upper() in CONFORMANCE_LEVELS:
                continue
            if k == "raw" and isinstance(v, dict):
                # The NVDA audit nests its measurements under "raw"; hoist them.
                for rk, rv in strip_verdicts(v, k).items():
                    out.setdefault(rk, rv)
                continue
            cleaned = strip_verdicts(v, new_key)
            if cleaned is None or cleaned == "":
                continue
            out[new_key] = cleaned
        return out
    if isinstance(obj, list):
        return [x for x in (strip_verdicts(i, key) for i in obj) if x is not None and x != ""]
    if isinstance(obj, str):
        if key in PROSE_KEYS:
            if obj.strip().lower() in VERDICT_VALUES:
                return None
            return _clean_prose(obj)
        return obj
    return obj


# --------------------------------------------------------------------------- #
#  Applying a framing to an agent instance                                      #
# --------------------------------------------------------------------------- #

def apply(agent, framing):
    """
    Re-point an agent's tool interface for the chosen framing.

    Must be called after the agent's execute_tool has been wrapped to inject
    html (conditions._retarget does that). Works for persona agents and for
    _VanillaAgent, which both expose tool_dispatcher and execute_tool.
    """
    if framing not in FRAMINGS:
        raise ValueError(f"tool framing must be one of {FRAMINGS}, got {framing!r}")
    if framing == "original":
        return agent

    names = list(agent.tool_dispatcher)
    schemas = neutral_schemas(names)
    agent.get_tools = lambda: schemas

    inner = agent.execute_tool

    def execute_tool(tool_name, arguments):
        result = inner(NEUTRAL_TO_ORIGINAL.get(tool_name, tool_name), arguments)
        if framing == "measurements" and isinstance(result, dict) and "error" not in result:
            result = strip_verdicts(result)
        return result

    agent.execute_tool = execute_tool
    return agent
