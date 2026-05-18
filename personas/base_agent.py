"""
Base class for all persona agents
Provides common agentic loop logic
"""

import openai
import json
import time

class BaseAgenticAgent:
    def __init__(self, api_key, persona_name):
        self.client = openai.OpenAI(api_key=api_key)
        self.persona_name = persona_name
        self.tools_called = []
        self.iteration_count = 0
    
    def evaluate(self, html):
        """
        Main evaluation method - calls tools iteratively until LLM concludes
        
        Args:
            html: HTML string to evaluate
            
        Returns:
            {
                "evaluation": {...},
                "metadata": {
                    "tools_called": [...],
                    "iteration_count": N
                }
            }
        """
        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": f"Evaluate this HTML:\n\n{html}"}
        ]
        
        self.tools_called = []
        self.iteration_count = 0
        start_time = time.time()
        
        for iteration in range(10):  # Max 10 iterations
            self.iteration_count = iteration + 1
            
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                tools=self.get_tools(),
                tool_choice="auto",
                temperature=0,
                seed=42
            )
            
            assistant_message = response.choices[0].message
            
            if assistant_message.tool_calls:
                # LLM wants to call tools
                messages.append(assistant_message)
                
                for tool_call in assistant_message.tool_calls:
                    tool_name = tool_call.function.name
                    self.tools_called.append(tool_name)
                    
                    arguments = json.loads(tool_call.function.arguments)
                    result = self.execute_tool(tool_name, arguments)
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": json.dumps(result)
                    })
            else:
                # LLM has final answer
                elapsed = time.time() - start_time
                
                return {
                    "evaluation": self.parse_output(assistant_message.content),
                    "metadata": {
                        "tools_called": self.tools_called,
                        "iteration_count": self.iteration_count,
                        "total_time_seconds": round(elapsed, 2)
                    }
                }
        
        raise Exception(f"{self.persona_name} agent exceeded max iterations (10)")
    
    def get_system_prompt(self):
        """Override in subclass - return persona-specific prompt"""
        raise NotImplementedError
    
    def get_tools(self):
        """Override in subclass - return list of tool definitions"""
        raise NotImplementedError
    
    def execute_tool(self, tool_name, arguments):
        """Override in subclass - route tool calls to actual implementations"""
        raise NotImplementedError
    
    def parse_output(self, text):
        """Parse LLM's final JSON output"""
        clean = text.strip()
        
        # Remove markdown fences
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0]
        elif "```" in clean:
            clean = clean.split("```")[1].split("```")[0]
        
        # Try to extract JSON if surrounded by text
        if '{' in clean and '}' in clean:
            start = clean.index('{')
            end = clean.rindex('}') + 1
            clean = clean[start:end]
        
        try:
            return json.loads(clean.strip())
        except json.JSONDecodeError as e:
            # LLM didn't return valid JSON
            return {
                "label": "error",
                "severity": "N/A",
                "issues": [],
                "overall_assessment": f"Parse error: {str(e)}",
                "raw_output": text[:500]
            }