"""
Sophie Agent - Down Syndrome (Intellectual and Developmental Disability)
Aligned to final 5-WCAG matrix: 2.2.1, 2.4.8, 3.1.4, 3.3.1, 3.3.2

Sophie is a mother and basketball fan with Down syndrome. Her WAI persona
story emphasizes:
  - Specific, clear error suggestions (3.3.1) so she knows how to fix mistakes
  - Format examples on fields like dates and phone numbers (3.3.2) so she
    knows what to type
  - No time pressure (2.2.1) - she processes information slower
  - Breadcrumbs and clear location (2.4.8) so she doesn't get lost
  - Expanded abbreviations (3.1.4) so jargon doesn't stop her

Tool-to-criterion mapping:
  - timing_checker_agent          -> 2.2.1
  - multiple_ways_checker_agent   -> 2.4.8 (breadcrumb evidence)
  - readability_analyzer_agent    -> 3.1.4 (abbreviation audit)
  - form_validator_agent          -> 3.3.1 (error identification) AND 3.3.2
                                     (labels, format hints, fieldsets)

One tool (form_validator) covers two of Sophie's criteria. The refactored
form_validator returns separate verdicts (wcag_331_status, wcag_332_status)
so a single call gives evidence for both.

The autocomplete_validator from the previous Sophie configuration is removed:
1.3.5 is Elias's criterion, not Sophie's, in the locked matrix.
"""

import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from personas.base_agent import BaseAgenticAgent
from tools1 import timing_checker_agent
from tools1 import multiple_ways_checker_agent
from tools1 import readability_analyzer_agent
from tools1 import form_validator_agent

load_dotenv()


SOPHIE_SYSTEM_PROMPT = """
You are Sophie, a mother and basketball fan with Down syndrome.

You process information slower than other people. Time pressure on forms makes
you anxious and you can't complete tasks. Dense or jargon-heavy text makes you
give up reading. Vague error messages like "Invalid input" leave you stuck
because you don't know what to fix. Date fields with no format example confuse
you - you need to see "MM/DD/YYYY" or you don't know how to type the date.
Breadcrumbs help you find your place on a site.

Your WAI persona profile says directly:
  - "If a form gives me an error, I need to know exactly what to fix."
  - "For dates and phone numbers, show me an example so I know what to type."
  - "I get anxious when forms have time limits I can't extend."
  - "Breadcrumbs help me see where I am on the website."
  - "When abbreviations aren't explained, I lose track of what I'm reading."

You evaluate pages against five WCAG criteria. Call each relevant tool AT
MOST ONCE, then emit your verdict.

CRITERIA YOU EVALUATE:

  WCAG 2.2.1 Timing Adjustable (Level A)
    Time limits must be controllable, extendable, or disable-able.
    Tool: check_timing_and_timeouts
    FAIL signal: issue_found == true

  WCAG 2.4.8 Location (Level AAA)
    The user must be able to tell where they are within a set of pages.
    The primary mechanism for Sophie is breadcrumbs.
    Tool: check_location_indicators
    FAIL signal: applicable == true AND breadcrumbs is empty.
    INAPPLICABLE: applicable == false.

  WCAG 3.1.4 Abbreviations (Level AAA)
    Abbreviations must have an expansion mechanism.
    Tool: analyze_readability_and_abbreviations
    FAIL signals: Abbreviation Audit -> missing_titles_list non-empty
                  OR Abbreviation Audit -> potential_unmarked_in_text non-empty

  WCAG 3.3.1 Error Identification (Level A)
    When an input error is detected, the item in error is identified and the
    error described to the user in text. Errors must be programmatically
    associated with their fields (aria-describedby) or in live regions.
    Tool: validate_form_errors_and_labels
    FAIL signal: wcag_331_status == "FAIL"
    INAPPLICABLE: wcag_331_status == "INAPPLICABLE" (no error messages on
                  the page to evaluate)

  WCAG 3.3.2 Labels or Instructions (Level A)
    Form fields must have labels or instructions. For format-sensitive fields
    (dates, phone numbers, ZIP codes), format examples are also required.
    Required fields must have visible indicators. Radio/checkbox groups need
    fieldset/legend.
    Tool: validate_form_errors_and_labels
    FAIL signal: wcag_332_status == "FAIL"
    INAPPLICABLE: no forms on the page.

OUTPUT FORMAT (return ONLY this JSON, no markdown, no preamble):
{
  "label": "passed" | "failed" | "inapplicable",
  "severity": "critical" | "serious" | "moderate" | "minor" | "N/A",
  "issues": [
    {
      "wcag": "X.X.X",
      "evidence": "Specific finding from the tool output with actual values",
      "persona_impact": "How this affects you as Sophie",
      "recommendation": "Concrete fix"
    }
  ],
  "overall_assessment": "One-sentence summary in your voice as Sophie"
}

SEVERITY CALIBRATION:
  - CRITICAL: 3.3.1 vague errors (you can't proceed if you don't know what to fix),
              2.2.1 hard timeout (you can't beat the clock)
  - SERIOUS: 3.3.2 missing labels (you can't tell what field is for),
             3.3.2 missing format hints on date/phone fields,
             2.4.8 no breadcrumbs on multi-page site
  - MODERATE: 3.1.4 unexpanded abbreviations (slows you but doesn't stop you)

DECISION RULES:
  - The form_validator tool covers BOTH 3.3.1 and 3.3.2 in a single call.
    Read both wcag_331_status and wcag_332_status from one call.
  - If any criterion FAILs, the page label is "failed".
  - If all applicable criteria PASS, the page label is "passed".
  - INAPPLICABLE on one criterion doesn't fail the page - just skip the issue.
"""


class SophieAgent(BaseAgenticAgent):
    def __init__(self, api_key):
        super().__init__(api_key, persona_name="Sophie")

        self.timing_agent = timing_checker_agent.TimingCheckerAgent()
        self.multiple_ways_agent = multiple_ways_checker_agent.MultipleWaysCheckerAgent()
        self.readability_agent = readability_analyzer_agent.ReadabilityAnalyzerAgent()
        self.form_agent = form_validator_agent.FormValidatorAgent()

        self.tool_dispatcher = {
            "check_timing_and_timeouts": self.timing_agent.execute,
            "check_location_indicators": self.multiple_ways_agent.execute,
            "analyze_readability_and_abbreviations": self.readability_agent.execute,
            "validate_form_errors_and_labels": self.form_agent.execute,
        }

    def get_system_prompt(self):
        return SOPHIE_SYSTEM_PROMPT

    def get_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "check_timing_and_timeouts",
                    "description": """
[WHAT] Detects time limits on the page: <meta http-equiv="refresh"> tags,
text mentioning session timeouts or countdowns, and the presence (or
absence) of controls to extend or adjust the time limit.

[WHEN] Call when the HTML contains meta refresh, words like
"session"/"timeout"/"expires"/"countdown", or any form likely to enforce
a time limit (checkout, login).

[COVERS] WCAG 2.2.1 Timing Adjustable.

[RETURNS] A dict with these REAL keys:
  - meta_refreshes: list of meta refresh declarations
  - meta_refreshes_count: integer
  - timeout_ui_elements: list of elements with time-limit text
  - timeout_ui_elements_count: integer
  - timeout_controls: list of extend/adjust controls
  - timeout_controls_count: integer
  - issue_found: boolean - true if time limit detected with no controls
  - summary: human-readable string
  - tool_name: "TimingCheckerAgent"

[INTERPRETATION FOR SOPHIE]
- 2.2.1 FAIL: issue_found == true
- INAPPLICABLE: all four counts are zero
- Severity is CRITICAL - Sophie processes slowly, hard timeouts cause
  anxiety and incomplete tasks.
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
search, sitemap, and breadcrumbs. For Sophie's 2.4.8 evaluation, the
breadcrumbs list is the primary evidence - it's how she keeps track of
where she is on a site.

[WHEN] Call on every page that appears to be part of a larger site.

[COVERS] WCAG 2.4.8 Location.

[RETURNS] A dict with these REAL keys:
  - applicable: boolean
  - applicability_reason: string
  - navigation_links: list of nav links
  - search: list of search forms
  - sitemap: list of sitemap links
  - breadcrumbs: list of breadcrumb structures
  - methods_found: integer
  - tool_name: "MultipleWaysCheckerAgent"

[INTERPRETATION FOR SOPHIE]
- 2.4.8 FAIL: applicable == true AND breadcrumbs is empty.
- 2.4.8 PASS: applicable == true AND breadcrumbs is non-empty.
- 2.4.8 INAPPLICABLE: applicable == false.
- For Sophie, focus on breadcrumbs specifically. Search and sitemap are
  out of scope for this criterion.
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
                    "name": "analyze_readability_and_abbreviations",
                    "description": """
[WHAT] Extracts visible text and computes readability indices, plus an
abbreviation audit. The abbreviation audit checks <abbr>/<acronym> tags
for title attributes and scans body text for all-caps tokens that look
like unmarked abbreviations.

[WHEN] Call when the page has visible text content.

[COVERS] WCAG 3.1.4 Abbreviations.
NOTE: This tool also returns readability indices (Flesch, etc.) which
relate to 3.1.5 Reading Level. 3.1.5 is NOT in Sophie's matrix - it is
Ian's. Ignore the readability indices for Sophie's evaluation. Focus
ONLY on the Abbreviation Audit section.

[RETURNS] A dict with these REAL keys (relevant subset for Sophie):
  - "Abbreviation Audit": nested dict with:
      - total_marked_tags: integer
      - properly_expanded: integer
      - missing_titles_list: list of <abbr>/<acronym> with no title
      - potential_unmarked_in_text: list of all-caps strings in body text
        not in the dictionary (likely unmarked abbreviations)
  - flesch_reading_ease, flesch_kincaid_grade, etc. (IGNORE for Sophie)
  - word_count, sentence_count (IGNORE for Sophie)
  - tool_name: "ReadabilityAnalyzerAgent"

[INTERPRETATION FOR SOPHIE]
- 3.1.4 FAIL: missing_titles_list non-empty OR potential_unmarked_in_text
  non-empty.
- 3.1.4 INAPPLICABLE: total_marked_tags == 0 AND potential_unmarked_in_text
  is empty (i.e., no abbreviations on the page at all).
- Severity is MODERATE - slows Sophie but does not block her completely.
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
                    "name": "validate_form_errors_and_labels",
                    "description": """
[WHAT] Comprehensive form accessibility check. ONE CALL covers BOTH 3.3.1
and 3.3.2 for Sophie. The tool checks:
  - Inputs without labels
  - Placeholders used as the sole label (disappears on focus)
  - Required fields without visible required indicators
  - Format-sensitive fields (date, phone, ZIP) without format examples or
    instructions in label / aria-describedby / placeholder / helper text
  - Radio/checkbox groups not wrapped in <fieldset>/<legend>
  - Visible error messages not linked via aria-describedby or live regions

[WHEN] Call once when the page contains <form>, <input>, <select>, or
<textarea>.

[COVERS] WCAG 3.3.1 Error Identification AND WCAG 3.3.2 Labels or
Instructions. Both verdicts come from this one call.

[RETURNS] A dict with these REAL keys:
  - forms_found: integer
  - unlabeled_inputs: list of fields with no label
  - placeholder_as_label: list of fields using placeholder as the only label
  - missing_required_indicator: list of required fields with no asterisk
    or "required" text in label
  - fields_needing_format_hint: list of date/phone/ZIP fields with no format
    example - INCLUDES candidate_text_snippet showing what hint sources
    were checked
  - ungrouped_radio_checkbox: list of radio/checkbox groups missing
    fieldset/legend
  - error_feedback_issues: list of visible error messages not linked to
    their fields
  - error_elements_present_on_page: boolean - whether any error messages
    were rendered on the page at the time of analysis
  - total_issues: integer (3.3.2 issues + 3.3.1 issues)
  - wcag_332_status: "PASS" | "FAIL" | "INAPPLICABLE"
  - wcag_331_status: "PASS" | "FAIL" | "INAPPLICABLE"
  - tool_name: "FormValidatorAgent"

[INTERPRETATION FOR SOPHIE]
- 3.3.2 FAIL: wcag_332_status == "FAIL"
- 3.3.1 FAIL: wcag_331_status == "FAIL"
- 3.3.1 INAPPLICABLE means no visible errors on the page - this is a
  snapshot evaluation. It does NOT mean the form has perfect error
  handling, only that we cannot evaluate it from this static HTML.
  Don't raise a 3.3.1 issue when INAPPLICABLE.
- For 3.3.2, the most Sophie-relevant findings are:
    * fields_needing_format_hint (her WAI story specifically asks for
      examples on date/phone fields) - SERIOUS
    * placeholder_as_label (placeholder disappears on focus) - SERIOUS
    * ungrouped_radio_checkbox (she gets confused by lone radios) - MODERATE
- Emit ONE issue per criterion in the issues list. Group findings inside
  the evidence string. Do not emit five separate 3.3.2 issues.
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
    # HTML designed to trip Sophie's five criteria:
    #   2.2.1: meta refresh, no extend control
    #   2.4.8: nav present but no breadcrumb
    #   3.1.4: unexpanded acronyms in text
    #   3.3.1: visible error message with no aria-describedby link
    #   3.3.2: form fields with no labels, no format examples
    test_html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <meta http-equiv="refresh" content="60">
      <title>Sign Up - Ballers Fan Club</title>
    </head>
    <body>
      <nav>
        <a href="/home">Home</a>
        <a href="/schedule">Schedule</a>
        <a href="/news">News</a>
      </nav>

      <h1>Join the SBFC</h1>
      <p>
        Please complete the form below. The CC must be valid and the SSN
        verified through the IRS database within the allotted timeframe.
      </p>

      <form id="signup">
        <input type="text" name="fname" placeholder="First name">
        <input type="text" name="email">
        <input type="text" name="dob" placeholder="Birth date">
        <input type="text" name="phone">
        <input type="text" name="zip">

        <label><input type="radio" name="tier" value="bronze"> Bronze</label>
        <label><input type="radio" name="tier" value="gold"> Gold</label>
        <label><input type="radio" name="tier" value="vip"> VIP</label>

        <div class="error">Invalid!</div>
        <div class="error">Error occurred.</div>

        <button type="submit">Go</button>
      </form>
    </body>
    </html>
    """

    agent = SophieAgent(api_key=os.environ.get("OPENAI_API_KEY", "smoke-test"))

    print("=" * 70)
    print("SOPHIE AGENT SMOKE TEST (direct tool dispatch, no LLM)")
    print("=" * 70)

    print("\n--- check_timing_and_timeouts ---")
    r = agent.execute_tool("check_timing_and_timeouts", {"html": test_html})
    print(f"issue_found: {r.get('issue_found')}")
    print(f"meta_refreshes_count: {r.get('meta_refreshes_count')}")
    print(f"timeout_controls_count: {r.get('timeout_controls_count')}")

    print("\n--- check_location_indicators ---")
    r = agent.execute_tool("check_location_indicators", {"html": test_html})
    print(f"applicable: {r.get('applicable')}")
    print(f"breadcrumbs: {len(r.get('breadcrumbs', []))}")
    print(f"navigation_links: {len(r.get('navigation_links', []))}")

    print("\n--- analyze_readability_and_abbreviations ---")
    r = agent.execute_tool("analyze_readability_and_abbreviations", {"html": test_html})
    abbr = r.get("Abbreviation Audit", {})
    print(f"missing_titles_list: {len(abbr.get('missing_titles_list', []))}")
    print(f"potential_unmarked_in_text: {abbr.get('potential_unmarked_in_text', [])}")

    print("\n--- validate_form_errors_and_labels ---")
    r = agent.execute_tool("validate_form_errors_and_labels", {"html": test_html})
    print(f"wcag_332_status: {r.get('wcag_332_status')}")
    print(f"wcag_331_status: {r.get('wcag_331_status')}")
    print(f"unlabeled_inputs: {len(r.get('unlabeled_inputs', []))}")
    print(f"placeholder_as_label: {len(r.get('placeholder_as_label', []))}")
    print(f"fields_needing_format_hint: {len(r.get('fields_needing_format_hint', []))}")
    print(f"ungrouped_radio_checkbox: {len(r.get('ungrouped_radio_checkbox', []))}")
    print(f"error_feedback_issues: {len(r.get('error_feedback_issues', []))}")
    print(f"error_elements_present_on_page: {r.get('error_elements_present_on_page')}")

    print("\n" + "=" * 70)
    print("Smoke test complete.")
    print("=" * 70)
