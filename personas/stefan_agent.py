
"""
Stefan agent evaluating HTML
"""

import openai
import os
import json
from dotenv import load_dotenv
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools import readability_analyzer_agent 
from tools import animation_detector_agent 
from tools import heading_structure_agent 
from tools import text_formatting_agent
from tools import multiple_ways_checker_agent

load_dotenv()

client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# Stefan's system prompt
STEFAN_PROMPT = """

You are Stefan, a student with dyslexia and attention deficit hyperactivity disorder (ADHD).
You struggle to stay focused on many tasks, like reading dense texts and inconsistent layouts. 
You use text-to-speech software to aid your understanding of complex text. When motion appears
on screen, your attention is immediately pulled away from what you're trying to read. Autoplay
videos are particularly disruptive.

Your task: Evaluate HTML for accessibility from YOUR perspective.

Available tools:
- analyze_readability: Checks text complexity (you need Flesch > 60)
- animation_detector_agent: Finds videos, GIFs, CSS animations and ways to stop, pause, or hide them.
- heading_structure_agent: Validates heading structure for navigation and comprehension.
- text_formatting_agent: Checks for proper HTML structure the structure and formatting of text content even with CSS changes
- multiple_ways_checker_agent: Checks for at least 2 ways to navigate the website

Output format: JSON with label, severity, issues
"""

# Stefan's tools
tools = [
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
            "name": "detect_animations",
            "description": "Detects autoplay videos, GIFs, CSS animations that distract users with ADHD (WCAG 2.2.2). Returns count and types of animated elements.",
            "parameters": {
                "type": "object",
                "properties": {
                    "html": {
                        "type": "string",
                        "description": "The full HTML source code to detect autoplayed video, GIF, or other animations that can't be paused, stopped, or hidden."
                    }
                },
                "required": ["html"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_heading_structure",
            "description": "Validates the hierarchical organization of headings (H1-H6). Ensures that the structure is logical and sequential to facilitate efficient navigation and clear comprehension for screen reader users.",
            "parameters": {
                "type": "object",
                "properties": {
                    "html": {
                        "type": "string",
                        "description": "The HTML source code of the page to evaluate for heading consistency and hierarchy."
                    }
                },
                "required": ["html"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_text_formatting",
            "description": "Examines the HTML structure and formatting of text content to ensure it remains accessible and semantically correct, even when visual styling is altered or disabled via CSS.",
            "parameters": {
                "type": "object",
                "properties": {
                    "html": {
                        "type": "string",
                        "description": "The HTML source code to be checked for semantic text formatting."
                    }
                },
                "required": ["html"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_multiple_ways",
            "description": "Verifies that there are at least two distinct methods available to locate a specific webpage within a set of pages (e.g., a search feature combined with a site map or navigation menu).",
            "parameters": {
                "type": "object",
                "properties": {
                    "html": {
                        "type": "string",
                        "description": "The HTML source code to be checked for multiple navigation ways."
                    }
                },
                "required": ["html"]
            }
        }
    }
]

# The tool agents instantiated
readability_agent = readability_analyzer_agent.ReadabilityAnalyzerAgent()
heading_agent = heading_structure_agent.HeadingStructureAgent()
text_format_agent = text_formatting_agent.TextFormattingAgent()
multiple_ways_checker_agent = multiple_ways_checker_agent.MultipleWaysCheckerAgent()
animation_detector_agent = animation_detector_agent.AnimationDetectorAgent()


TOOL_DISPATCHER = {
    "analyze_readability": readability_agent.execute,
    "detect_animations": animation_detector_agent.execute,
    "check_heading_structure": heading_agent.execute,
    "check_multiple_ways": multiple_ways_checker_agent.execute,
    "check_text_formatting": text_format_agent.execute
}

# Tool execution
def execute_stefan_tool(tool_name, arguments):
    html = arguments.get("html") or arguments.get("html_content") or arguments.get("content") or next(iter(arguments.values()), None)
    
    if tool_name in TOOL_DISPATCHER:
        # Calls the actual tool's execute function
        return TOOL_DISPATCHER[tool_name](html=html)
    return {"error": f"Tool '{tool_name}' not implemented in the dispatcher."} # Error handling

test_html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="UTF-8">
    <title>UW - CSE 311: Course Dashboard</title>
    <style>
        /* This flashing alert is a nightmare for my focus */
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
            <li><a href="/resources">Click Here</a></li> </ul>
        </nav>
    </header>

    <main>
        <section>
        <h6>Assignment Instructions</h6> <p>
            The pedagogical objectives of this particular problem set necessitate a 
            comprehensive understanding of Boolean algebraic structures and the 
            application of De Morgan's Laws within a constrained propositional logic 
            framework. Students must ensure that their formalized proofs adhere to 
            the rigorous syntactic requirements stipulated in the departmental handbook.
        </p>
        
        <form id="hw-upload">
            <h3>Submit Your Work</h3>
            
            <label for="student_id">Student ID:</label>
            <input type="text" id="student_id" name="sid"> <label for="email">University Email:</label>
            <input type="text" id="email" name="u_email"> <button type="submit">Submit</button>
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

messages = [
    {"role": "system", "content": STEFAN_PROMPT},
    {"role": "user", "content": f"Evaluate this HTML:\n\n{test_html}"}
]

print("=== STEFAN AGENT EVALUATION ===\n")

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
            
            result = execute_stefan_tool(tool_name, arguments)
            
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id, # Link it to the specific request
                "name": tool_name,
                "content": json.dumps(result)
            })
    
    else:
        print(f"\nStefan's Final Persona-Based Evaluation:")
        print("------------------------------------------")
        print(assistant_message.content)
        break
print("\n=== EVALUATION COMPLETE ===")