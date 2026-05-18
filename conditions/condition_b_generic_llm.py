"""
Condition B: Generic LLM Baseline
gpt-4o with no persona, no tools
"""

import os
import json
import time
import openai
from dotenv import load_dotenv

load_dotenv()

GENERIC_PROMPT = """
You are an expert accessibility evaluator with deep knowledge of WCAG 2.1 Level AA.

Evaluate the HTML for accessibility. Consider impacts on users with:
- Visual disabilities (blindness, low vision)
- Motor disabilities (keyboard-only, limited dexterity)
- Cognitive disabilities (ADHD, dyslexia, IDD, autism)
- Hearing disabilities

Check for: missing alt text, poor contrast, missing labels, keyboard issues, heading hierarchy, 
ARIA errors, time limits, tiny targets, complex language, inconsistent navigation.

Output ONLY valid JSON (no preamble, no markdown):
{
  "label": "passed" | "failed" | "inapplicable",
  "severity": "critical" | "serious" | "moderate" | "minor" | "N/A",
  "issues": [
    {
      "wcag": "X.X.X",
      "description": "What's wrong",
      "evidence": "What you found",
      "recommendation": "How to fix",
      "affected_users": "Which disability groups"
    }
  ],
  "overall_assessment": "Brief summary"
}
"""


class GenericLLMBaseline:
    def __init__(self, api_key: str):
        self.client = openai.OpenAI(api_key=api_key)
    
    def evaluate(self, html: str) -> dict:
        start_time = time.time()
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": GENERIC_PROMPT},
                    {"role": "user", "content": f"Evaluate this HTML:\n\n{html}"}
                ],
                temperature=0
            )
            
            output_text = response.choices[0].message.content
            evaluation = self._parse_llm_output(output_text)
            
            elapsed = time.time() - start_time
            metadata = {
                "tools_called": [],
                "iteration_count": 1,
                "total_time_seconds": round(elapsed, 2)
            }
            
            return {"evaluation": evaluation, "metadata": metadata}
            
        except Exception as e:
            return {
                "evaluation": {
                    "label": "error",
                    "severity": "N/A",
                    "issues": [],
                    "overall_assessment": f"LLM evaluation failed: {str(e)}"
                },
                "metadata": {
                    "tools_called": [],
                    "iteration_count": 1,
                    "total_time_seconds": 0,
                    "error": str(e)
                }
            }
    
    def _parse_llm_output(self, text: str) -> dict:
        clean = text.strip()
        
        # Extract JSON from surrounding text
        if '{' in clean and '}' in clean:
            start = clean.index('{')
            end = clean.rindex('}') + 1
            clean = clean[start:end]
        
        # Remove markdown fences
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0]
        elif "```" in clean:
            clean = clean.split("```")[1].split("```")[0]
        
        try:
            evaluation = json.loads(clean.strip())
            
            # Validate required fields
            required = ["label", "severity", "issues", "overall_assessment"]
            for field in required:
                if field not in evaluation:
                    raise ValueError(f"Missing field: {field}")
            
            return evaluation
            
        except (json.JSONDecodeError, ValueError) as e:
            return {
                "label": "error",
                "severity": "N/A",
                "issues": [],
                "overall_assessment": f"Parse error: {str(e)}",
                "raw_output": text[:500]
            }


if __name__ == "__main__":
    import json
    
    baseline = GenericLLMBaseline(os.environ["OPENAI_API_KEY"])
    
    html_bad = """
    <html><body>
        <img src="test.jpg">
        <form>
            <input type="text" name="email" placeholder="Email">
        </form>
    </body></html>
    """
    
    result = baseline.evaluate(html_bad)
    
    print("=== CONDITION B TEST ===")
    print(json.dumps(result, indent=2))
    
    assert result['evaluation']['label'] in ['failed', 'error']
    print("\n✓ TEST PASSED")