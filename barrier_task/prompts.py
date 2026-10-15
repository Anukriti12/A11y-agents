"""
Prompts for the barrier task.

The WCAG task asked "does this page pass/fail/not apply to criterion X?".
The barrier task asks the question the specialists answered: "is this page
a barrier for this person?", with the same three labels and definitions as
barrier_study/MASTER_INSTRUCTIONS.md.

Persona conditions (B, C) get the barrier-first persona profile and task
question from barrier_study/persona_prompts/<persona>_profile.py, i.e. the
same description the annotators worked from.

Vanilla conditions (D, E) get only a one-line description of the user
(PERSON_DESCRIPTORS). So B vs D is "rich persona vs. minimal user
description", not "persona vs. nothing": without naming a user, the barrier
question cannot be asked at all.

Neither condition sees WCAG criteria, the barrier checklist, or the WCAG
label.
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = ROOT / "barrier_study" / "persona_prompts"

PERSONAS = ["ade", "elias", "ian", "lakshmi", "sophie", "stefan"]

LABELS = ("Barrier", "No-Barrier", "Not-Encountered")

PERSON_DESCRIPTORS = {
    "ade":     "a keyboard-only user with limited mobility who cannot use a mouse",
    "elias":   "a user with low vision and a hand tremor",
    "ian":     "an autistic user",
    "lakshmi": "a blind user who uses the NVDA screen reader",
    "sophie":  "a user with Down syndrome",
    "stefan":  "a user with ADHD and dyslexia",
}


def _load_profile(persona):
    path = PROFILE_DIR / f"{persona}_profile.py"
    spec = importlib.util.spec_from_file_location(f"_barrier_profile_{persona}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    upper = persona.upper()
    return getattr(mod, f"{upper}_BARRIER_PROFILE"), getattr(mod, f"{upper}_TASK_FRAME")


VERDICT_INSTRUCTIONS = """
Judge the page for this one person only. Do not judge whether the page is
technically correct or standards-conformant; judge whether this person
could use it.

Choose exactly one label:
  - "Barrier": this person would be blocked, significantly delayed, or excluded.
  - "No-Barrier": this person encounters the relevant elements but can complete the task.
  - "Not-Encountered": the page has nothing that this person's needs make relevant.

Use "Not-Encountered" only when the page truly has nothing relevant to this
person, not merely because it looks fine.

If the label is "Barrier", also give:
  - severity: "Blocking" | "Frustrating" | "Minor"
  - one entry in "barriers" per distinct barrier, saying in 1-2 sentences what
    blocks the person and citing the HTML fragment that causes it.
Otherwise severity is "N/A" and "barriers" is [].

Return ONLY this JSON object, no markdown fences, no preamble:
{
  "label": "Barrier" | "No-Barrier" | "Not-Encountered",
  "severity": "Blocking" | "Frustrating" | "Minor" | "N/A",
  "barriers": [
    {"what_blocks": "<1-2 sentences>", "evidence": "<HTML fragment>"}
  ],
  "confidence": "High" | "Medium" | "Low",
  "rationale": "<2-4 sentences explaining the label>"
}
"""

TOOL_ADDENDUM = """
You have tools that run automated technical checks on the page. Their
results are evidence, not verdicts: a technical failure is only a barrier
if it would actually block this person, and a page can pass every check
and still be a barrier. Call a tool at most once, pass the full page HTML
as the "html" argument, and then give your final JSON answer.
"""

NO_TOOLS_NOTE = """
You have no tools. Reason from the HTML source directly.
"""


def persona_system_prompt(persona, with_tools):
    profile, task = _load_profile(persona)
    return (
        profile
        + "\n\nYour task: " + task
        + "\n" + (TOOL_ADDENDUM if with_tools else NO_TOOLS_NOTE)
        + VERDICT_INSTRUCTIONS
    )


def vanilla_system_prompt(persona, with_tools):
    who = PERSON_DESCRIPTORS[persona]
    return (
        "You are an accessibility expert. Decide whether the web page below "
        f"presents a barrier to {who}.\n"
        + (TOOL_ADDENDUM if with_tools else NO_TOOLS_NOTE)
        + VERDICT_INSTRUCTIONS
    )


def user_message(html):
    # Identical to the user turn BaseAgenticAgent sends, so the agent and
    # single-call conditions see the same message.
    return f"Evaluate this HTML:\n\n{html}"
