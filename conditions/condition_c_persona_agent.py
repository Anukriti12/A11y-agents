"""
Condition C: Persona-Agent

Full persona-grounded agent with access to specialized accessibility tools.
This is the primary contribution of A11yAgents.

Thin wrapper around the persona agent classes from personas1/. The wrapper
exposes the uniform evaluate(html, persona) interface shared with Condition
A (Axe) and Condition B (Persona-LLM), so run_experiment.py can treat all
three conditions interchangeably.
"""

import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from personas.ade_agent import AdeAgent
from personas.elias_agent import EliasAgent
from personas.ian_agent import IanAgent
from personas.lakshmi_agent import LakshmiAgent
from personas.sophie_agent import SophieAgent
from personas.stefan_agent import StefanAgent


class PersonaAgentCondition:
    """Persona system prompt + specialized WCAG tools. Full A11yAgents."""

    def __init__(self, api_key):
        self.agents = {
            "ade": AdeAgent(api_key),
            "elias": EliasAgent(api_key),
            "ian": IanAgent(api_key),
            "lakshmi": LakshmiAgent(api_key),
            "sophie": SophieAgent(api_key),
            "stefan": StefanAgent(api_key),
        }

    def evaluate(self, html, persona):
        agent = self.agents[persona]
        result = agent.evaluate(html)
        # Persona agents already return {"evaluation": ..., "metadata": ...}
        # Add the persona label to metadata for downstream analysis.
        result.setdefault("metadata", {})["persona"] = persona
        return result


if __name__ == "__main__":
    import json
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or api_key == "smoke-test":
        print("Set OPENAI_API_KEY to run this test.")
    else:
        cond = PersonaAgentCondition(api_key)
        result = cond.evaluate(
            "<html><body><img src='x.jpg'><button></button></body></html>",
            persona="lakshmi",
        )
        print(json.dumps(result, indent=2, default=str))
