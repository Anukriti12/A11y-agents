"""
The five conditions, re-posed as the barrier task (two labels).

  A  axe            any WCAG-tagged axe-core violation on the page -> Barrier,
                    none -> No-Barrier. Not filtered to the persona's WCAG
                    criteria (no condition is pointed at particular criteria);
                    axe's "best practice" rules are not counted.
  B  persona_llm    barrier persona profile, no tools, one call
  C  persona_agent  barrier persona profile + all 18 tools
  D  vanilla_llm    one-line user description, no tools, one call
  E  vanilla_agent  one-line user description + all 18 tools

C and E use the same agent (conditions/condition_e_vanilla_agent._VanillaAgent)
with the same 18 tools and differ only in the system prompt, so C vs E and
B vs D both isolate the persona description, and C vs B and E vs D isolate the
tools. C and E take tool_framing ("original" | "neutral" | "measurements"),
which controls how the tools are described and what tool outputs the model
sees; see barrier_task/tool_framing.py.

The existing condition and agent classes are not edited; only the system
prompt, the tool interface and the output parser are replaced on instances.

Every condition returns {"evaluation": {...}, "metadata": {...}} where
evaluation["label"] is "Barrier", "No-Barrier" or "error".
"""

import os
import sys
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from barrier_task import prompts, tool_framing

DEFAULT_MODEL = "gpt-4o"
TEMPERATURE = 0
MAX_TOKENS = int(os.environ.get("A11Y_MAX_TOKENS", "4096"))


def _key(label):
    return str(label).lower().replace("-", "").replace("_", "").replace(" ", "")


def _validate(parsed):
    """Coerce a parsed model answer into the two-label barrier envelope."""
    if not isinstance(parsed, dict):
        return _error("Model output was not a JSON object")
    if parsed.get("label") == "error":
        return parsed
    raw_label = str(parsed.get("label", "")).strip()
    key = _key(raw_label)
    if key == "barrier":
        label = "Barrier"
    elif key in ("nobarrier", "notencountered"):
        # A model that still answers Not-Encountered is not reporting a barrier.
        label = "No-Barrier"
    else:
        return _error(f"Unrecognized label {raw_label!r}", raw=str(parsed)[:500])
    if label != raw_label:
        parsed["label_as_returned"] = raw_label
    parsed["label"] = label
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


class _AllToolsAgentCondition:
    """An 18-tool agent whose system prompt is chosen per persona."""

    variant = None

    def __init__(self, api_key, model=None, tool_framing_arm="original"):
        self.model = model or os.environ.get("A11Y_MODEL") or DEFAULT_MODEL
        self.tool_framing = tool_framing_arm
        os.environ["A11Y_MODEL"] = self.model
        from conditions.condition_e_vanilla_agent import _VanillaAgent
        self.agent = _VanillaAgent(api_key)
        if self.agent.model != self.model:
            raise RuntimeError(f"Model mismatch: agent resolved {self.agent.model!r}, expected {self.model!r}.")
        self.agent.parse_output = _parse_text
        # _VanillaAgent.execute_tool already fills in a missing html argument.
        tool_framing.apply(self.agent, tool_framing_arm)

    def system_prompt(self, persona):
        raise NotImplementedError

    def evaluate(self, html, persona):
        prompt = self.system_prompt(persona)
        self.agent.get_system_prompt = lambda: prompt
        result = self.agent.evaluate(html)
        result["evaluation"] = _validate(result.get("evaluation"))
        md = result.setdefault("metadata", {})
        md.update(persona=persona, condition_variant=self.variant,
                  tool_framing=self.tool_framing)
        md.setdefault("model", self.model)
        return result


class BarrierPersonaAgent(_AllToolsAgentCondition):
    variant = "barrier_persona_agent"

    def system_prompt(self, persona):
        return prompts.persona_system_prompt(persona, with_tools=True)


class BarrierVanillaAgent(_AllToolsAgentCondition):
    variant = "barrier_vanilla_agent"

    def system_prompt(self, persona):
        return prompts.vanilla_system_prompt(persona, with_tools=True)


def _is_wcag_violation(issue):
    """True for an axe issue tagged with a WCAG success criterion."""
    wcag = str(issue.get("wcag", "")).lower()
    return wcag not in ("", "best practice", "unknown")


class BarrierAxe:
    """axe-core on the whole page: any violation counts as a barrier."""

    def __init__(self):
        from conditions.condition_a_axe import AxeCondition
        self.axe = AxeCondition()

    def evaluate(self, html, persona):
        result = self.axe.evaluate(html, persona)
        ev = result.get("evaluation", {})
        if ev.get("label") == "error":
            label, issues = "error", []
        else:
            # all_issues = every violation axe reported, before the
            # persona-criteria filter the WCAG-task condition applies. Only
            # WCAG-tagged violations count: axe's "best practice" rules
            # (landmarks, region) fire on almost every page fragment.
            issues = [i for i in ev.get("all_issues", ev.get("issues", []))
                      if _is_wcag_violation(i)]
            label = "Barrier" if issues else "No-Barrier"
        result["evaluation"] = {
            "label": label,
            "severity": "N/A",
            "barriers": [{"what_blocks": i.get("description", ""), "evidence": i.get("wcag", "")}
                         for i in issues],
            "confidence": "",
            "rationale": f"{len(issues)} axe-core violation(s) on the page",
            "axe_issues": issues,
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
