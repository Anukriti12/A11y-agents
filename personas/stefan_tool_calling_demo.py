# stefan_tool_calling_demo.py

"""
Stefan agent evaluating HTML with autoplay video
Demonstrates persona-grounded agentic tool selection
"""

import openai
import os
import json

client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# Stefan's system prompt
STEFAN_PROMPT = """
You are Stefan, a 28-year-old with ADHD and dyslexia.

When motion appears on screen, your attention is immediately pulled away from what you're trying to read. Autoplay videos are particularly disruptive.

Your task: Evaluate HTML for accessibility from YOUR perspective.

Available tools:
- detect_animations: Finds videos, GIFs, CSS animations
- analyze_readability: Checks text complexity (you need Flesch > 60)

Output format: JSON with label, severity, issues
"""

# Stefan's tools
tools = [
    {
        "type": "function",
        "function": {
            "name": "detect_animations",
            "description": "Detects autoplay videos, GIFs, CSS animations that distract users with ADHD (WCAG 2.2.2). Returns count and types of animated elements.",
            "parameters": {
                "type": "object",
                "properties": {
                    "html": {"type": "string"}
                },
                "required": ["html"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_readability",
            "description": "Calculates Flesch reading ease. Stefan with dyslexia needs score > 60 for comfortable reading (WCAG 3.1.5).",
            "parameters": {
                "type": "object",
                "properties": {
                    "html": {"type": "string"}
                },
                "required": ["html"]
            }
        }
    }
]

# Tool execution
def execute_stefan_tool(tool_name, arguments):
    html = arguments["html"]
    
    if tool_name == "detect_animations":
        # Simplified - real version uses Playwright
        has_autoplay = "autoplay" in html.lower()
        return {
            "animation_count": 1 if has_autoplay else 0,
            "autoplay_videos": 1 if has_autoplay else 0,
            "css_animations": 0
        }
    
    elif tool_name == "analyze_readability":
        # Simplified - real version uses textstat
        word_count = len(html.split())
        return {
            "flesch_score": 45,  # Simulated
            "reading_level": "college",
            "complex_words": ["implementation", "synergistic"]
        }

# Test HTML
test_html = """
<video autoplay loop src="ad.mp4"></video>
<article>
  <h1>Welcome</h1>
  <p>Simple text here.</p>
</article>
"""

# Conversation
messages = [
    {"role": "system", "content": STEFAN_PROMPT},
    {"role": "user", "content": f"Evaluate this HTML:\n\n{test_html}"}
]

# Agentic loop
print("=== STEFAN AGENT EVALUATION ===\n")

for iteration in range(10):
    print(f"--- Iteration {iteration + 1} ---")
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        tools=tools,
        tool_choice="auto"
    )
    
    assistant_message = response.choices[0].message
    
    if assistant_message.tool_calls:
        print(f"Stefan wants to call: {len(assistant_message.tool_calls)} tool(s)")
        
        messages.append({
            "role": "assistant",
            "content": assistant_message.content,
            "tool_calls": assistant_message.tool_calls
        })
        
        for tool_call in assistant_message.tool_calls:
            tool_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)
            
            print(f"  → {tool_name}")
            
            result = execute_stefan_tool(tool_name, arguments)
            print(f"     Result: {result}")
            
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result)
            })
    
    else:
        print(f"\nStefan's evaluation:")
        print(assistant_message.content)
        break

print("\n=== DONE ===")
