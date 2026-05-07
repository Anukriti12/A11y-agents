"""
Ade agent evaluating HTML
Demonstrates persona-grounded agentic tool selection
"""

import openai
import os
import json
from dotenv import load_dotenv
import sys

# Ensure we can import from the root directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools import keyboard_navigation_agent
from tools import target_size_validator_agent
from tools import timing_checker_agent
from tools import form_validator_agent
from prompts.ade_system_prompt import ADE_SYSTEM_PROMPT

load_dotenv()

client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# Ade's tools
tools = [
    {
        "type": "function",
        "function": {
            "name": "check_keyboard_navigation",
            "description": "Analyzes HTML to find all focusable elements and checks for potential keyboard navigation issues. Essential for users relying heavily on keyboard navigation (WCAG 2.1.1, 2.4.3).",
            "parameters": {
                "type": "object",
                "properties": {
                    "html": {
                        "type": "string",
                        "description": "The full HTML source code to evaluate."
                    }
                },
                "required": ["html"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "validate_target_size",
            "description": "Checks for interactive elements that are too small to easily click. Identifies click targets smaller than 44x44 pixels, which is a barrier for users with limited fine motor control (WCAG 2.5.5).",
            "parameters": {
                "type": "object",
                "properties": {
                    "html": {
                        "type": "string",
                        "description": "The full HTML source code to evaluate."
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
            "description": "Identifies time limits, session timeouts, or automatic page refreshes (WCAG 2.2.1). Detects if a user can turn off, adjust, or extend the time limit.",
            "parameters": {
                "type": "object",
                "properties": {
                    "html": {
                        "type": "string",
                        "description": "The full HTML source code to evaluate."
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
            "description": "Analyzes HTML forms for accessibility issues. Checks for properly associated labels, which is critical for speech recognition software (WCAG 3.3.2).",
            "parameters": {
                "type": "object",
                "properties": {
                    "html": {
                        "type": "string",
                        "description": "The full HTML source code of the form to evaluate."
                    }
                },
                "required": ["html"]
            }
        }
    }
]

# The tool agents instantiated
keyboard_agent = keyboard_navigation_agent.KeyboardNavigationAgent()
target_size_agent = target_size_validator_agent.TargetSizeValidatorAgent()
timing_agent = timing_checker_agent.TimingCheckerAgent()
form_agent = form_validator_agent.FormValidationAgent()

TOOL_DISPATCHER = {
    "check_keyboard_navigation": keyboard_agent.execute,
    "validate_target_size": target_size_agent.execute,
    "check_timing_and_timeouts": timing_agent.execute,
    "validate_form_errors_and_labels": form_agent.execute
}

# Tool execution
def execute_ade_tool(tool_name, arguments):
    html = arguments["html"]
    
    if tool_name in TOOL_DISPATCHER:
        # Calls the actual tool's execute function
        return TOOL_DISPATCHER[tool_name](html=html)
    return {"error": f"Tool '{tool_name}' not implemented in the dispatcher."}

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
        <!-- Missing label -->
        <input type="text" name="address" placeholder="Address">

        <!-- Missing label -->
        <input type="text" name="city" placeholder="City">

        <button type="submit">Submit</button>
      </form>
    </section>

    <section>
      <h2>Add a tip?</h2>
      <!-- Small click target -->
      <button class="tiny-btn">+</button>
      <button class="tiny-btn">-</button>
    </section>

    <!-- Keyboard trap potential via bad navigation elements or modal logic -->
    <div id="popup" tabindex="0">
      <p>Special offer!</p>
    </div>

  </main>

</body>
</html>
"""

messages = [
    {"role": "system", "content": ADE_SYSTEM_PROMPT},
    {"role": "user", "content": f"Evaluate this HTML:\n\n{test_html}"}
]

print("=== ADE AGENT EVALUATION ===\n")

for iteration in range(10):
    print(f"--- Iteration {iteration + 1} ---")
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages, # Pass the WHOLE history every time
        tools=tools,
        tool_choice="auto"
    )
    
    assistant_message = response.choices[0].message
    
    if assistant_message.tool_calls:
        print(f"Ade wants to call: {len(assistant_message.tool_calls)} tool(s)")
        messages.append(assistant_message) 
        
        for tool_call in assistant_message.tool_calls:
            tool_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)
            
            print(f"  → {tool_name}")
            
            result = execute_ade_tool(tool_name, arguments)
            
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id, # Link it to the specific request
                "name": tool_name,
                "content": json.dumps(result)
            })
    
    else:
        print(f"\nAde's Final Persona-Based Evaluation:")
        print("------------------------------------------")
        print(assistant_message.content)
        break
        
print("\n=== EVALUATION COMPLETE ===")
