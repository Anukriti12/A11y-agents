"""
Ian Agent - Autism
Needs predictability, consistency, and literal language
"""

import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from personas.base_agent import BaseAgenticAgent
from tools import animation_detector_agent
from tools import autocomplete_validator_agent
from tools import keyboard_navigation_agent
from tools import readability_analyzer_agent
from tools import form_validator_agent

load_dotenv()

IAN_PROMPT = """
You are Ian, a software developer with autism.

You rely heavily on predictability and consistency. Unexpected changes in navigation, inconsistent labeling, or sudden animations cause significant distress and cognitive overload.

Critical barriers for you:
- Unexpected animations → SENSORY OVERLOAD
- Inconsistent navigation → DISORIENTED
- Ambiguous language → CAN'T UNDERSTAND
- Vague errors → ANXIOUS
- Unpredictable interactions → STRESSED

You need:
- Consistent navigation patterns (WCAG 3.2.3)
- Predictable behaviors (WCAG 3.2.4)
- No unexpected animations (WCAG 2.2.2)
- Literal, clear language (WCAG 3.1.3)
- Consistent error messages (WCAG 3.3.1)

Output ONLY valid JSON:
{
  "label": "passed" | "failed",
  "severity": "critical" | "serious" | "moderate" | "minor" | "N/A",
  "issues": [{
    "wcag": "X.X.X",
    "evidence": "What found",
    "persona_impact": "Why affects Ian",
    "recommendation": "Fix"
  }],
  "overall_assessment": "Summary"
}

INTERPRETING TOOLS:
- If unexpected_animations > 0 → FAILED (serious)
- If inconsistent_navigation found → FAILED (serious)
- If ambiguous_language found → FAILED (moderate)
- If vague_errors is NOT EMPTY → FAILED (moderate)
"""


class IanAgent(BaseAgenticAgent):
    def __init__(self, api_key):
        super().__init__(api_key, persona_name="Ian")
        
        self.animation_agent = animation_detector_agent.AnimationDetectorAgent()
        self.autocomplete_agent = autocomplete_validator_agent.AutocompleteValidatorAgent()
        self.keyboard_agent = keyboard_navigation_agent.KeyboardNavigationAgent()
        self.readability_agent = readability_analyzer_agent.ReadabilityAnalyzerAgent()
        self.form_agent = form_validator_agent.FormValidationAgent()
        
        self.tool_dispatcher = {
            "detect_animations": self.animation_agent.execute,
            "validate_autocomplete": self.autocomplete_agent.execute,
            "check_keyboard_navigation": self.keyboard_agent.execute,
            "analyze_readability": self.readability_agent.execute,
            "validate_forms": self.form_agent.execute
        }
    
    def get_system_prompt(self):
        return IAN_PROMPT
    
    def get_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "detect_animations",
                    "description": """
[WHAT] Detects unexpected animations or auto-updating content.

[WHEN] Use when:
- HTML has <video>, <audio>, CSS animations
- Checking for unpredictable content changes
- Page has auto-refresh or dynamic content

[WHO] CRITICAL for Ian (autism - unexpected changes cause distress)
- Ian: Sudden animations → sensory overload, can't focus
- Also helps: Stefan (ADHD - distraction)

[RETURNS]
- animation_count: If >0 AND no user control → FAILED (serious)
- autoplay_videos, unexpected_motion

[DON'T USE] When page is entirely static
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
                    "name": "validate_autocomplete",
                    "description": """
[WHAT] Checks form autocomplete attributes for predictable data entry.

[WHEN] Use when HTML contains forms asking for personal data.

[WHO] Important for Ian (autism - predictable form filling reduces anxiety)
- Ian: Autocomplete = predictable, consistent data entry

[RETURNS]
- missing_autocomplete: Fields that should have it

[DON'T USE] When no forms present
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
                    "name": "check_keyboard_navigation",
                    "description": """
[WHAT] Validates predictable keyboard navigation order.

[WHEN] Use when HTML has interactive elements.

[WHO] Important for Ian (autism - needs predictable tab order)
- Ian: Unpredictable focus order → confused, anxious

[RETURNS]
- tab_order_issues: Illogical sequence (if present → FAILED moderate)
- keyboard_traps

[DON'T USE] When no interactive elements
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
                    "name": "analyze_readability",
                    "description": """
[WHAT] Checks for literal, clear language (no idioms/ambiguity).

[WHEN] Use when page has text content.

[WHO] CRITICAL for Ian (autism - needs literal language)
- Ian: "Things are heating up!" → confusing metaphor
- Needs direct, concrete language

[RETURNS]
- complex_words, ambiguous_phrases
- idioms_found: If present → FAILED (moderate)

[DON'T USE] When minimal text
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
                    "name": "validate_forms",
                    "description": """
[WHAT] Checks for consistent, predictable form validation and errors.

[WHEN] Use when HTML contains forms.

[WHO] CRITICAL for Ian (autism - needs consistent error patterns)
- Ian: Vague or inconsistent errors → anxious, confused

[RETURNS]
- vague_errors: If NOT EMPTY → FAILED (moderate)
- consistent_error_patterns: Boolean

[DON'T USE] When no forms
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
                return {"error": str(e), "tool_name": tool_name}
        
        return {"error": f"Unknown tool: {tool_name}"}


# Test code - ONLY runs when you execute this file directly
if __name__ == "__main__":
    import json
    
    test_html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <title>Project Updates</title>
      <style>
        .flash { animation: blink 1s infinite; }
        @keyframes blink { 50% { opacity: 0; } }
      </style>
    </head>
    <body>
      <nav>
        <a href="/home">Home</a>
        <a href="/about">About</a>
        <a href="/contact">Contact</a>
      </nav>
      <main>
        <h1>Latest Updates</h1>
        <p>Things are heating up! Click here for more info.</p>
        <div class="flash">NEW!</div>
        
        <h2>Submit Feedback</h2>
        <form>
          <label for="name">Name:</label>
          <input type="text" id="name" name="name">
          
          <label for="email">Email:</label>
          <input type="email" id="email" name="email">
          
          <label for="comment">Comment:</label>
          <textarea id="comment" name="comment"></textarea>
          
          <!-- Vague error -->
          <div class="error" style="display:none;">Error!</div>
          
          <button type="submit">Send</button>
        </form>
      </main>
    </body>
    </html>
    """
    
    agent = IanAgent(os.environ["OPENAI_API_KEY"])
    result = agent.evaluate(test_html)
    
    print("=" * 70)
    print("IAN AGENT TEST")
    print("=" * 70)
    print(json.dumps(result, indent=2))