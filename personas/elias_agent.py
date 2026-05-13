"""
Elias agent evaluating HTML
Demonstrates persona-grounded agentic tool selection
"""

import openai
import os
import json
from dotenv import load_dotenv
import sys

# Ensure we can import from the root directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools import Contrast_Checker_Agent
from tools import animation_detector_agent
from tools import autocomplete_validator_agent
from tools import heading_structure_agent
from tools import target_size_validator_agent
from tools import text_formatting_agent
from prompts.elias_system_prompt import ELIAS_SYSTEM_PROMPT

load_dotenv()

client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# Elias's tools
tools = [
    {
        "type": "function",
        "function": {
            "name": "check_aaa_color_contrast",
            "description": "Runs axe-core color checks at WCAG AAA (enhanced contrast). Critical for low vision users who struggle with pale or low-contrast text (WCAG 1.4.6).",
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
            "name": "detect_animations_and_autoplay_media",
            "description": "Detects CSS animations and autoplaying video/audio. Important for users who enable reduce motion or cannot rely on distracting movement (WCAG 2.3.3, 1.4.2).",
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
            "name": "validate_autocomplete_and_autofill",
            "description": "Validates autocomplete attributes on form fields and tests whether autofill behaves correctly. Essential when users depend on saved data due to memory limitations (WCAG 1.3.5).",
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
            "description": "Analyzes heading hierarchy, skipped levels, generic headings, and text density between headings. Supports navigation and orientation for users who need clear document structure (WCAG 1.3.1, 2.4.6).",
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
            "name": "check_wcag_text_spacing_and_reflow",
            "description": "Applies WCAG 1.4.12 text spacing overrides and checks for clipping or overflow. Surfaces barriers for users who zoom or increase spacing for low vision.",
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
contrast_agent = Contrast_Checker_Agent.ContrastAAA_HTML_Agent()
animation_agent = animation_detector_agent.AnimationDetectorAgent()
autocomplete_agent = autocomplete_validator_agent.AutocompleteValidatorAgent()
heading_agent = heading_structure_agent.HeadingStructureAgent()
target_size_agent = target_size_validator_agent.TargetSizeValidatorAgent()
text_formatting_agent_inst = text_formatting_agent.TextFormattingAgent()

TOOL_DISPATCHER = {
    "check_aaa_color_contrast": contrast_agent.execute,
    "detect_animations_and_autoplay_media": animation_agent.execute,
    "validate_autocomplete_and_autofill": autocomplete_agent.execute,
    "analyze_heading_structure": heading_agent.execute,
    "validate_target_size": target_size_agent.execute,
    "check_wcag_text_spacing_and_reflow": text_formatting_agent_inst.execute,
}

# Tool execution
def execute_elias_tool(tool_name, arguments):
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
  <title>Family Health Portal — Broken demo</title>
  <style>
    /* Tiny base text + low contrast body copy */
    body { font-size: 10px; color: #c6c6c6; background: #fdfdfd; max-width: 260px; }
    /* Zoom / reflow: fixed narrow column, no wrap, hidden overflow — long lines clip instead of reflowing */
    .zoom-trap {
      width: 220px;
      max-height: 3.2em;
      overflow: hidden;
      white-space: nowrap;
      border: 1px solid #eee;
    }
    .shimmer {
      display: inline-block;
      width: 16px;
      height: 16px;
      background: #aaa;
      animation: shimmer 0.8s linear infinite;
    }
    @keyframes shimmer {
      0% { opacity: 1; transform: translateX(0); }
      100% { opacity: 0.3; transform: translateX(6px); }
    }
    .micro { width: 18px; height: 18px; padding: 0; line-height: 1; font-size: 8px; }
    a.tiny-link { display: inline-block; width: 22px; height: 20px; overflow: hidden; font-size: 1px; }
  </style>
</head>
<body>

  <!-- Illogical structure: no h1; skip levels (h4 → h2 → h5); generic labels -->
  <h4>Section</h4>
  <p style="color:#bbbbbb;background:#ffffff;">Low-contrast notice: prescription renewals may expire without email confirmation.</p>

  <h2>More</h2>
  <h3>Click here</h3>
  <p><span class="shimmer" aria-hidden="true"></span> Flashing status indicator (decorative).</p>

  <h5>Details</h5>
  <p style="color:#d0d0d0;background:#f9f9f9;">Secondary low-contrast text: copay amounts below are estimates only.</p>

  <p class="zoom-trap">
    When you enlarge text to 200% or 300% this paragraph stays on one line inside a fixed-width box,
    so words disappear at the edges and you must scroll sideways with a tremor to read the full message.
  </p>

  <video width="140" height="80" autoplay muted playsinline loop>
    <source src="data:video/mp4;base64,AAAAHGZ0eXBpc29tAAACAGlzb21pc28yYXZjMQAAAAhmcmVlAAAA" type="video/mp4">
  </video>
  <p><small>Required medication tutorial — no captions.</small></p>

  <h2>Another block</h2>
  <a href="#" class="tiny-link" title="next">›</a>
  <button type="button" class="micro" title="close">×</button>

  <!-- Form fields intentionally have no autocomplete attributes -->
  <form id="rx-refill" method="post" action="#">
    <label>Full name<input type="text" name="patient_name" placeholder="Jane Doe"></label>
    <label>Email<input type="email" name="email" placeholder="you@example.com"></label>
    <label>Street<input type="text" name="ship_line1" placeholder="123 Main St"></label>
    <label>Card<input type="text" name="pan" placeholder="4111…"></label>
    <button type="submit" class="micro">OK</button>
  </form>

</body>
</html>
"""

messages = [
    {"role": "system", "content": ELIAS_SYSTEM_PROMPT},
    {"role": "user", "content": f"Evaluate this HTML:\n\n{test_html}"}
]

print("=== ELIAS AGENT EVALUATION ===\n")

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
        print(f"Elias wants to call: {len(assistant_message.tool_calls)} tool(s)")
        messages.append(assistant_message) 
        
        for tool_call in assistant_message.tool_calls:
            tool_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)
            
            print(f"  → {tool_name}")
            
            result = execute_elias_tool(tool_name, arguments)
            
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id, # Link it to the specific request
                "name": tool_name,
                "content": json.dumps(result)
            })
    
    else:
        print(f"\nElias's Final Persona-Based Evaluation:")
        print("------------------------------------------")
        print(assistant_message.content)
        break
        
print("\n=== EVALUATION COMPLETE ===")
