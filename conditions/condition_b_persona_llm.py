"""
Condition B: Persona-LLM

Same persona system prompt as Condition C (Persona-Agent), but WITHOUT
tool access. The LLM reasons about the HTML directly using its training
knowledge. This is the ablation that isolates the contribution of the
specialized accessibility tools.

MULTI-MODEL VERSION. Routes through llm_client.make_client() so the same
condition runs on gpt-4o, claude-sonnet-4-6, and claude-opus-4-8.

Design:
    We instantiate the persona agent classes just to reuse their
    get_system_prompt() output. Then we make a single LLM call with
    tools disabled, appending an override that tells the LLM to ignore
    the tool references and reason from the HTML directly.

    This guarantees Condition B and Condition C share the SAME persona
    grounding, so any difference in verdicts is attributable to tool
    access, not prompt differences.

    The persona agents constructed here also build their own LLM clients
    (unused in this condition), so they are given the same model to avoid
    a spurious second provider handshake.
"""

import json
import os
import sys
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from llm_client import make_client

from personas1.ade_agent import AdeAgent
from personas1.elias_agent import EliasAgent
from personas1.ian_agent import IanAgent
from personas1.lakshmi_agent import LakshmiAgent
from personas1.sophie_agent import SophieAgent
from personas1.stefan_agent import StefanAgent


DEFAULT_MODEL = "gpt-4o"


# Override appended to each persona's system prompt to disable tools for
# this condition. The LLM must reason from the HTML directly.
NO_TOOLS_OVERRIDE = """

======================================================================
IMPORTANT: CONDITION B OVERRIDE
======================================================================
For THIS evaluation you have NO TOOLS AVAILABLE.

Disregard every instruction above about calling tools, iterating on
tool output, or "tool: <n>". Those instructions do not apply here.

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
    """Persona system prompt, no tool access. Single direct model call."""

    TEMPERATURE = 0
    MAX_TOKENS = int(os.environ.get("A11Y_MAX_TOKENS", "4096"))

    def __init__(self, api_key, model=None):
        self.model = model or os.environ.get("A11Y_MODEL") or DEFAULT_MODEL
        self.client = make_client(self.model, api_key)
        self.provider = self.client.provider

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

            response = self.client.chat(
                system=system_prompt,
                messages=[
                    {"role": "user", "content": f"Evaluate this HTML:\n\n{html}"},
                ],
                tools=None,  # the LLM cannot call anything in this condition
                temperature=self.TEMPERATURE,
                max_tokens=self.MAX_TOKENS,
            )

            evaluation = self._parse(response["text"])

            return {
                "evaluation": evaluation,
                "metadata": {
                    "tools_called": [],
                    "iteration_count": 1,
                    "total_time_seconds": round(time.time() - start, 2),
                    "persona": persona,
                    "model": self.model,
                    "provider": self.provider,
                    "usage": response.get("usage", {}),
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
                    "model": self.model,
                    "provider": getattr(self, "provider", None),
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
    from dotenv import load_dotenv
    from llm_client import key_env_var

    load_dotenv()
    model = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL
    os.environ["A11Y_MODEL"] = model

    api_key = os.environ.get(key_env_var(model))
    if not api_key or api_key == "smoke-test":
        print(f"Set {key_env_var(model)} to run this test.")
    else:
        cond = PersonaLLMCondition(api_key, model=model)
        result = cond.evaluate(
            "<html><body><img src='x.jpg'><button></button></body></html>",
            persona="lakshmi",
        )
        print(json.dumps(result, indent=2))
