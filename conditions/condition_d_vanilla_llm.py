"""
Condition D: Vanilla-LLM

Generic accessibility-expert LLM evaluation. Same 5 WCAG criteria that the
persona-based conditions would evaluate, but WITHOUT the persona backstory,
user story, or disability profile framing.

This is the ablation Lucy asked for. It isolates persona framing from
criterion selection:

  Condition B (Persona-LLM):  persona backstory  + 5 criteria + no tools
  Condition D (Vanilla-LLM):  NO persona         + 5 criteria + no tools

The delta between B and D measures the contribution of persona framing.

Same public interface (evaluate(html, persona)) so run_experiment.py can
treat all conditions interchangeably. The `persona` argument is used ONLY
to look up which 5 WCAG criteria to evaluate. The LLM never sees any
persona reference.
"""

import json
import os
import sys
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from llm_client import make_client


DEFAULT_MODEL = "gpt-4o"


# The same 5 WCAG criteria each persona targets, but stripped of persona
# framing. Sourced from personas1/*_agent.py criterion assignments.
PERSONA_CRITERIA = {
    "ade":     ["2.1.1", "2.2.1", "2.4.3", "2.4.7", "2.5.5"],
    "elias":   ["1.3.5", "1.4.3", "1.4.12", "2.2.2", "2.4.8"],
    "ian":     ["1.3.1", "2.2.2", "2.4.6", "3.1.4", "3.1.5"],
    "lakshmi": ["1.1.1", "1.3.1", "2.1.1", "2.4.1", "4.1.2"],
    "sophie":  ["2.2.1", "2.4.8", "3.1.4", "3.3.1", "3.3.2"],
    "stefan":  ["1.4.12", "2.2.2", "2.4.5", "2.4.6", "3.1.4"],
}


# One-line title for each WCAG criterion (from WCAG 2.1 spec).
WCAG_TITLES = {
    "1.1.1":  "Non-text Content (Level A)",
    "1.3.1":  "Info and Relationships (Level A)",
    "1.3.5":  "Identify Input Purpose (Level AA)",
    "1.4.3":  "Contrast Minimum (Level AA)",
    "1.4.12": "Text Spacing (Level AA)",
    "2.1.1":  "Keyboard (Level A)",
    "2.2.1":  "Timing Adjustable (Level A)",
    "2.2.2":  "Pause, Stop, Hide (Level A)",
    "2.4.1":  "Bypass Blocks (Level A)",
    "2.4.3":  "Focus Order (Level A)",
    "2.4.5":  "Multiple Ways (Level AA)",
    "2.4.6":  "Headings and Labels (Level AA)",
    "2.4.7":  "Focus Visible (Level AA)",
    "2.4.8":  "Location (Level AAA)",
    "2.5.5":  "Target Size (Level AAA)",
    "3.1.4":  "Abbreviations (Level AAA)",
    "3.1.5":  "Reading Level (Level AAA)",
    "3.3.1":  "Error Identification (Level A)",
    "3.3.2":  "Labels or Instructions (Level A)",
    "4.1.2":  "Name, Role, Value (Level A)",
}


def build_vanilla_system_prompt(criteria):
    """
    Compose the vanilla accessibility-expert system prompt for the given
    criterion list. No persona backstory, no user story, no disability
    profile. Generic accessibility-engineer voice.
    """
    criteria_lines = "\n".join(
        f"  - WCAG {c} {WCAG_TITLES.get(c, '')}" for c in criteria
    )
    return f"""You are an accessibility expert evaluating a web page against a specific set of WCAG 2.1 success criteria.

Your task: examine the HTML and produce a single verdict for the page against these criteria:
{criteria_lines}

For each criterion, decide whether the page:
  - "passed" — the page complies with the criterion
  - "failed" — the page violates the criterion
  - "inapplicable" — the criterion does not apply to this page (e.g., no images means 1.1.1 is inapplicable; no forms means 3.3.1 is inapplicable)

Base your reasoning on the HTML source. Cite specific HTML fragments (elements, attributes, or text content) as evidence. Refer to WCAG techniques where relevant (e.g., H98 for input purpose, G18 for contrast).

Return a single JSON object with these fields:
{{
  "label": "passed" | "failed" | "inapplicable",
  "severity": "critical" | "serious" | "moderate" | "minor" | "N/A",
  "issues": [
    {{
      "wcag": "<criterion number>",
      "description": "<short description of the issue>",
      "evidence": "<specific HTML fragment showing the issue>",
      "recommendation": "<how to fix>"
    }},
    ...
  ],
  "overall_assessment": "<one-paragraph summary of the verdict and reasoning>"
}}

The "label" field should be the overall verdict for the criterion being evaluated (each snippet targets ONE criterion). If any issue in the "issues" list violates the target criterion, label is "failed." If no issues apply and the elements the criterion targets are absent, label is "inapplicable." Otherwise, "passed."

Return ONLY the JSON object. No markdown fences. No preamble.
"""


class VanillaLLMCondition:
    """Generic accessibility-expert LLM prompt. No persona. No tools."""

    TEMPERATURE = 0
    MAX_TOKENS = int(os.environ.get("A11Y_MAX_TOKENS", "4096"))

    def __init__(self, api_key, model=None):
        self.model = model or os.environ.get("A11Y_MODEL") or DEFAULT_MODEL
        self.client = make_client(self.model, api_key)
        self.provider = self.client.provider

    def evaluate(self, html, persona):
        """
        Evaluate the HTML against the 5 WCAG criteria that this persona
        would have targeted. The LLM sees the criterion list but not the
        persona backstory.
        """
        start = time.time()
        try:
            criteria = PERSONA_CRITERIA.get(persona, [])
            if not criteria:
                raise ValueError(
                    f"Unknown persona '{persona}'. "
                    f"Known: {sorted(PERSONA_CRITERIA)}"
                )

            system_prompt = build_vanilla_system_prompt(criteria)

            response = self.client.chat(
                system=system_prompt,
                messages=[
                    {"role": "user", "content": f"Evaluate this HTML:\n\n{html}"},
                ],
                tools=None,
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
                    "criteria_evaluated": criteria,
                    "model": self.model,
                    "provider": self.provider,
                    "usage": response.get("usage", {}),
                    "condition_variant": "vanilla_llm",
                },
            }
        except Exception as e:
            return {
                "evaluation": {
                    "label": "error",
                    "severity": "N/A",
                    "issues": [],
                    "overall_assessment": f"Vanilla-LLM failed: {e}",
                },
                "metadata": {
                    "tools_called": [],
                    "iteration_count": 1,
                    "total_time_seconds": round(time.time() - start, 2),
                    "persona": persona,
                    "model": self.model,
                    "provider": getattr(self, "provider", None),
                    "error": str(e),
                    "condition_variant": "vanilla_llm",
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
        cond = VanillaLLMCondition(api_key, model=model)
        result = cond.evaluate(
            "<html><body><img src='x.jpg'><button></button></body></html>",
            persona="lakshmi",
        )
        print(json.dumps(result, indent=2))
