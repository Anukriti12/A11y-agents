

"""
Simplest possible agentic system
A chatbot that can check weather
"""

import openai
import os
import json

client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# STEP 1: Define available tools
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a city. Use this when user asks about temperature, conditions, or weather.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "City name, e.g. Seattle, Tokyo"
                    }
                },
                "required": ["city"]
            }
        }
    }
]

# STEP 2: Define tool execution
def execute_tool(tool_name, arguments):
    """Execute the requested tool"""
    if tool_name == "get_weather":
        city = arguments["city"]
        # Fake weather data (in real life, call weather API)
        return {
            "city": city,
            "temperature": 72,
            "condition": "sunny"
        }
    else:
        raise ValueError(f"Unknown tool: {tool_name}")

# STEP 3: Conversation
messages = [
    {"role": "user", "content": "What's the weather in Seattle?"}
]

# STEP 4: Agentic loop
print("=== AGENTIC LOOP ===\n")

for iteration in range(5):  # Max 5 iterations
    print(f"--- Iteration {iteration + 1} ---")
    
    # Call LLM
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        tools=tools,
        tool_choice="auto"
    )
    
    assistant_message = response.choices[0].message
    
    # Check if LLM wants to call a tool
    if assistant_message.tool_calls:
        print(f"LLM requested: {len(assistant_message.tool_calls)} tool(s)")
        
        # Add LLM's response to conversation
        messages.append({
            "role": "assistant",
            "content": assistant_message.content,
            "tool_calls": assistant_message.tool_calls
        })
        
        # Execute each requested tool
        for tool_call in assistant_message.tool_calls:
            tool_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)
            
            print(f"  Calling: {tool_name}({arguments})")
            
            # Execute
            result = execute_tool(tool_name, arguments)
            print(f"  Result: {result}")
            
            # Send result back to LLM
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result)
            })
    
    else:
        # LLM is done, has final answer
        print(f"LLM final answer: {assistant_message.content}")
        break

print("\n=== DONE ===")
