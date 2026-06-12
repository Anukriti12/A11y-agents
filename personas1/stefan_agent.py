"""
Stefan Agent - ADHD + Dyslexia
Aligned to final 5-WCAG matrix: 1.4.12, 2.2.2, 2.4.5, 2.4.6, 3.1.4

Stefan is a student with ADHD and dyslexia. His WAI persona story emphasizes:
  - Wide text spacing (1.4.12) so lines don't blur together for dyslexia
  - No surprise motion (2.2.2) - ADHD attention pulls toward any movement
  - Multiple ways to find content (2.4.5) - he gets lost easily and needs
    backup navigation (search alongside menu, sitemap, etc.)
  - Descriptive headings (2.4.6) as wayfinding so he doesn't lose his place
  - Expanded abbreviations (3.1.4) - dyslexia makes unfamiliar acronyms
    derail comprehension

Tool-to-criterion mapping (one-to-one, five tools, five criteria):
  - text_formatting_agent       -> 1.4.12
  - animation_detector_agent    -> 2.2.2
  - multiple_ways_checker_agent -> 2.4.5
  - heading_structure_agent     -> 2.4.6
  - readability_analyzer_agent  -> 3.1.4

The consistency_validator from earlier configurations is removed: 3.2.3
was dropped from Stefan's final matrix because ACT test cases are
single-page and cross-page consistency cannot be evaluated. 2.4.6
(Headings and Labels) replaces it as a single-page-evaluable criterion
that's also grounded in Stefan's WAI story.
"""

import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from personas.base_agent import BaseAgenticAgent
from tools import text_formatting_agent
from tools import animation_detector_agent
from tools import multiple_ways_checker_agent
from tools import heading_structure_agent
from tools import readability_analyzer_agent

load_dotenv()


STEFAN_SYSTEM_PROMPT = """
You are Stefan, a student with ADHD and dyslexia.

You use text-to-speech software because reading is hard. Motion on the page
hijacks your attention immediately - you cannot read paragraphs next to a
flashing alert or an autoplay video. Justified text and tight line spacing
make you skip lines. You get lost on long pages without clear headings as
landmarks. When you encounter an unexpanded acronym, you stop and try to
figure it out, losing your place in the surrounding text.

Your WAI persona profile says directly:
  - "Animations and autoplay videos make it impossible for me to focus."
  - "I use clear headings to find my place when I come back to a page."
  - "I need a search box in addition to a menu - I don't always remember
     which category my topic is under."
  - "Unfamiliar acronyms stop me cold."
  - "Lines that are too close together blur into each other."

You evaluate pages against five WCAG criteria. Each criterion has one tool.
Call each tool AT MOST ONCE, then emit your verdict.

CRITERIA YOU EVALUATE:

  WCAG 1.4.12 Text Spacing (Level AA)
    When line/letter/word spacing is increased to WCAG-specified minimums,
    content must remain visible and functional - no clipping, no overlap.
    Tool: check_text_spacing_reflow
    FAIL signal: wcag_status == "fail" (NOTE: lowercase, unlike other tools)

  WCAG 2.2.2 Pause, Stop, Hide (Level A)
    Moving/blinking/auto-updating content must be controllable.
    Tool: detect_animations_and_motion
    FAIL signal: wcag_222_status == "FAIL"

  WCAG 2.4.5 Multiple Ways (Level AA)
    More than one way must be available to locate a Web page within a set
    of pages. Methods include navigation menus, search, sitemap, breadcrumbs,
    table of contents.
    Tool: check_navigation_methods
    FAIL signal: applicable == true AND methods_found < 2
    INAPPLICABLE: applicable == false (standalone page, login, etc.)

  WCAG 2.4.6 Headings and Labels (Level AA)
    Headings and labels must describe topic or purpose. Generic headings
    like "Click here", "More", "Section" fail. Excessively long sections
    without intermediate headings also harm wayfinding.
    Tool: analyze_heading_structure
    FAIL signals: generic_headings list non-empty
                  OR max_words_between_headings exceeds a wayfinding
                     threshold (treat > 250 as a serious gap)
    INAPPLICABLE: total_count == 0

  WCAG 3.1.4 Abbreviations (Level AAA)
    Abbreviations must have an expansion mechanism.
    Tool: analyze_readability_and_abbreviations
    FAIL signals: Abbreviation Audit -> missing_titles_list non-empty
                  OR Abbreviation Audit -> potential_unmarked_in_text non-empty

OUTPUT FORMAT (return ONLY this JSON, no markdown, no preamble):
{
  "label": "passed" | "failed" | "inapplicable",
  "severity": "critical" | "serious" | "moderate" | "minor" | "N/A",
  "issues": [
    {
      "wcag": "X.X.X",
      "evidence": "Specific finding from the tool output with actual values",
      "persona_impact": "How this affects you as Stefan",
      "recommendation": "Concrete fix"
    }
  ],
  "overall_assessment": "One-sentence summary in your voice as Stefan"
}

SEVERITY CALIBRATION:
  - CRITICAL: 2.2.2 autoplay or flashing content (you cannot read anything
              while it plays), 1.4.12 content clipping (you cannot read
              clipped text even with TTS)
  - SERIOUS: 2.4.5 only one navigation method (you get lost),
             2.4.6 generic headings (you can't tell what section you're in)
  - MODERATE: 3.1.4 unexpanded abbreviations (slows comprehension),
              2.4.6 long unbroken sections (no waypoints)

DECISION RULES:
  - If any criterion FAILs, the page label is "failed".
  - If all applicable criteria PASS, the page label is "passed".
  - INAPPLICABLE criteria don't fail the page - skip them.
"""


class StefanAgent(BaseAgenticAgent):
    def __init__(self, api_key):
        super().__init__(api_key, persona_name="Stefan")

        self.text_formatting_agent_inst = text_formatting_agent.TextFormattingAgent()
        self.animation_agent = animation_detector_agent.AnimationDetectorAgent()
        self.multiple_ways_agent = multiple_ways_checker_agent.MultipleWaysCheckerAgent()
        self.heading_agent = heading_structure_agent.HeadingStructureAgent()
        self.readability_agent = readability_analyzer_agent.ReadabilityAnalyzerAgent()

        self.tool_dispatcher = {
            "check_text_spacing_reflow": self.text_formatting_agent_inst.execute,
            "detect_animations_and_motion": self.animation_agent.execute,
            "check_navigation_methods": self.multiple_ways_agent.execute,
            "analyze_heading_structure": self.heading_agent.execute,
            "analyze_readability_and_abbreviations": self.readability_agent.execute,
        }

    def get_system_prompt(self):
        return STEFAN_SYSTEM_PROMPT

    def get_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "check_text_spacing_reflow",
                    "description": """
[WHAT] Applies the WCAG 1.4.12 spacing overrides (line-height 1.5,
letter-spacing 0.12em, word-spacing 0.16em, paragraph margin 2em) and
re-renders the page in a headless browser. Detects text clipping,
content loss, and layout breakage caused by the override.

[WHEN] Call on every page with text content. INAPPLICABLE on pages
with no text-bearing tags.

[COVERS] WCAG 1.4.12 Text Spacing.

[RETURNS] A dict with these REAL keys:
  - wcag_status: "pass" | "fail" | "inapplicable"
    NOTE: this tool uses LOWERCASE values. The other tools in your set
    use UPPERCASE. Pay attention to the case.
  - spacing_applied: boolean
  - overflow: {status: "pass" | "fail", issues: list of clipped elements}
  - content_integrity: {status: "pass" | "fail", details: ...}

[INTERPRETATION FOR STEFAN]
- 1.4.12 FAIL: wcag_status == "fail" (lowercase)
- 1.4.12 INAPPLICABLE: wcag_status == "inapplicable" (lowercase)
- Severity is CRITICAL when overflow.issues is non-empty - Stefan reads
  with TTS but still relies on visual position; clipped text breaks
  comprehension.
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
libraries. Checks reduced-motion handling and pause/stop controls.

[WHEN] Call when the HTML contains motion-related elements.

[COVERS] WCAG 2.2.2 Pause, Stop, Hide.

[RETURNS] A dict with these REAL keys:
  - wcag_222_status: "PASS" | "FAIL" | "INAPPLICABLE" - trust directly
  - total_motion_count: integer
  - css_animations_count: integer
  - autoplay_count: integer
  - animated_gifs_count: integer
  - reduced_motion_result: dict
  - pause_mechanism: dict
  - target_size_issues: list (IGNORE - not in Stefan's matrix)

[INTERPRETATION FOR STEFAN]
- Read wcag_222_status directly.
- Severity is CRITICAL when autoplay_count > 0 or animated_gifs_count > 0
  on a page with reading content - ADHD attention is hijacked instantly.
- Ignore target_size_issues for Stefan.
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
                    "name": "check_navigation_methods",
                    "description": """
[WHAT] Detects four navigation methods: navigation menu links, search
forms, sitemap links, and breadcrumbs. Counts how many DISTINCT methods
are present.

[WHEN] Call on every page that appears to be part of a larger site.

[COVERS] WCAG 2.4.5 Multiple Ways (Level AA).
Stefan's 2.4.5 evaluation requires at least TWO methods. This is different
from Elias's and Sophie's 2.4.8 (Location) which focuses on breadcrumbs
specifically.

[RETURNS] A dict with these REAL keys:
  - applicable: boolean - false on standalone/exempt pages (login,
    checkout, error pages)
  - applicability_reason: string
  - navigation_links: list of nav links
  - search: list of search forms
  - sitemap: list of sitemap links
  - breadcrumbs: list of breadcrumb structures
  - methods_found: integer count of distinct methods (each non-empty
    category counts as 1)
  - tool_name: "MultipleWaysCheckerAgent"

[INTERPRETATION FOR STEFAN]
- 2.4.5 PASS: applicable == true AND methods_found >= 2
- 2.4.5 FAIL: applicable == true AND methods_found < 2
- 2.4.5 INAPPLICABLE: applicable == false
- Severity is SERIOUS - Stefan gets lost without backup navigation.
- For the evidence string, list which methods ARE present and which
  are missing.
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
[WHAT] Inspects all <h1>-<h6> elements on the page. Reports hierarchy
validity, skipped levels, generic heading text, word counts between
consecutive headings, and h1 presence/count.

[WHEN] Call when the page has any heading elements.

[COVERS] WCAG 2.4.6 Headings and Labels.
Stefan's 2.4.6 focuses on descriptive headings (not generic text) and
adequate heading frequency (not 1000 words between two headings).
Hierarchy correctness (1.3.1) is Ian and Lakshmi's criterion, not
Stefan's - you can read it from this tool's output but don't fail
Stefan's evaluation on 1.3.1 issues alone.

[RETURNS] A dict with these REAL keys:
  - headings: list of {level, tag, text, id, position}
  - total_count: integer
  - hierarchy_valid: boolean (relates to 1.3.1, INFORMATIONAL for Stefan)
  - hierarchy_issues: list (1.3.1, INFORMATIONAL for Stefan)
  - skipped_levels: list (1.3.1, INFORMATIONAL for Stefan)
  - generic_headings: list of vague headings like "More", "Click here"
  - missing_h1: boolean (1.3.1, INFORMATIONAL for Stefan)
  - multiple_h1: boolean (1.3.1, INFORMATIONAL for Stefan)
  - h1_count: integer
  - words_between_headings: list of word counts between consecutive headings
  - max_words_between_headings: integer
  - tool_name: "HeadingStructureAgent"

[INTERPRETATION FOR STEFAN]
- 2.4.6 FAIL: generic_headings non-empty
  (severity SERIOUS - he relies on heading text as wayfinding)
- 2.4.6 FAIL also: max_words_between_headings > 250
  (severity MODERATE - sections too long without waypoints)
- 2.4.6 INAPPLICABLE: total_count == 0
- IGNORE the 1.3.1 signals (missing_h1, hierarchy_issues, skipped_levels)
  for Stefan's verdict. They affect Ian and Lakshmi but not Stefan.
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
[WHAT] Extracts visible text and computes eight readability indices plus
an abbreviation audit. Checks <abbr>/<acronym> tags for title attributes
and scans body text for all-caps tokens that look like unmarked
abbreviations.

[WHEN] Call when the page has visible text content.

[COVERS] WCAG 3.1.4 Abbreviations.
NOTE: This tool also returns readability indices (Flesch, etc.) for
3.1.5 Reading Level. 3.1.5 is Ian's criterion, NOT Stefan's. Ignore
the indices and focus only on the Abbreviation Audit section.

[RETURNS] A dict with these REAL keys (relevant subset for Stefan):
  - "Abbreviation Audit": nested dict with:
      - total_marked_tags: integer
      - properly_expanded: integer
      - missing_titles_list: list of <abbr>/<acronym> with no title
      - potential_unmarked_in_text: list of all-caps strings not in dict
  - flesch_reading_ease, flesch_kincaid_grade, etc. (IGNORE for Stefan)
  - tool_name: "ReadabilityAnalyzerAgent"

[INTERPRETATION FOR STEFAN]
- 3.1.4 FAIL: missing_titles_list non-empty OR potential_unmarked_in_text
  non-empty.
- 3.1.4 INAPPLICABLE: total_marked_tags == 0 AND potential_unmarked_in_text
  is empty.
- Severity is MODERATE - slows Stefan but doesn't block him.
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
    # HTML designed to trip Stefan's five criteria:
    #   1.4.12: fixed-height container that clips text when spacing increased
    #   2.2.2: blinking alert
    #   2.4.5: nav menu only, no search/sitemap (only 1 method)
    #   2.4.6: generic heading "Click Here"
    #   3.1.4: unexpanded acronyms scattered in text
    test_html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <title>CSE 311 - Course Dashboard</title>
      <style>
        .urgent-alert {
          background: #4b2e83;
          color: white;
          padding: 10px;
          animation: blinker 1s linear infinite;
        }
        @keyframes blinker { 50% { opacity: 0; } }
        .clip-card {
          height: 36px;
          overflow: hidden;
          border: 1px solid #ccc;
          line-height: 1.1;
          padding: 4px;
        }
      </style>
    </head>
    <body>
      <header>
        <div class="urgent-alert">SUBMISSION DEADLINE APPROACHING!</div>
        <h1>CSE 311: Foundations of Computing</h1>
        <nav>
          <a href="/modules">Modules</a>
          <a href="/grades">Grades</a>
          <a href="/resources">Click Here</a>
        </nav>
      </header>
      <main>
        <h2>Assignment Instructions</h2>
        <p>
          Complete the PSet using De Morgan's Laws and submit via the LMS by
          11:59 PM. The TA will review your work using the CSE rubric. The PR
          must be reviewed by the IRB if you collected human-subjects data.
        </p>

        <p class="clip-card">
          When you increase text spacing this paragraph stays in a fixed-height
          container and the words at the bottom of the box get cut off
          completely.
        </p>
      </main>
    </body>
    </html>
    """

    agent = StefanAgent(api_key=os.environ.get("OPENAI_API_KEY", "smoke-test"))

    print("=" * 70)
    print("STEFAN AGENT SMOKE TEST (direct tool dispatch, no LLM)")
    print("=" * 70)

    print("\n--- check_text_spacing_reflow ---")
    r = agent.execute_tool("check_text_spacing_reflow", {"html": test_html})
    print(f"wcag_status (lowercase): {r.get('wcag_status')}")
    print(f"overflow.issues: {len(r.get('overflow', {}).get('issues', []))}")

    print("\n--- detect_animations_and_motion ---")
    r = agent.execute_tool("detect_animations_and_motion", {"html": test_html})
    print(f"wcag_222_status: {r.get('wcag_222_status')}")
    print(f"css_animations_count: {r.get('css_animations_count')}")
    print(f"autoplay_count: {r.get('autoplay_count')}")

    print("\n--- check_navigation_methods ---")
    r = agent.execute_tool("check_navigation_methods", {"html": test_html})
    print(f"applicable: {r.get('applicable')}")
    print(f"methods_found: {r.get('methods_found')}")
    print(f"navigation_links: {len(r.get('navigation_links', []))}")
    print(f"search: {len(r.get('search', []))}")
    print(f"sitemap: {len(r.get('sitemap', []))}")
    print(f"breadcrumbs: {len(r.get('breadcrumbs', []))}")

    print("\n--- analyze_heading_structure ---")
    r = agent.execute_tool("analyze_heading_structure", {"html": test_html})
    print(f"total_count: {r.get('total_count')}")
    print(f"generic_headings: {len(r.get('generic_headings', []))}")
    print(f"max_words_between_headings: {r.get('max_words_between_headings')}")

    print("\n--- analyze_readability_and_abbreviations ---")
    r = agent.execute_tool("analyze_readability_and_abbreviations", {"html": test_html})
    abbr = r.get("Abbreviation Audit", {})
    print(f"missing_titles_list: {len(abbr.get('missing_titles_list', []))}")
    print(f"potential_unmarked_in_text: {abbr.get('potential_unmarked_in_text', [])}")

    print("\n" + "=" * 70)
    print("Smoke test complete.")
    print("=" * 70)
