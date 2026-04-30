"""
Sophie agent evaluating HTML
"""

import openai
import os
import json
from dotenv import load_dotenv
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools import readability_analyzer_agent 
# from tools import nvda_agent 
from tools import timing_checker_agent 
from tools import form_validator_agent 
from tools import autocomplete_validator_agent

load_dotenv()

client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# Sophie's system prompt
SOPHIE_PROMPT = """
You are Sophie, a mother and basketball fan with Down Syndrome.

You rely on familiar layouts and consistent labels for buttons to navigate without 
feeling disoriented or uncertain about what will happen next. Dense blocks of text 
are overwhelming for you, so you need wide line spacing and clear headings to help 
you and process information, otherwise you quit reading. If you make a mistake on
a form, you need specific, clear suggestions on how to fix the error so you don't
 feel anxious or stuck.


Your task: Evaluate HTML for accessibility from YOUR perspective.

Available tools:
- analyze_readability: Checks text complexity (you need Flesch > 60)
- nvda_agent: Checks for explicit link purpose
- timing_checker_agent: Checks for timers and any refreshes without a stop or add time button
- form_validator_agent: Checks for proper, nonvague error message
- autocomplete_validator_agent: Validates the proper attributes on forms can be correctly autocompleted

Output format: JSON with label, severity, issues
"""

# Sophie's tools
tools = [
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "analyze_link_context_and_purpose",
    #         "description": "Evaluates if links provide clear purpose (WCAG 2.4.4) by simulating NVDA screen reader output and inspecting the Accessibility Tree. Flags links that are 'silent', generic (e.g., 'click here'), or only announced as 'graphic' without destination context.",
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "html": {
    #                     "type": "string",
    #                     "description": "The full HTML source code to evaluate for link accessibility."
    #                 }
    #             },
    #             "required": ["html"]
    #         }
    #     }
    # },
    {
        "type": "function",
        "function": {
            "name": "analyze_readability",
            "description": "Calculates Flesch reading ease. Checks for unexplained abbreviations and acronyms. Sophie with down syndrome needs score > 60 for comfortable reading (WCAG 3.1.5).",
            "parameters": {
                "type": "object",
                "properties": {
                    "html": {
                        "type": "string",
                        "description": "The full HTML source code to analyze readability, acronym and abbreviation usage."
                        }
                },
                "required": ["html"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_timing_and_timeouts",
            "description": "Identifies time limits, session timeouts, or automatic page refreshes (WCAG 2.2.1). Detects if a user can turn off, adjust, or extend the time limit. Critical for users with cognitive or motor disabilities who need more time to interact with the page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "html": {
                        "type": "string",
                        "description": "The full HTML source code to analyze for timing-related elements and meta-refresh tags."
                    }
                },
                "required": ["html"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "validate_form_errors_and_labels",
            "description": "Evaluates form accessibility (WCAG 3.3.1, 3.3.3) by identifying input fields and triggering validation logic. Specifically checks for 'vague' error messages (e.g., 'Invalid input') and verifies if error suggestions are specific, helpful, and programmatically associated with the correct fields via aria-describedby.",
            "parameters": {
                "type": "object",
                "properties": {
                    "html": {
                        "type": "string",
                        "description": "The full HTML source code of the form to be validated."
                    }
                },
                "required": ["html"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "validate_autocomplete_attributes",
            "description": "Scans form inputs to ensure they use appropriate 'autocomplete' attributes (WCAG 1.3.5). Verifies that the purpose of each input (e.g., name, address, credit card) is programmatically defined, allowing browsers to correctly autofill user data and reducing cognitive load.",
            "parameters": {
                "type": "object",
                "properties": {
                    "html": {
                        "type": "string",
                        "description": "The HTML source code of the form to evaluate for autocomplete compliance."
                    }
                },
                "required": ["html"]
            }
        }
    }


]

# The tool agents instantiated
readability_agent = readability_analyzer_agent.ReadabilityAnalyzerAgent()
# nvda_agent = nvda_agent.NVDAAgent()
timing_agent = timing_checker_agent.TimingCheckerAgent()
form_agent = form_validator_agent.FormValidationAgent()
autocomplete_agent = autocomplete_validator_agent.AutocompleteValidatorAgent()

TOOL_DISPATCHER = {
    "analyze_readability": readability_agent.execute,
    # "analyze_link_context_and_purpose": nvda_agent.execute,
    "check_timing_and_timeouts": timing_agent.execute,
    "validate_form_errors_and_labels": form_agent.execute,
    "validate_autocomplete_attributes": autocomplete_agent.execute
}

# Tool execution
def execute_sophie_tool(tool_name, arguments):
    html = arguments["html"]
    
    if tool_name in TOOL_DISPATCHER:
        # Calls the actual tool's execute function
        return TOOL_DISPATCHER[tool_name](html=html)
    return {"error": f"Tool '{tool_name}' not implemented in the dispatcher."} # Error handling

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

messages = [
    {"role": "system", "content": SOPHIE_PROMPT},
    {"role": "user", "content": f"Evaluate this HTML:\n\n{test_html}"}
]

print("=== SOPHIE AGENT EVALUATION ===\n")

for iteration in range(10):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages, # Pass the WHOLE history every time
        tools=tools,
        tool_choice="auto"
    )
    
    assistant_message = response.choices[0].message
    
    if assistant_message.tool_calls:
        messages.append(assistant_message) 
        
        for tool_call in assistant_message.tool_calls:
            tool_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)
            
            result = execute_sophie_tool(tool_name, arguments)
            
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id, # Link it to the specific request
                "name": tool_name,
                "content": json.dumps(result)
            })
    
    else:
        print(f"\nSophie's Final Persona-Based Evaluation:")
        print("------------------------------------------")
        print(assistant_message.content)
        break
print("\n=== EVALUATION COMPLETE ===")