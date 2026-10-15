"""
The five conditions, re-posed as the barrier task.

These wrap the existing condition and persona-agent classes without editing
them: the agents are constructed exactly as in run_experiment.py, and only
the system prompt (and an html-injecting execute_tool) is replaced on each
instance. Tool sets, model settings and the agentic loop are unchanged, so
the WCAG-task and barrier-task runs differ only in the question asked.

  A  axe            axe-core violations on the persona's criteria -> Barrier,
                    none -> No-Barrier (axe cannot say Not-Encountered)
  B  persona_llm    barrier persona profile, no tools, one call
  C  persona_agent  barrier persona profile + that persona's original tools
  D  vanilla_llm    one-line user description, no tools, one call
  E  vanilla_agent  one-line user description + all 18 tools

Every condition returns {"evaluation": {...}, "metadata": {...}} where
evaluation["label"] is one of prompts.LABELS or "error".
"""

import os
import sys
import time
import types

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from barrier_task import prompts

DEFAULT_MODEL = "gpt-4o"
TEMPERATURE = 0
MAX_TOKENS = int(os.environ.get("A11Y_MAX_TOKENS", "4096"))


def _validate(parsed):
    """Coerce a parsed model answer into the barrier envelope."""
    if not isinstance(parsed, dict):
        return _error("Model output was not a JSON object")
    if parsed.get("label") == "error":
        return parsed
    label = str(parsed.get("label", "")).strip()
    # Tolerate case/spacing drift ("no barrier", "NOT_ENCOUNTERED").
    norm = {l.lower().replace("-", "").replace("_", "").replace(" ", ""): l for l in prompts.LABELS}
    key = label.lower().replace("-", "").replace("_", "").replace(" ", "")
    if key not in norm:
        return _error(f"Unrecognized label {label!r}", raw=str(parsed)[:500])
    parsed["label"] = norm[key]
    parsed.setdefault("severity", "N/A")
    parsed.setdefault("barriers", [])
    parsed.setdefault("confidence", "")
    parsed.setdefault("rationale", "")
    return parsed


def _error(msg, raw=None):
    env = {"label": "error", "severity": "N/A", "barriers": [],
           "confidence": "", "rationale": msg}
    if raw:
        env["raw_output"] = raw
    return env


def _parse_text(text):
    # Same lenient JSON extraction the persona agents use.
    from personas.base_agent import BaseAgenticAgent
    parsed = BaseAgenticAgent.parse_output(None, text)
    if parsed.get("label") == "error":
        parsed.setdefault("barriers", [])
        parsed.setdefault("rationale", parsed.get("overall_assessment", ""))
    return _validate(parsed)


def _injecting_execute_tool(original):
    """Wrap an agent's execute_tool so a missing html argument is filled in."""
    def execute_tool(self, tool_name, arguments):
        arguments = dict(arguments or {})
        if not arguments.get("html"):
            arguments["html"] = getattr(self, "_barrier_html", "")
        return original(tool_name, arguments)
    return execute_tool


def _retarget(agent, system_prompt):
    """Point an existing agent instance at the barrier task."""
    agent.get_system_prompt = lambda: system_prompt
    agent.parse_output = _parse_text
    agent.execute_tool = types.MethodType(_injecting_execute_tool(agent.execute_tool), agent)
    return agent


class _SingleCallCondition:
    """Shared body of the two no-tool conditions (B and D)."""

    variant = None

    def __init__(self, api_key, model=None):
        from llm_client1 import make_client
        self.model = model or os.environ.get("A11Y_MODEL") or DEFAULT_MODEL
        self.client = make_client(self.model, api_key)
        self.provider = self.client.provider

    def system_prompt(self, persona):
        raise NotImplementedError

    def evaluate(self, html, persona):
        start = time.time()
        md = {"tools_called": [], "iteration_count": 1, "persona": persona,
              "model": self.model, "provider": self.provider,
              "condition_variant": self.variant}
        try:
            response = self.client.chat(
                system=self.system_prompt(persona),
                messages=[{"role": "user", "content": prompts.user_message(html)}],
                tools=None,
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
            )
            evaluation = _parse_text(response["text"])
            md["usage"] = response.get("usage", {})
        except Exception as e:
            evaluation = _error(f"{self.variant} failed: {e}")
            md["error"] = str(e)
        md["total_time_seconds"] = round(time.time() - start, 2)
        return {"evaluation": evaluation, "metadata": md}


class BarrierPersonaLLM(_SingleCallCondition):
    variant = "barrier_persona_llm"

    def system_prompt(self, persona):
        return prompts.persona_system_prompt(persona, with_tools=False)


class BarrierVanillaLLM(_SingleCallCondition):
    variant = "barrier_vanilla_llm"

    def system_prompt(self, persona):
        return prompts.vanilla_system_prompt(persona, with_tools=False)


class BarrierPersonaAgent:
    """Persona agents from personas1/ with their own tools, barrier prompt."""

    def __init__(self, api_key, model=None):
        self.model = model or os.environ.get("A11Y_MODEL") or DEFAULT_MODEL
        os.environ["A11Y_MODEL"] = self.model
        from conditions.condition_c_persona_agent import PersonaAgentCondition
        self.agents = PersonaAgentCondition(api_key, model=self.model).agents
        for persona, agent in self.agents.items():
            _retarget(agent, prompts.persona_system_prompt(persona, with_tools=True))

    def evaluate(self, html, persona):
        agent = self.agents[persona]
        agent._barrier_html = html
        result = agent.evaluate(html)
        result["evaluation"] = _validate(result.get("evaluation"))
        md = result.setdefault("metadata", {})
        md.update(persona=persona, condition_variant="barrier_persona_agent")
        md.setdefault("model", self.model)
        return result


class BarrierVanillaAgent:
    """The 18-tool vanilla agent, barrier prompt with a one-line user description."""

    def __init__(self, api_key, model=None):
        self.model = model or os.environ.get("A11Y_MODEL") or DEFAULT_MODEL
        os.environ["A11Y_MODEL"] = self.model
        from conditions.condition_e_vanilla_agent import _VanillaAgent
        self.agent = _VanillaAgent(api_key)
        self.agent.parse_output = _parse_text

    def evaluate(self, html, persona):
        prompt = prompts.vanilla_system_prompt(persona, with_tools=True)
        self.agent.get_system_prompt = lambda: prompt
        # _VanillaAgent.evaluate already injects html into tool calls.
        result = self.agent.evaluate(html)
        result["evaluation"] = _validate(result.get("evaluation"))
        md = result.setdefault("metadata", {})
        md.update(persona=persona, condition_variant="barrier_vanilla_agent")
        md.setdefault("model", self.model)
        return result


class BarrierAxe:
    """axe-core, filtered to the persona's criteria as in the WCAG run."""

    def __init__(self):
        from conditions.condition_a_axe import AxeCondition
        self.axe = AxeCondition()

    def evaluate(self, html, persona):
        result = self.axe.evaluate(html, persona)
        ev = result.get("evaluation", {})
        wcag_label = ev.get("label")
        label = {"failed": "Barrier", "passed": "No-Barrier"}.get(wcag_label, "error")
        result["evaluation"] = {
            "label": label,
            "severity": "N/A",
            "barriers": [{"what_blocks": i.get("description", ""), "evidence": i.get("wcag", "")}
                         for i in ev.get("issues", [])],
            "confidence": "",
            "rationale": f"axe-core label {wcag_label!r} mapped to {label!r}",
            "axe_issues": ev.get("issues", []),
        }
        result.setdefault("metadata", {})["condition_variant"] = "barrier_axe"
        return result


CONDITIONS = {
    "A": ("axe", BarrierAxe),
    "B": ("persona_llm", BarrierPersonaLLM),
    "C": ("persona_agent", BarrierPersonaAgent),
    "D": ("vanilla_llm", BarrierVanillaLLM),
    "E": ("vanilla_agent", BarrierVanillaAgent),
}
