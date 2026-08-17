"""
Condition C: Persona-Agent

Full persona-grounded agent with access to specialized accessibility tools.
This is the primary contribution of AgentA11y.

Thin wrapper around the persona agent classes from personas1/. The wrapper
exposes the uniform evaluate(html, persona) interface shared with Condition
A (Axe) and Condition B (Persona-LLM), so run_experiment.py can treat all
three conditions interchangeably.

MULTI-MODEL VERSION. The persona classes themselves take only api_key, so
the model is communicated through the A11Y_MODEL environment variable, which
personas/base_agent.py reads inside __init__. This wrapper sets it before
constructing the agents, which means no edits are needed in any of the six
personas1/*_agent.py files.
"""

import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

DEFAULT_MODEL = "gpt-4o"


class PersonaAgentCondition:
    """Persona system prompt + specialized WCAG tools. Full AgentA11y."""

    def __init__(self, api_key, model=None):
        self.model = model or os.environ.get("A11Y_MODEL") or DEFAULT_MODEL
        # Must be set BEFORE the persona agents are constructed, since
        # BaseAgenticAgent.__init__ reads it to pick its provider adapter.
        os.environ["A11Y_MODEL"] = self.model

        from personas1.ade_agent import AdeAgent
        from personas1.elias_agent import EliasAgent
        from personas1.ian_agent import IanAgent
        from personas1.lakshmi_agent import LakshmiAgent
        from personas1.sophie_agent import SophieAgent
        from personas1.stefan_agent import StefanAgent

        self.agents = {
            "ade": AdeAgent(api_key),
            "elias": EliasAgent(api_key),
            "ian": IanAgent(api_key),
            "lakshmi": LakshmiAgent(api_key),
            "sophie": SophieAgent(api_key),
            "stefan": StefanAgent(api_key),
        }

        # Sanity check: every agent should have resolved to the same model.
        resolved = {a.model for a in self.agents.values()}
        if resolved != {self.model}:
            raise RuntimeError(
                f"Model mismatch across persona agents: {resolved}, "
                f"expected {self.model}. Check A11Y_MODEL handling."
            )

    def evaluate(self, html, persona):
        agent = self.agents[persona]
        result = agent.evaluate(html)
        # Persona agents already return {"evaluation": ..., "metadata": ...}
        # Add the persona label to metadata for downstream analysis.
        md = result.setdefault("metadata", {})
        md["persona"] = persona
        md.setdefault("model", self.model)
        return result


if __name__ == "__main__":
    import json
    from dotenv import load_dotenv
    from llm_client1 import key_env_var

    load_dotenv()
    model = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL
    api_key = os.environ.get(key_env_var(model))
    if not api_key or api_key == "smoke-test":
        print(f"Set {key_env_var(model)} to run this test.")
    else:
        cond = PersonaAgentCondition(api_key, model=model)
        result = cond.evaluate(
            "<html><body><img src='x.jpg'><button></button></body></html>",
            persona="lakshmi",
        )
        print(json.dumps(result, indent=2, default=str))
