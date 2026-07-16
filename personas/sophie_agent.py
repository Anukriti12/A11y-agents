"""
Sophie Agent - Down Syndrome (Intellectual and Developmental Disability)
Refactored to class-based architecture with BaseAgenticAgent
"""

import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from personas.base_agent import BaseAgenticAgent
from tools import readability_analyzer_agent 
from tools import timing_checker_agent 
from tools import form_validator_agent 
from tools import autocomplete_validator_agent

load_dotenv()

SOPHIE_SYSTEM_PROMPT = """
You are Sophie, a mother and basketball fan with Down Syndrome.

You rely on familiar layouts and consistent labels for buttons to navigate without feeling disoriented. 
Dense blocks of text are overwhelming for you, so you need wide line spacing and clear headings to help 
you process information - otherwise you quit reading.

If you make a mistake on a form, you need specific, clear suggestions on how to fix the error so you 
don't feel anxious or stuck.

You need simple language (Flesch reading ease > 60). Complex words and long sentences make you give up.

Output ONLY valid JSON (no preamble, no markdown):
{
  "label": "passed" | "failed" | "inapplicable",
  "severity": "critical" | "serious" | "moderate" | "minor" | "N/A",
  "issues": [
    {
      "wcag": "X.X.X",
      "evidence": "What the tool found",
      "persona_impact": "Why this affects YOU as Sophie with Down Syndrome",
      "recommendation": "How to fix it"
    }
  ],
  "overall_assessment": "Brief summary from your perspective"
}

DECISION CRITERIA:
- FAILED = Violations that make content hard for Sophie to understand or complete tasks
- PASSED = Content is clear, simple, and supportive
- Severity:
  - CRITICAL: Prevents task completion (vague form errors, impossible time limits)
  - SERIOUS: Makes content too hard to understand (complex text, no autocomplete help)
  - MODERATE: Creates frustration but manageable

TOOL USAGE:
- Call each tool AT MOST ONCE
- If text present → Call analyze_readability to check simplicity
- If <form> present → Call validate_form_errors_and_labels AND validate_autocomplete_attributes
- If <meta refresh> or time limit text → Call check_timing_and_timeouts

INTERPRETING RESULTS:
- analyze_readability: If flesch_score < 60 → FAILED serious
- validate_form_errors_and_labels: If vague_errors found → FAILED critical
- check_timing_and_timeouts: If time_limits without control → FAILED serious
- validate_autocomplete_attributes: If missing autocomplete → FAILED moderate
"""

class SophieAgent(BaseAgenticAgent):
    def __init__(self, api_key):
        super().__init__(api_key, persona_name="Sophie")
        
        self.readability_agent = readability_analyzer_agent.ReadabilityAnalyzerAgent()
        self.timing_agent = timing_checker_agent.TimingCheckerAgent()
        self.form_agent = form_validator_agent.FormValidationAgent()
        self.autocomplete_agent = autocomplete_validator_agent.AutocompleteValidatorAgent()
        
        self.tool_dispatcher = {
            "analyze_readability": self.readability_agent.execute,
            "check_timing_and_timeouts": self.timing_agent.execute,
            "validate_form_errors_and_labels": self.form_agent.execute,
            "validate_autocomplete_attributes": self.autocomplete_agent.execute
        }
    
    def get_system_prompt(self):
        return SOPHIE_SYSTEM_PROMPT
    
    def get_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "analyze_readability",
                    "description": """
[WHAT] Calculates Flesch reading ease score, checks for complex words and unexplained abbreviations.

[WHEN] Use this when:
- Page has text content (paragraphs, instructions, articles)
- Checking if language is simple enough for IDD users
- Text appears to use jargon or complex vocabulary

[WHO] CRITICAL for Sophie (Down Syndrome - needs plain, simple language)
- Sophie: Flesch > 60 required - complex text causes her to give up entirely
- Also helps: Stefan (dyslexia), general audience (plain language benefits everyone)

[RETURNS]
- flesch_score: 0-100 (if < 60 → FAILED serious for Sophie)
- complex_words: List of difficult vocabulary
- unexplained_abbreviations: Acronyms without definitions
- avg_sentence_length: Long sentences are harder to process

[DON'T USE]
- Page has no text content (images/videos only)
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
[WHAT] Identifies time limits, auto-refresh, session timeouts (WCAG 2.2.1). Checks for user control.

[WHEN] Use this when:
- HTML has <meta http-equiv="refresh">
- Text mentions time limits ("expires in X seconds", "timeout")
- Evaluating timed forms or checkout flows

[WHO] CRITICAL for Sophie (processes information slower, needs extra time)
- Sophie: Time limits cause severe anxiety - she can't complete tasks under pressure
- Also helps: Ade (voice control slower), Elias (tremor slower), all users under stress

[RETURNS]
- time_limits_found: Meta refresh, timeout text
- timeout_duration: How long before expiry
- user_control_available: Can user extend/disable time limit?
- If time_limits > 0 AND no user_control → FAILED serious

[DON'T USE]
- Static content with no time-sensitive elements
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
[WHAT] Checks forms for proper labels and specific error messages (WCAG 3.3.1, 3.3.2, 3.3.3).

[WHEN] Use this when:
- HTML contains <form> element (AUTOMATIC TRIGGER)
- Has input fields, selects, textareas
- Checking if forms provide clear guidance

[WHO] CRITICAL for Sophie (needs clear, specific error messages to fix mistakes)
- Sophie: Vague errors like "Invalid input" cause anxiety and confusion - she doesn't know how to fix
- Needs specific guidance: "Email must include @" not just "Error"
- Also helps: Ade (voice needs labels), Lakshmi (screen reader needs labels)

[RETURNS]
- unlabeled_inputs: Fields missing <label> or aria-label
- vague_errors: Generic errors without specifics (if found → FAILED critical)
- missing_suggestions: Errors without "how to fix" guidance
- If vague_errors found → FAILED critical (blocks Sophie completely)

[DON'T USE]
- Page has no forms
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
                    "name": "validate_autocomplete_attributes",
                    "description": """
[WHAT] Checks if form inputs have autocomplete attributes to help browsers autofill (WCAG 1.3.5).

[WHEN] Use this when:
- HTML has <form> with input fields
- Checking if forms reduce cognitive load
- Inputs collect personal data (name, email, address, phone)

[WHO] Important for Sophie (autocomplete reduces memory burden and typing errors)
- Sophie: Autocomplete helps her fill forms correctly without remembering/typing everything
- Reduces anxiety about making mistakes
- Also helps: Elias (reduces typing with tremor), all users (convenience)

[RETURNS]
- missing_autocomplete: Inputs that should have autocomplete but don't
- autocomplete_coverage: Percentage of appropriate fields with autocomplete
- If missing_autocomplete NOT EMPTY → FAILED moderate

[DON'T USE]
- Page has no forms
- Form has no personal data fields (e.g., search box only)
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
                return {"error": str(e), "tool_name": tool_name, "status": "failed"}
        
        return {"error": f"Unknown tool: {tool_name}"}


# Test code - ONLY runs when you execute this file directly
if __name__ == "__main__":
    import json
    
    test_html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <meta http-equiv="refresh" content="60">
      <title>Seattle Ballers Fan Club - Sign Up</title>
    </head>
    <body>
      <header>
        <h1>Seattle Ballers Fan Club</h1>
        <nav>
          <a href="/home">Home</a>
          <a href="/schedule">Schedule</a>
          <a href="/merch">Click here</a>
          <a href="/news">Read more</a>
        </nav>
      </header>
      <main>
        <section>
          <h2>Join the Club</h2>
          <p>
            The SBFC (Seattle Ballers Fan Club) membership portal requires all prospective members 
            to complete the subsequent registration form in its entirety, ensuring that all mandatory 
            fields satisfy the requisite validation criteria prior to submission. Incomplete or 
            erroneous submissions will be subject to iterative resubmission protocols.
          </p>
          <form id="signup-form">
            <label for="fname">First Name:</label>
            <input type="text" id="fname" name="fname">
            
            <label for="lname">Last Name:</label>
            <input type="text" id="lname" name="lname">
            
            <label for="email">Email:</label>
            <input type="text" id="email" name="email">
            
            <label for="dob">DOB:</label>
            <input type="text" id="dob" name="dob" placeholder="MM/DD/YYYY">
            
            <label for="phone">Phone:</label>
            <input type="text" id="phone" name="phone">
            
            <label for="addr">Address:</label>
            <input type="text" id="addr" name="addr">
            
            <label for="city">City:</label>
            <input type="text" id="city" name="city">
            
            <label for="zip">ZIP:</label>
            <input type="text" id="zip" name="zip">
            
            <label for="cc">CC Number:</label>
            <input type="text" id="cc" name="cc">
            
            <label for="promo">Promo Code:</label>
            <input type="text" id="promo" name="promo">
            
            <label for="tier">Membership Tier:</label>
            <select id="tier" name="tier">
              <option value="">-- Select --</option>
              <option value="bronze">Bronze</option>
              <option value="gold">Gold</option>
              <option value="vip">VIP</option>
            </select>
            
            <!-- Vague error messages -->
            <div class="error" id="fname-error">Invalid!</div>
            <div class="error" id="email-error">Error occurred.</div>
            <div class="error" id="cc-error">Bad input.</div>
            
            <button type="submit">Go</button>
          </form>
        </section>
        <section>
          <h2>Latest News</h2>
          <p>
            Q3 YOY stats demonstrate a 47% improvement in avg. PPG metrics with a statistically 
            significant p-value (&lt;0.05) correlating to enhanced PnR efficiency across the 
            roster's starting 5.
          </p>
          <a href="/full-stats">Click here for more</a>
        </section>
      </main>
      <footer>
        <p>© 2025 SBFC. All rights reserved. TOS apply. See FAQ for details.</p>
      </footer>
    </body>
    </html>
    """
    
    agent = SophieAgent(os.environ["OPENAI_API_KEY"])
    result = agent.evaluate(test_html)
    
    print("=" * 70)
    print("SOPHIE AGENT TEST")
    print("=" * 70)
    print(json.dumps(result, indent=2))