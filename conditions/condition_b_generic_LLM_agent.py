"""
Generic LLM Accessibility Agent

Loads a persona system prompt and evaluates HTML for accessibility issues.
The persona prompt defines who the user is — their disabilities, assistive
tools, and browsing context. The model responds in-character, describing
what it experiences and what it would do.
"""

import importlib.util
import os
import sys
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")

USER_PROMPT = "Evaluate this HTML for accessibility issues from your perspective:\n\n{html}"


def load_persona_prompt(persona_name: str):
    """
    Loads the system prompt for a given persona name.
    e.g. persona_name="stefan" loads prompts/stefan_system_prompt.py
    and returns the value of STEFAN_SYSTEM_PROMPT (case-insensitive suffix match).
    """
    filename = f"{persona_name.lower()}_system_prompt.py"
    filepath = os.path.join(PROMPTS_DIR, filename)

    if not os.path.exists(filepath):
        available = [
            f.replace("_system_prompt.py", "")
            for f in os.listdir(PROMPTS_DIR)
            if f.endswith("_system_prompt.py")
        ]
        raise FileNotFoundError(
            f"No prompt file found for persona '{persona_name}'.\n"
            f"Available personas: {', '.join(available) or 'none'}"
        )

    spec = importlib.util.spec_from_file_location("persona_module", filepath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Match any attribute ending in _SYSTEM_PROMPT (case-insensitive)
    for attr in dir(module):
        if attr.upper().endswith("_SYSTEM_PROMPT"):
            value = getattr(module, attr)
            if isinstance(value, str) and value.strip():
                return value

    raise ValueError(
        f"No non-empty *_SYSTEM_PROMPT variable found in '{filename}'.\n"
        f"Expected a string variable like {persona_name.upper()}_SYSTEM_PROMPT."
    )


def execute_generic_llm_agent(persona_name: str, html: str, *, model: str = "gpt-4o-mini",):
    """
    Evaluates HTML from the perspective of the given persona.

    Args:
        persona_name: Name of the persona (maps to a *_system_prompt.py file).
        html: The HTML string to evaluate.
        model: OpenAI model to use.

    Returns:
        The model's accessibility evaluation as a JSON string.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY is not set in environment or .env file.")

    system_prompt = load_persona_prompt(persona_name)
    client = OpenAI(api_key=api_key)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": USER_PROMPT.format(html=html)},
        ],
    )

    return response.choices[0].message.content

# To execute for a specific persona add the name of 
# the persona as the first argument in the terminal
if __name__ == "__main__":
    persona = sys.argv[1] if len(sys.argv) > 1 else "stefan"

    if len(sys.argv) > 2 and os.path.exists(sys.argv[2]):
        with open(sys.argv[2]) as f:
            html = f.read()
    else:
        html = """
         <!DOCTYPE html>
            <html lang="en">
            <!-- WCAG 3.1.4 | FAIL | SYNTHETIC | Persona: Stefan (ADHD/dyslexia)
                Abbreviations used without any expansion mechanism.
                Severity for Stefan: SERIOUS - TTS reads letters individually ("S-S-A") with no context;
                comprehension of the sentence is broken. -->
            <head><meta charset="utf-8"><title>Tax Filing Guide</title></head>
            <body>
            <main>
                <h1>How to File Your Taxes</h1>
                <p>Download the W-2 form from your employer's HR portal by January 31.</p>
                <p>If you have income from freelance work, you will also need a 1099 form.
                File your return with the IRS by April 15 to avoid penalties.</p>
                <p>Consider using EITC if you qualify — this can significantly reduce your AGI
                and lower the amount you owe to the IRS.</p>
                <p>For complex returns, consult a CPA. VITA offers free tax prep for qualifying filers.</p>
            </main>
            </body>
            </html>
        """

    print(f"=== {persona.upper()} ACCESSIBILITY EVALUATION ===\n")

    try:
        result = execute_generic_llm_agent(persona, html)
        print(result)
    except (FileNotFoundError, ValueError, EnvironmentError) as e:
        print(f"[Error] {e}", file=sys.stderr)
        sys.exit(1)