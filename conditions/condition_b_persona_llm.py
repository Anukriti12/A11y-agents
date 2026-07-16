"""
Condition B: Persona-LLM

Same persona system prompt as Condition C (Persona-Agent), but WITHOUT
tool access. The LLM reasons about the HTML directly using its training
knowledge. This is the ablation that isolates the contribution of the
specialized accessibility tools.

Design:
    We instantiate the persona agent classes just to reuse their
    get_system_prompt() output. Then we make a single LLM call with
    tools disabled, appending an override that tells the LLM to ignore
    the tool references and reason from the HTML directly.

    This guarantees Condition B and Condition C share the SAME persona
    grounding, so any difference in verdicts is attributable to tool
    access, not prompt differences.
"""

import json
import os
import sys
import time
import openai

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from personas1.ade_agent import AdeAgent
from personas1.elias_agent import EliasAgent
from personas1.ian_agent import IanAgent
from personas1.lakshmi_agent import LakshmiAgent
from personas1.sophie_agent import SophieAgent
from personas1.stefan_agent import StefanAgent


# Override appended to each persona's system prompt to disable tools for
# this condition. The LLM must reason from the HTML directly.
NO_TOOLS_OVERRIDE = """

======================================================================
IMPORTANT: CONDITION B OVERRIDE
======================================================================
For THIS evaluation you have NO TOOLS AVAILABLE.

Disregard every instruction above about calling tools, iterating on
tool output, or "tool: <name>". Those instructions do not apply here.

Instead, evaluate the HTML directly using your training knowledge.
For each of the five WCAG criteria in your matrix:
  1. Examine the HTML for signals that would indicate pass, fail, or
     inapplicable for that criterion.
  2. Cite specific HTML fragments (element, attribute values, or text
     content) as evidence in the "evidence" field of each issue.
  3. Apply your persona's lived perspective when interpreting severity.

Return your verdict in the SAME JSON format specified above. Return
ONLY the JSON object, no markdown fences, no preamble.
======================================================================
"""


class PersonaLLMCondition:
    """Persona system prompt, no tool access. GPT-4o direct call."""

    MODEL = "gpt-4o"
    TEMPERATURE = 0
    SEED = 42

    def __init__(self, api_key):
        self.client = openai.OpenAI(api_key=api_key)
        # Instantiate agents only to reuse their system prompts.
        # We never call their evaluate() method in this condition.
        self.persona_agents = {
            "ade": AdeAgent(api_key),
            "elias": EliasAgent(api_key),
            "ian": IanAgent(api_key),
            "lakshmi": LakshmiAgent(api_key),
            "sophie": SophieAgent(api_key),
            "stefan": StefanAgent(api_key),
        }

    def evaluate(self, html, persona):
        start = time.time()
        try:
            agent = self.persona_agents[persona]
            system_prompt = agent.get_system_prompt() + NO_TOOLS_OVERRIDE

            response = self.client.chat.completions.create(
                model=self.MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Evaluate this HTML:\n\n{html}"},
                ],
                temperature=self.TEMPERATURE,
                seed=self.SEED,
                # No tools parameter; the LLM cannot call anything.
            )

            evaluation = self._parse(response.choices[0].message.content)

            return {
                "evaluation": evaluation,
                "metadata": {
                    "tools_called": [],
                    "iteration_count": 1,
                    "total_time_seconds": round(time.time() - start, 2),
                    "persona": persona,
                    "model": self.MODEL,
                },
            }
        except Exception as e:
            return {
                "evaluation": {
                    "label": "error",
                    "severity": "N/A",
                    "issues": [],
                    "overall_assessment": f"Persona-LLM failed: {e}",
                },
                "metadata": {
                    "tools_called": [],
                    "iteration_count": 1,
                    "total_time_seconds": round(time.time() - start, 2),
                    "persona": persona,
                    "error": str(e),
                },
            }

    def _parse(self, text):
        if not text:
            return self._error_envelope("Empty LLM response")
        clean = text.strip()
        if "```json" in clean:
            clean = clean.split("```json", 1)[1].split("```", 1)[0]
        elif "```" in clean:
            clean = clean.split("```", 1)[1].split("```", 1)[0]
        if "{" in clean and "}" in clean:
            clean = clean[clean.index("{"):clean.rindex("}") + 1]
        try:
            parsed = json.loads(clean.strip())
            for field in ("label", "severity", "issues", "overall_assessment"):
                if field not in parsed:
                    return self._error_envelope(f"Missing field: {field}", text)
            return parsed
        except json.JSONDecodeError as e:
            return self._error_envelope(f"Parse error: {e}", text)

    def _error_envelope(self, msg, raw=None):
        env = {
            "label": "error",
            "severity": "N/A",
            "issues": [],
            "overall_assessment": msg,
        }
        if raw:
            env["raw_output"] = raw[:500]
        return env


if __name__ == "__main__":
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or api_key == "smoke-test":
        print("Set OPENAI_API_KEY to run this test.")
    else:
        cond = PersonaLLMCondition(api_key)
        result = cond.evaluate(
            "<html><body><img src='x.jpg'><button></button></body></html>",
            persona="lakshmi",
        )
        print(json.dumps(result, indent=2))
