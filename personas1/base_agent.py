"""
Base class for all persona agents in the A11yAgents study.

Provides the common agentic loop that drives the OpenAI tool-use conversation:
  1. Send system prompt + HTML to the LLM with the tool registry exposed
  2. Process any tool calls the LLM requests
  3. Loop until the LLM produces a final non-tool message
  4. Parse the JSON verdict out of that final message

Each persona subclass overrides three methods:
  - get_system_prompt() returns the persona prompt
  - get_tools() returns the OpenAI function-calling tool definitions
  - execute_tool(name, args) dispatches a tool call to a real Python function

The return contract from evaluate() is:
  {
      "evaluation": { ... persona's parsed JSON output ... },
      "metadata": {
          "tools_called": [list of tool name strings],
          "iteration_count": int,
          "total_time_seconds": float,
      }
  }
"""

import json
import time
import openai


class BaseAgenticAgent:
    """Common agentic loop for persona-grounded WCAG evaluation."""

    # Maximum tool-call iterations before we abort. Each iteration is one
    # LLM call. Persona prompts tell the model to call each tool AT MOST
    # ONCE; with five tools that's an upper bound of ~6 iterations
    # (5 tool calls + final answer). 10 is a safety margin.
    MAX_ITERATIONS = 10

    # Model used for all evaluations. Hardcoded for study reproducibility.
    # Change here if you need to compare model versions.
    MODEL = "gpt-4o"

    # Deterministic decoding for reproducibility within a single eval run.
    # Note: OpenAI does not guarantee determinism even with seed+temp=0,
    # but this minimizes variance.
    TEMPERATURE = 0
    SEED = 42

    def __init__(self, api_key, persona_name):
        self.client = openai.OpenAI(api_key=api_key)
        self.persona_name = persona_name
        self.tools_called = []
        self.iteration_count = 0

    # ------------------------------------------------------------------ #
    #  Main evaluation loop                                                #
    # ------------------------------------------------------------------ #

    def evaluate(self, html):
        """
        Run the full evaluation loop for one HTML page.

        Args:
            html: HTML string to evaluate.

        Returns:
            {
                "evaluation": parsed JSON verdict from the LLM,
                "metadata": tools_called list, iteration count, timing
            }
        """
        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": f"Evaluate this HTML:\n\n{html}"},
        ]

        self.tools_called = []
        self.iteration_count = 0
        start_time = time.time()

        for iteration in range(self.MAX_ITERATIONS):
            self.iteration_count = iteration + 1

            response = self.client.chat.completions.create(
                model=self.MODEL,
                messages=messages,
                tools=self.get_tools(),
                tool_choice="auto",
                temperature=self.TEMPERATURE,
                seed=self.SEED,
            )

            assistant_message = response.choices[0].message

            if assistant_message.tool_calls:
                # LLM wants to call one or more tools. Run them all,
                # append the responses, and loop.
                messages.append(assistant_message)

                for tool_call in assistant_message.tool_calls:
                    tool_name = tool_call.function.name
                    self.tools_called.append(tool_name)

                    try:
                        arguments = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        arguments = {}

                    result = self.execute_tool(tool_name, arguments)

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": json.dumps(result, default=str),
                    })
            else:
                # LLM produced a final non-tool message. Parse and return.
                elapsed = time.time() - start_time
                return {
                    "evaluation": self.parse_output(assistant_message.content),
                    "metadata": {
                        "tools_called": self.tools_called,
                        "iteration_count": self.iteration_count,
                        "total_time_seconds": round(elapsed, 2),
                    },
                }

        # Exceeded max iterations. Return an error envelope rather than
        # raising, so a batch run doesn't die on one stuck evaluation.
        elapsed = time.time() - start_time
        return {
            "evaluation": {
                "label": "error",
                "severity": "N/A",
                "issues": [],
                "overall_assessment": (
                    f"{self.persona_name} exceeded max iterations "
                    f"({self.MAX_ITERATIONS}) without producing a final verdict."
                ),
            },
            "metadata": {
                "tools_called": self.tools_called,
                "iteration_count": self.iteration_count,
                "total_time_seconds": round(elapsed, 2),
                "error": "max_iterations_exceeded",
            },
        }

    # ------------------------------------------------------------------ #
    #  Abstract methods - each persona subclass overrides                  #
    # ------------------------------------------------------------------ #

    def get_system_prompt(self):
        raise NotImplementedError("Subclass must define get_system_prompt()")

    def get_tools(self):
        raise NotImplementedError("Subclass must define get_tools()")

    def execute_tool(self, tool_name, arguments):
        raise NotImplementedError("Subclass must define execute_tool()")

    # ------------------------------------------------------------------ #
    #  JSON parsing of the final LLM verdict                               #
    # ------------------------------------------------------------------ #

    def parse_output(self, text):
        """
        Extract the JSON verdict from the LLM's final message.

        Strips markdown fences and any surrounding prose. If the JSON
        is malformed, returns an error envelope instead of raising,
        so a single bad parse doesn't kill a batch.
        """
        if not text:
            return {
                "label": "error",
                "severity": "N/A",
                "issues": [],
                "overall_assessment": "LLM returned empty content.",
            }

        clean = text.strip()

        # Strip markdown code fences if present
        if "```json" in clean:
            clean = clean.split("```json", 1)[1].split("```", 1)[0]
        elif "```" in clean:
            clean = clean.split("```", 1)[1].split("```", 1)[0]

        # If there's surrounding prose, isolate the outermost JSON object
        if "{" in clean and "}" in clean:
            start = clean.index("{")
            end = clean.rindex("}") + 1
            clean = clean[start:end]

        try:
            return json.loads(clean.strip())
        except json.JSONDecodeError as e:
            return {
                "label": "error",
                "severity": "N/A",
                "issues": [],
                "overall_assessment": f"Parse error: {str(e)}",
                "raw_output": text[:500],
            }
