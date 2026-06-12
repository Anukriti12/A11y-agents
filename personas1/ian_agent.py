"""
Ian Agent - Autism
Aligned to final 5-WCAG matrix: 1.3.1, 2.2.2, 2.4.6, 3.1.4, 3.1.5

Ian is a software developer on the autism spectrum. His WAI persona story
emphasizes plain language, expanded abbreviations, descriptive heading
structure, and predictable pages without surprise motion. This rewrite
removes tools that don't match those needs (autocomplete, keyboard,
forms) and replaces them with the three tools that do.

Tool-to-criterion mapping:
  - heading_structure_agent  -> 1.3.1, 2.4.6
  - animation_detector_agent -> 2.2.2
  - readability_analyzer_agent -> 3.1.4, 3.1.5

All tool descriptions in this file reference REAL keys that those tools
actually return. Verified against the tool sources.
"""

import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from personas.base_agent import BaseAgenticAgent
from tools import heading_structure_agent
from tools import animation_detector_agent
from tools import readability_analyzer_agent

load_dotenv()


IAN_SYSTEM_PROMPT = """
You are Ian, a software developer with autism.

You rely on plain language, expanded abbreviations, and predictable structure
to read and use a web page. Surprise animations and dense walls of text are
overwhelming. Long sentences with technical jargon make you give up.

Your WAI persona profile says directly:
  - "I like plain language and simple sentences. Short paragraphs are easier."
  - "When I see an abbreviation I don't know, I lose track of what I am reading."
  - "Descriptive headings and labels help me find what I need."
  - "When animations or videos start without me asking, I lose focus immediately."

You evaluate pages against five WCAG criteria. Each criterion has one or two
tools that produce evidence. You must call each relevant tool AT MOST ONCE,
then stop and emit your verdict.

CRITERIA YOU EVALUATE:

  WCAG 1.3.1 Info and Relationships (Level A)
    Headings must form a programmatically determinable hierarchy.
    Tool: analyze_heading_structure
    FAIL signals: missing_h1=true, multiple_h1=true, hierarchy_issues non-empty,
                  skipped_levels non-empty

  WCAG 2.4.6 Headings and Labels (Level AA)
    Headings must be descriptive (no generic "Click here", "More", "Section").
    Tool: analyze_heading_structure
    FAIL signals: generic_headings list is non-empty

  WCAG 2.2.2 Pause, Stop, Hide (Level A)
    Moving / blinking / auto-updating content must be controllable.
    Tool: detect_animations_and_motion
    Trust the tool's verdict: wcag_222_status is "PASS", "FAIL", or "INAPPLICABLE".

  WCAG 3.1.4 Abbreviations (Level AAA)
    Abbreviations must have an expansion mechanism.
    Tool: analyze_readability
    FAIL signals: Abbreviation Audit -> missing_titles_list is non-empty
                  OR Abbreviation Audit -> potential_unmarked_in_text is non-empty

  WCAG 3.1.5 Reading Level (Level AAA)
    Content should be readable at lower-secondary level (about grade 9).
    Tool: analyze_readability
    FAIL signals: flesch_kincaid_grade > 9 OR flesch_reading_ease < 60

OUTPUT FORMAT (return ONLY this JSON, no markdown, no preamble):
{
  "label": "passed" | "failed" | "inapplicable",
  "severity": "critical" | "serious" | "moderate" | "minor" | "N/A",
  "issues": [
    {
      "wcag": "X.X.X",
      "evidence": "Specific finding from the tool output, with the actual values",
      "persona_impact": "How this affects you as Ian",
      "recommendation": "Concrete fix"
    }
  ],
  "overall_assessment": "One-sentence summary in your voice as Ian"
}

SEVERITY CALIBRATION:
  - SERIOUS: 2.2.2 (autoplay/motion without pause), 3.1.5 (grade > 12 or Flesch < 40)
  - MODERATE: 1.3.1 (skipped headings), 2.4.6 (generic headings), 3.1.4 (unmarked abbreviations)
  - MINOR: 3.1.5 close to the threshold (grade 9-11)

DECISION RULES:
  - If any criterion FAILs, the page label is "failed".
  - If all applicable criteria PASS and no criterion FAILs, the page label is "passed".
  - If all tools return INAPPLICABLE, the page label is "inapplicable".
"""


class IanAgent(BaseAgenticAgent):
    def __init__(self, api_key):
        super().__init__(api_key, persona_name="Ian")

        self.heading_agent = heading_structure_agent.HeadingStructureAgent()
        self.animation_agent = animation_detector_agent.AnimationDetectorAgent()
        self.readability_agent = readability_analyzer_agent.ReadabilityAnalyzerAgent()

        self.tool_dispatcher = {
            "analyze_heading_structure": self.heading_agent.execute,
            "detect_animations_and_motion": self.animation_agent.execute,
            "analyze_readability": self.readability_agent.execute,
        }

    def get_system_prompt(self):
        return IAN_SYSTEM_PROMPT

    def get_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "analyze_heading_structure",
                    "description": """
[WHAT] Inspects all <h1>-<h6> elements on the page and reports hierarchy
validity, skipped levels, multiple or missing h1s, and generic heading text.

[WHEN] Call when the page has any heading elements. If the HTML you were
given contains <h1>, <h2>, <h3>, <h4>, <h5>, or <h6>, call this tool.

[COVERS] WCAG 1.3.1 Info and Relationships, WCAG 2.4.6 Headings and Labels.
- 1.3.1: programmatic heading hierarchy
- 2.4.6: headings must be descriptive

[RETURNS] A dict with these REAL keys (use exactly these names when reading the output):
  - headings: list of {level, tag, text, id, position} for every heading
  - total_count: integer count of all headings
  - hierarchy_valid: boolean - true only if no hierarchy issues
  - hierarchy_issues: list of out-of-order or skipped levels
  - skipped_levels: list of {from_heading, to_heading, gap} when a level is skipped
  - generic_headings: list of headings with vague text like "Click here", "More", "Section"
  - missing_h1: boolean - true if the page has no h1
  - multiple_h1: boolean - true if there is more than one h1
  - h1_count: integer
  - words_between_headings: list of word counts between consecutive headings
  - max_words_between_headings: integer

[INTERPRETATION FOR IAN]
- 1.3.1 FAIL: missing_h1 OR multiple_h1 OR hierarchy_issues non-empty OR skipped_levels non-empty
- 2.4.6 FAIL: generic_headings non-empty
- INAPPLICABLE: total_count == 0
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
libraries. Also checks whether the page honors prefers-reduced-motion and
whether a pause/stop/hide control exists.

[WHEN] Call when the HTML contains any of:
  - <video> or <audio> tags (especially with `autoplay` attribute)
  - <img> with .gif source
  - CSS @keyframes or `animation:` declarations
  - libraries like gsap, anime.js, lottie

[COVERS] WCAG 2.2.2 Pause, Stop, Hide.

[RETURNS] A dict with these REAL keys:
  - wcag_222_status: "PASS", "FAIL", or "INAPPLICABLE" - trust this verdict directly
  - total_motion_count: integer - sum of all motion sources
  - css_animations_count: integer
  - css_transitions_count: integer
  - autoplay_count: integer - count of autoplay media that runs >5 seconds
  - animated_gifs_count: integer
  - js_animation_libs: list of detected library names
  - reduced_motion_result: dict {honored: bool, ...}
  - pause_mechanism: dict {has_pause_control: bool, controls_attribute_present: bool, ...}

[INTERPRETATION FOR IAN]
- Just read wcag_222_status. If FAIL -> emit a 2.2.2 issue (severity SERIOUS).
- INAPPLICABLE means there's no motion on the page; do not raise an issue.
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
                    "name": "analyze_readability",
                    "description": """
[WHAT] Extracts visible text from the HTML and computes eight readability
indices plus an abbreviation audit. The abbreviation audit checks <abbr>
and <acronym> tags for title attributes and scans the body text for
all-caps tokens that look like unmarked abbreviations.

[WHEN] Call when the page has any visible text content (paragraphs,
articles, instructions, list items, etc.).

[COVERS] WCAG 3.1.4 Abbreviations, WCAG 3.1.5 Reading Level.

[RETURNS] A dict with these REAL keys:
  - flesch_reading_ease: 0-100 (higher = easier; <60 = harder than grade 9)
  - flesch_kincaid_grade: US grade level (higher = harder)
  - gunning_fog, smog_index, automated_readability_index, coleman_liau_index,
    linsear_write_formula, dale_chall_readability_score: additional indices
  - word_count, sentence_count, average_sentence_length, reading_time_seconds
  - "Abbreviation Audit": nested dict with:
      - total_marked_tags: integer
      - properly_expanded: integer
      - missing_titles_list: list of <abbr>/<acronym> tags with no title attribute
      - potential_unmarked_in_text: list of all-caps strings in body text
        that are NOT in the dictionary (likely unmarked abbreviations)

[INTERPRETATION FOR IAN]
- 3.1.4 FAIL: missing_titles_list non-empty OR potential_unmarked_in_text non-empty
- 3.1.5 FAIL: flesch_kincaid_grade > 9 OR flesch_reading_ease < 60
- 3.1.5 INAPPLICABLE: word_count == 0
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
#  Smoke test: instantiates the agent, dispatches each tool directly on
#  a controlled HTML sample, prints raw tool output. Does NOT invoke the LLM
#  (so it runs without OPENAI_API_KEY). The LLM-driven end-to-end test
#  follows the same pattern as the other persona files and runs when the
#  key is set.
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    import json

    # HTML chosen to trip Ian's specific criteria:
    # - skipped heading levels (1.3.1)
    # - generic heading text (2.4.6)
    # - autoplay video without pause (2.2.2)
    # - unexpanded abbreviations (3.1.4)
    # - dense bureaucratic prose (3.1.5)
    test_html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <title>Project Updates</title>
      <style>
        .marquee { animation: scroll 8s linear infinite; }
        @keyframes scroll { from { transform: translateX(100%); } to { transform: translateX(-100%); } }
      </style>
    </head>
    <body>
      <h2>Welcome</h2>
      <h5>Click here</h5>
      <p>
        The implementation of the aforementioned heuristic-driven optimization
        framework necessitates a comprehensive evaluation of the underlying
        algorithmic substrate, particularly with respect to the asymptotic
        complexity of the resultant computational artifacts.
      </p>
      <p>
        Please consult the SOP and ensure your IAM credentials are configured
        in accordance with the CIDR policies enumerated in the RFC.
      </p>
      <div class="marquee">Latest news scrolling here!</div>
      <video autoplay loop muted src="demo.mp4"></video>
      <h6>Section</h6>
    </body>
    </html>
    """

    agent = IanAgent(api_key=os.environ.get("OPENAI_API_KEY", "smoke-test"))

    # Direct tool calls (no LLM in the loop) — confirms wiring.
    print("=" * 70)
    print("IAN AGENT SMOKE TEST (direct tool dispatch, no LLM)")
    print("=" * 70)

    for tool_name in ["analyze_heading_structure",
                      "detect_animations_and_motion",
                      "analyze_readability"]:
        print(f"\n--- {tool_name} ---")
        result = agent.execute_tool(tool_name, {"html": test_html})
        # Print just the high-signal keys to keep output readable
        if tool_name == "analyze_heading_structure":
            print(f"missing_h1: {result.get('missing_h1')}")
            print(f"multiple_h1: {result.get('multiple_h1')}")
            print(f"skipped_levels: {len(result.get('skipped_levels', []))}")
            print(f"generic_headings: {len(result.get('generic_headings', []))}")
            print(f"hierarchy_issues: {len(result.get('hierarchy_issues', []))}")
        elif tool_name == "detect_animations_and_motion":
            print(f"wcag_222_status: {result.get('wcag_222_status')}")
            print(f"total_motion_count: {result.get('total_motion_count')}")
            print(f"autoplay_count: {result.get('autoplay_count')}")
            print(f"css_animations_count: {result.get('css_animations_count')}")
        elif tool_name == "analyze_readability":
            print(f"flesch_reading_ease: {result.get('flesch_reading_ease')}")
            print(f"flesch_kincaid_grade: {result.get('flesch_kincaid_grade')}")
            print(f"word_count: {result.get('word_count')}")
            abbr = result.get("Abbreviation Audit", {})
            print(f"missing_titles_list: {len(abbr.get('missing_titles_list', []))}")
            print(f"potential_unmarked_in_text: {abbr.get('potential_unmarked_in_text', [])}")

    print("\n" + "=" * 70)
    print("Smoke test complete. To run end-to-end with LLM, set OPENAI_API_KEY")
    print("and call: agent.evaluate(test_html)")
    print("=" * 70)
