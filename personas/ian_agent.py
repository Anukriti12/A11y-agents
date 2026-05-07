"""
Ian agent evaluating HTML
Demonstrates persona-grounded agentic tool selection
"""

import openai
import os
import json
from dotenv import load_dotenv
import sys

# Ensure we can import from the root directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools import animation_detector_agent
from tools import consistency_validator_agent
from tools import heading_structure_agent
from tools import readability_analyzer_agent
from prompts.ian_system_prompt import IAN_SYSTEM_PROMPT

load_dotenv()

client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# Ian's tools
tools = [
    {
        "type": "function",
        "function": {
            "name": "detect_animations",
            "description": "Detects CSS animations and autoplay media. Autoplaying videos and animations are highly distracting and overwhelming for Ian.",
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
            "name": "validate_consistency",
            "description": "Analyzes multiple pages to detect inconsistencies in layout and navigation. Ian thrives on consistency and predictability; sudden changes cause panic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "html_pages": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "An array of HTML source code strings from different pages to compare."
                    }
                },
                "required": ["html_pages"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_heading_structure",
            "description": "Analyzes heading hierarchy, logical structure, and content quality. Ian needs clear, descriptive headings and struggles with long blocks of text without structure.",
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
            "name": "analyze_readability",
            "description": "Calculates readability scores and checks for unmarked abbreviations. Ian has difficulty with non-literal language, metaphors, and corporate jargon.",
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
animation_agent = animation_detector_agent.AnimationDetectorAgent()
consistency_agent = consistency_validator_agent.ConsistencyValidatorAgent()
heading_agent = heading_structure_agent.HeadingStructureAgent()
readability_agent = readability_analyzer_agent.ReadabilityAnalyzerAgent()

TOOL_DISPATCHER = {
    "detect_animations": lambda args: animation_agent.execute(args["html"]),
    "validate_consistency": lambda args: consistency_agent.execute(args["html_pages"]),
    "analyze_heading_structure": lambda args: heading_agent.execute(args["html"]),
    "analyze_readability": lambda args: readability_agent.execute(args["html"])
}

# Tool execution
def execute_ian_tool(tool_name, arguments):
    if tool_name in TOOL_DISPATCHER:
        # Calls the actual tool's execute function
        return TOOL_DISPATCHER[tool_name](arguments)
    return {"error": f"Tool '{tool_name}' not implemented in the dispatcher."}

test_html_page1 = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Corporate Dashboard - Home</title>
  <style>
    @keyframes flash { 50% { opacity: 0; } }
    .alert { animation: flash 1s infinite; color: red; font-weight: bold; }
  </style>
</head>
<body>

  <header>
    <h1>Synergistic Solutions Dashboard</h1>
    <nav>
      <a href="/home">Home</a>
      <a href="/reports">Reports</a>
      <a href="/settings">Settings</a>
    </nav>
  </header>

  <main>
    <div class="alert">URGENT: Paradigm shift required!</div>
    
    <video autoplay loop src="corporate_broll.mp4"></video>

    <!-- Missing headings, wall of text, corporate jargon -->
    <p>
      We need to boil the ocean and think outside the box to leverage our core competencies. 
      By synergizing our bandwidth, we can move the needle on our KPIs and achieve a win-win scenario.
      Please ensure all deliverables are aligned with our strategic vision before the end of play.
      The ROI on this initiative will be off the charts if we can just get all our ducks in a row.
      Let's touch base offline to discuss the low-hanging fruit and ensure we're comparing apples to apples.
      We must pivot our approach to maximize the bottom line and drive disruptive innovation.
    </p>
    
    <p>
      Please review the <abbr>Q3</abbr> <abbr>YTD</abbr> metrics and cross-reference with the <abbr>EBITDA</abbr> projections.
    </p>

  </main>

</body>
</html>
"""

test_html_page2 = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Corporate Dashboard - Reports</title>
</head>
<body>

  <header>
    <h1>Reports</h1>
  </header>

  <!-- Inconsistent navigation layout -->
  <main>
    <nav>
      <a href="/dashboard">Dashboard</a>
      <a href="/analytics">Analytics</a>
      <a href="/preferences">Preferences</a>
    </nav>

    <h2>Quarterly Review</h2>
    <p>Data goes here.</p>
  </main>

</body>
</html>
"""

messages = [
    {"role": "system", "content": IAN_SYSTEM_PROMPT},
    {"role": "user", "content": f"Evaluate these two HTML pages for consistency and accessibility:\n\nPage 1:\n{test_html_page1}\n\nPage 2:\n{test_html_page2}"}
]

print("=== IAN AGENT EVALUATION ===\n")

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
        print(f"Ian wants to call: {len(assistant_message.tool_calls)} tool(s)")
        messages.append(assistant_message) 
        
        for tool_call in assistant_message.tool_calls:
            tool_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)
            
            print(f"  → {tool_name}")
            
            result = execute_ian_tool(tool_name, arguments)
            
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id, # Link it to the specific request
                "name": tool_name,
                "content": json.dumps(result)
            })
    
    else:
        print(f"\nIan's Final Persona-Based Evaluation:")
        print("------------------------------------------")
        print(assistant_message.content)
        break
        
print("\n=== EVALUATION COMPLETE ===")
