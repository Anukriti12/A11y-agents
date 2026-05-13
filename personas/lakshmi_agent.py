"""
Lakshmi agent evaluating HTML
Demonstrates persona-grounded agentic tool selection
"""

import openai
import os
import json
from dotenv import load_dotenv
import sys

# Ensure we can import from the root directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools.Contrast_Checker_Agent import ContrastAAA_HTML_Agent as ContrastCheckerAgent
from tools import heading_structure_agent
from tools import keyboard_navigation_agent
from prompts.lakshmi_system_prompt import LAKSHMI_SYSTEM_PROMPT


class NVDAAgent:
    """Delegates to ``tools.nvda_agent.run_full_analysis`` using a temporary HTML document."""

    def execute(self, html: str) -> dict:
        import tempfile
        from pathlib import Path

        from tools.nvda_agent import run_full_analysis

        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8")
        tmp.write(html)
        tmp.close()
        path = tmp.name
        try:
            uri = Path(path).resolve().as_uri()
            return run_full_analysis(uri)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass


load_dotenv()

client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# Lakshmi's tools
tools = [
    {
        "type": "function",
        "function": {
            "name": "check_aaa_color_contrast",
            "description": "Runs axe-core color checks at WCAG AAA (enhanced contrast). Some low-vision adjacent checks still matter when collaborators review with sighted QA (WCAG 1.4.6).",
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
            "name": "analyze_heading_structure",
            "description": "Analyzes heading hierarchy, skipped levels, generic headings, and text density between headings. Critical for screen reader users who navigate by headings (H key) (WCAG 1.3.1, 2.4.6).",
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
            "name": "check_keyboard_navigation",
            "description": "Analyzes HTML to find all focusable elements and checks for potential keyboard navigation issues. Essential for screen reader users who navigate entirely by keyboard (WCAG 2.1.1, 2.4.3).",
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
            "name": "run_nvda_accessibility_analysis",
            "description": "Runs NVDA-backed checks for non-text content, images of text, bypass blocks, and name/role/value across the page. Requires NVDA Speech Viewer and related tooling (Windows-oriented pipeline).",
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
    }
]

# The tool agents instantiated
contrast_agent = ContrastCheckerAgent()
heading_agent = heading_structure_agent.HeadingStructureAgent()
keyboard_agent = keyboard_navigation_agent.KeyboardNavigationAgent()
nvda_agent = NVDAAgent()

TOOL_DISPATCHER = {
    "check_aaa_color_contrast": contrast_agent.execute,
    "analyze_heading_structure": heading_agent.execute,
    "check_keyboard_navigation": keyboard_agent.execute,
    "run_nvda_accessibility_analysis": nvda_agent.execute,
}

# Tool execution
def execute_lakshmi_tool(tool_name, arguments):
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
  <title>HR self‑serve — broken SR demo</title>
  <style>
    body { font-family: sans-serif; }
    .topbar a { margin-right: 6px; }
    .fake-toggle { border: 1px solid #333; padding: 6px; cursor: default; }
  </style>
</head>
<body>

  <!-- Intentionally no skip link and no landmark regions (no header/nav/main/aside with roles) -->

  <div class="topbar">
    <a href="/dash">Dashboard</a>
    <a href="/time">Time cards</a>
    <a href="/benefits">Benefits</a>
    <a href="#"></a>
    <button type="button"></button>
    <button type="button"><img src="https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/img/dummy.png" width="14" height="14"></button>
  </div>

  <!-- Illogical heading order: no h1; start with h4; skip to h2; generic h3; jump to h5 -->
  <h4>Self‑serve</h4>
  <p>Status chart (no text alternative):</p>
  <p><img src="https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/img/dummy.png" width="180" height="90"></p>

  <h2>Overview</h2>
  <h3>Click here</h3>
  <p>Team photo:</p>
  <p><img src="https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/img/dummy.png" width="200" height="120"></p>

  <h5>Enrollment</h5>

  <!-- Interactive elements with no appropriate ARIA roles (generic div/span controls) -->
  <p><span onclick="void(0)" style="text-decoration:underline;color:#00c;">Apply for leave</span></p>
  <div tabindex="0" onclick="void(0)" class="fake-toggle">Submit request</div>

  <form id="pto" action="#" method="post">
    <p>Request PTO</p>
    <!-- Native checkbox hidden from tab order; visible “toggle” is a div with no role or aria-checked -->
    <input type="checkbox" id="halfday" name="halfday" tabindex="-1" style="position:absolute;opacity:0;width:1px;height:1px;">
    <div tabindex="0" onclick="document.getElementById('halfday').click();">
      Half day only <span id="halfday-label">(off)</span>
    </div>
    <p>No aria-checked, role, or live region — screen reader state does not track the real checkbox.</p>

    <input type="text" name="start" placeholder="Start date">
    <input type="text" name="end" placeholder="End date">

    <input type="image" src="https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/img/dummy.png" width="72" height="22">
  </form>

</body>
</html>
"""

messages = [
    {"role": "system", "content": LAKSHMI_SYSTEM_PROMPT},
    {"role": "user", "content": f"Evaluate this HTML:\n\n{test_html}"}
]

print("=== LAKSHMI AGENT EVALUATION ===\n")

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
        print(f"Lakshmi wants to call: {len(assistant_message.tool_calls)} tool(s)")
        messages.append(assistant_message) 
        
        for tool_call in assistant_message.tool_calls:
            tool_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)
            
            print(f"  → {tool_name}")
            
            result = execute_lakshmi_tool(tool_name, arguments)
            
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id, # Link it to the specific request
                "name": tool_name,
                "content": json.dumps(result)
            })
    
    else:
        print(f"\nLakshmi's Final Persona-Based Evaluation:")
        print("------------------------------------------")
        print(assistant_message.content)
        break
        
print("\n=== EVALUATION COMPLETE ===")
