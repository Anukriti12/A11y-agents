"""
Stefan Agent - ADHD + Dyslexia
Refactored to class-based architecture with BaseAgenticAgent
"""

import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from personas.base_agent import BaseAgenticAgent
from tools import readability_analyzer_agent 
from tools import animation_detector_agent 
from tools import heading_structure_agent 
from tools import text_formatting_agent
from tools import multiple_ways_checker_agent

load_dotenv()

STEFAN_SYSTEM_PROMPT = """
You are Stefan, a student with dyslexia and ADHD.

You struggle to stay focused when motion appears on screen - your attention is immediately pulled away 
from text you're trying to read. Autoplay videos are particularly disruptive.

Dense, complex text is difficult for you. You need Flesch reading ease scores above 60 to read 
comfortably. You use text-to-speech software to help.

Justified text alignment and tight line spacing make it hard to track lines. You need clear heading 
structure to navigate documents without getting lost.

Output ONLY valid JSON (no preamble, no markdown):
{
  "label": "passed" | "failed" | "inapplicable",
  "severity": "critical" | "serious" | "moderate" | "minor" | "N/A",
  "issues": [
    {
      "wcag": "X.X.X",
      "evidence": "What the tool found",
      "persona_impact": "Why this affects YOU as Stefan with ADHD and dyslexia",
      "recommendation": "How to fix it"
    }
  ],
  "overall_assessment": "Brief summary from your perspective"
}

DECISION CRITERIA:
- FAILED = One or more WCAG violations found that impact Stefan
- PASSED = All checks pass, no barriers for Stefan
- Severity calibration:
  - CRITICAL: Completely prevents you from reading/using the page (autoplay video during reading)
  - SERIOUS: Major barrier requiring significant workarounds (Flesch < 40, complex jargon)
  - MODERATE: Inconvenient but manageable (poor heading structure, tight spacing)
  - MINOR: Best practice issue with minimal impact

TOOL USAGE RULES:
- Call each tool AT MOST ONCE per evaluation
- Stop when you have enough evidence (found FAIL → conclude immediately)
- If you see <video autoplay> or CSS animations → MUST call detect_animations
- If text looks complex or has jargon → Call analyze_readability
- If you see <h4> before <h2> or skipped levels → Call check_heading_structure
- If you see text-align: justify → Call check_text_formatting

INTERPRETING TOOL RESULTS:
- detect_animations: If animation_count > 0 OR autoplay found → FAILED critical
- analyze_readability: If flesch_score < 60 → FAILED serious
- check_heading_structure: If heading_issues NOT EMPTY → FAILED moderate
- check_text_formatting: If justified_text found → FAILED moderate
"""

class StefanAgent(BaseAgenticAgent):
    def __init__(self, api_key):
        super().__init__(api_key, persona_name="Stefan")
        
        # Instantiate tool agents
        self.readability_agent = readability_analyzer_agent.ReadabilityAnalyzerAgent()
        self.animation_agent = animation_detector_agent.AnimationDetectorAgent()
        self.heading_agent = heading_structure_agent.HeadingStructureAgent()
        self.text_format_agent = text_formatting_agent.TextFormattingAgent()
        self.multiple_ways_agent = multiple_ways_checker_agent.MultipleWaysCheckerAgent()
        
        # Tool dispatcher
        self.tool_dispatcher = {
            "analyze_readability": self.readability_agent.execute,
            "detect_animations": self.animation_agent.execute,
            "check_heading_structure": self.heading_agent.execute,
            "check_text_formatting": self.text_format_agent.execute,
            "check_multiple_ways": self.multiple_ways_agent.execute
        }
    
    def get_system_prompt(self):
        """Return Stefan's persona prompt"""
        return STEFAN_SYSTEM_PROMPT
    
    def get_tools(self):
        """Return Stefan's available tools with structured descriptions"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "analyze_readability",
                    "description": """
[WHAT] Calculates Flesch reading ease score and identifies complex vocabulary, unexplained abbreviations.

[WHEN] Use this when:
- Page has text content (paragraphs, articles, instructions)
- Text appears complex or uses jargon
- Checking if content is readable for users with dyslexia
- Page has unexplained acronyms or abbreviations

[WHO] CRITICAL for Stefan (dyslexia - needs simple, clear language)
- Stefan: Needs Flesch reading ease > 60 to read comfortably with dyslexia
- Also helps: Sophie (IDD - needs plain language)

[RETURNS]
- flesch_score: 0-100 scale (if < 60 → FAILED serious for Stefan)
- complex_words: List of difficult vocabulary
- unexplained_abbreviations: Acronyms without definitions
- If flesch_score >= 60 AND no unexplained abbreviations → PASSED

[DON'T USE]
- Page is purely visual (images, videos) with no text
- Already confirmed page has no text content
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
                    "name": "detect_animations",
                    "description": """
[WHAT] Detects autoplay videos, GIFs, CSS animations that distract users with ADHD (WCAG 2.2.2, 2.3.3).

[WHEN] Use this when:
- HTML contains <video> or <audio> tags
- HTML has <img src="*.gif">
- CSS contains @keyframes or animation properties
- Checking for motion that disrupts focus

[WHO] CRITICAL for Stefan (ADHD - motion immediately breaks concentration)
- Stefan: Autoplay videos completely prevent reading - attention is hijacked
- Also helps: Ian (autism - unexpected motion causes distress), Elias (motion sensitivity)

[RETURNS]
- animation_count: Number of animated elements found
- autoplay_found: Boolean - is there autoplay video/audio?
- animation_types: List of animation sources (video, gif, css)
- controls_available: Can user pause/stop the motion?
- If animation_count > 0 OR autoplay_found = true → FAILED critical (unless pause control available)

[DON'T USE]
- Page is static text/images only
- Already confirmed no video, gif, or CSS animations present
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
                    "name": "check_heading_structure",
                    "description": """
[WHAT] Validates heading hierarchy (H1-H6) for logical navigation and comprehension (WCAG 1.3.1, 2.4.6).

[WHEN] Use this when:
- Page has heading tags (<h1>, <h2>, etc.)
- Checking document structure and navigation
- Evaluating if content is organized logically

[WHO] Important for Stefan (ADHD - needs clear structure to track reading position)
- Stefan: Skipped heading levels or illogical order makes it hard to understand document organization
- Also helps: Lakshmi (screen reader navigation), all users (content comprehension)

[RETURNS]
- heading_hierarchy: List of headings in order (h1, h2, h3...)
- skipped_levels: Heading jumps (e.g., h1 → h4, skipping h2, h3)
- multiple_h1s: Boolean - more than one h1?
- generic_headings: Vague headings like "Click here", "More"
- If skipped_levels NOT EMPTY OR generic_headings found → FAILED moderate

[DON'T USE]
- Page has no headings at all
- Page is a single paragraph with no structure
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
                    "name": "check_text_formatting",
                    "description": """
[WHAT] Checks for justified text alignment and line-height < 1.5x which are problematic for dyslexia (WCAG 1.4.8, 1.4.12).

[WHEN] Use this when:
- Page has text content with CSS styling
- Checking if text formatting supports readability
- Looking for justified text or tight line spacing

[WHO] CRITICAL for Stefan (dyslexia - justified text creates uneven spacing that makes tracking difficult)
- Stefan: Justified text creates rivers of white space that disrupt reading flow
- Tight line spacing causes line skipping and re-reading
- Also helps: Users with low vision who need adequate spacing

[RETURNS]
- justified_text_found: Boolean - is text-align: justify used?
- tight_line_height: Elements with line-height < 1.5
- text_spacing_issues: Other spacing problems
- If justified_text_found OR tight_line_height found → FAILED moderate

[DON'T USE]
- Page has no text content
- Text has no custom styling (uses browser defaults)
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
                    "name": "check_multiple_ways",
                    "description": """
[WHAT] Verifies at least 2 navigation methods exist (menu + search, menu + sitemap) (WCAG 2.4.5).

[WHEN] Use this when:
- Evaluating site navigation
- Page is part of a multi-page site (has navigation elements)
- Checking if users can find content without getting lost

[WHO] Helps Stefan (ADHD - needs multiple ways to find content without getting lost)
- Stefan: Needs backup navigation methods when he loses track of where he is
- Also helps: All users (improves findability)

[RETURNS]
- navigation_methods: List of available methods (menu, search, sitemap, breadcrumbs)
- methods_count: Number of distinct navigation methods
- If methods_count < 2 → FAILED moderate

[DON'T USE]
- Single-page application with no navigation
- Static single page (not part of a larger site)
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
        """Execute the requested tool with error handling"""
        html = arguments.get("html", "")
        
        if not html:
            return {
                "error": "Missing 'html' parameter",
                "tool_name": tool_name,
                "status": "failed"
            }
        
        if tool_name in self.tool_dispatcher:
            try:
                return self.tool_dispatcher[tool_name](html=html)
            except Exception as e:
                return {
                    "error": str(e),
                    "tool_name": tool_name,
                    "status": "failed"
                }
        
        return {
            "error": f"Unknown tool: {tool_name}",
            "available_tools": list(self.tool_dispatcher.keys())
        }

# Test code - ONLY runs when you execute this file directly
if __name__ == "__main__":
    import json
    
    test_html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <title>UW - CSE 311: Course Dashboard</title>
      <style>
        /* Flashing alert - nightmare for focus */
        .urgent-alert {
          background-color: #4b2e83;
          color: white;
          padding: 10px;
          text-align: center;
          animation: blinker 1.5s linear infinite;
        }
        @keyframes blinker {
          50% { opacity: 0; }
        }
      </style>
    </head>
    <body>
      <header>
        <div class="urgent-alert" role="alert">
          ⚠️ SUBMISSION DEADLINE APPROACHING! ⚠️
        </div>
        <h1>CSE 311: Foundations of Computing</h1>
        <nav>
          <ul>
            <li><a href="/modules">Modules</a></li>
            <li><a href="/grades">Grades</a></li>
            <li><a href="/resources">Click Here</a></li>
          </ul>
        </nav>
      </header>
      <main>
        <section>
          <h6>Assignment Instructions</h6>
          <p>
            The pedagogical objectives of this particular problem set necessitate a 
            comprehensive understanding of Boolean algebraic structures and the 
            application of De Morgan's Laws within a constrained propositional logic 
            framework. Students must ensure that their formalized proofs adhere to 
            the rigorous syntactic requirements stipulated in the departmental handbook.
          </p>
          
          <form id="hw-upload">
            <h3>Submit Your Work</h3>
            <label for="student_id">Student ID:</label>
            <input type="text" id="student_id" name="sid">
            <label for="email">University Email:</label>
            <input type="text" id="email" name="u_email">
            <button type="submit">Submit</button>
          </form>
        </section>
        <section>
          <h2>Weekly Readings</h2>
          <p>Please read the following chapters before Tuesday's lecture.</p>
          <div class="list-item">Chapter 1: Logic</div>
          <div class="list-item">Chapter 2: Proofs</div>
        </section>
      </main>
      <footer>
        <p>Contact the TA at: <a href="mailto:ta@uw.edu">Email</a></p>
      </footer>
    </body>
    </html>
    """
    
    agent = StefanAgent(os.environ["OPENAI_API_KEY"])
    result = agent.evaluate(test_html)
    
    print("=" * 70)
    print("STEFAN AGENT TEST")
    print("=" * 70)
    print(json.dumps(result, indent=2))