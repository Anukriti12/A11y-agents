"""
Base class for all persona agents in the A11yAgents study.

Additions in this version, in addition to the tool_trace field:
  1. Per-tool TIMEOUT (default 60s) so a hung tool doesn't block the whole
     agent loop. Timed-out calls are recorded in tool_trace with
     `status="timeout"` and the LLM sees an error dict.
  2. Structured logging via Python's logging module. Each tool invocation
     writes a line to results/logs/base_agent_YYYYMMDD.log (or stderr if
     no file handler is attached). Format:
        <time> <persona> <tool_name> status=<ok|error|timeout> elapsed=<s>
     Watch runs in real time with:
        tail -f results/logs/base_agent_*.log

The return contract from evaluate() is:
  {
      "evaluation": {parsed persona JSON},
      "metadata": {
          "tools_called": [names in order],
          "tool_trace": [
              {
                  "name": str,
                  "iteration": int,
                  "arguments": {sanitized args},
                  "output": {full or truncated result},
                  "output_truncated": bool,
                  "output_size_bytes": int,
                  "elapsed_seconds": float,
                  "status": "ok" | "error" | "timeout",
                  "error": str or None,
                  "tool_call_id": str,
              },
              ...
          ],
          "iteration_count": int,
          "total_time_seconds": float,
          "tool_timeout_seconds": float,
      }
  }
"""

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime

import openai


# --------------------------------------------------------------------------- #
#  Configuration                                                               #
# --------------------------------------------------------------------------- #

# Per-tool cap. Selenium/Playwright tools have their own internal timeouts
# but they can still hang past those (browser crashes, network stalls).
# 60s is a generous ceiling for legitimate work; anything longer is a bug.
TOOL_TIMEOUT_SEC = float(os.environ.get("A11Y_TOOL_TIMEOUT_SEC", "60"))

# Cap on per-tool-call output stored in the trace. Set very high; can be
# lowered if row sizes get unwieldy.
MAX_TOOL_OUTPUT_BYTES = int(os.environ.get("A11Y_MAX_TOOL_OUTPUT", "100000"))


# --------------------------------------------------------------------------- #
#  Logging setup                                                               #
# --------------------------------------------------------------------------- #

def _setup_logger():
    """Attach a file handler for tool traces, once per process."""
    logger = logging.getLogger("a11yagents.base_agent")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)

    log_dir = os.environ.get("A11Y_LOG_DIR", "results/logs")
    try:
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(
            log_dir,
            f"base_agent_{datetime.utcnow().strftime('%Y%m%d')}.log",
        )
        fh = logging.FileHandler(log_path, mode="a", encoding="utf-8")
        fh.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(message)s"
        ))
        logger.addHandler(fh)
    except OSError:
        # Filesystem read-only or similar; fall back to stderr
        pass

    # Also mirror to stderr so runs are watchable without tail -f
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter("[base_agent] %(message)s"))
    sh.setLevel(logging.WARNING)  # only warnings/errors on stderr
    logger.addHandler(sh)

    return logger


LOGGER = _setup_logger()


# --------------------------------------------------------------------------- #
#  Base class                                                                  #
# --------------------------------------------------------------------------- #

class BaseAgenticAgent:
    """Common agentic loop for persona-grounded WCAG evaluation."""

    MAX_ITERATIONS = 10
    MODEL = "gpt-4o"
    TEMPERATURE = 0
    SEED = 42

    def __init__(self, api_key, persona_name):
        self.client = openai.OpenAI(api_key=api_key)
        self.persona_name = persona_name
        self.tools_called = []
        self.tool_trace = []
        self.iteration_count = 0

    def evaluate(self, html):
        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": f"Evaluate this HTML:\n\n{html}"},
        ]

        self.tools_called = []
        self.tool_trace = []
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
                messages.append(assistant_message)

                for tool_call in assistant_message.tool_calls:
                    tool_name = tool_call.function.name
                    self.tools_called.append(tool_name)

                    try:
                        arguments = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        arguments = {}

                    # Run the tool under a wall-clock timeout so one hung
                    # call cannot block the whole evaluation.
                    result, status, error, elapsed = self._invoke_with_timeout(
                        tool_name, arguments
                    )

                    # Log the outcome
                    LOGGER.info(
                        "persona=%s tool=%s status=%s elapsed=%.2f iter=%d",
                        self.persona_name, tool_name, status,
                        elapsed, self.iteration_count,
                    )
                    if status != "ok":
                        LOGGER.warning(
                            "persona=%s tool=%s failed: %s",
                            self.persona_name, tool_name, error,
                        )

                    # Serialize and possibly truncate for the trace
                    result_json = json.dumps(result, default=str)
                    output_size = len(result_json.encode("utf-8"))
                    stored_output = result
                    truncated = False
                    if output_size > MAX_TOOL_OUTPUT_BYTES:
                        stored_output = {
                            "_truncated": True,
                            "_original_size_bytes": output_size,
                            "_head": result_json[:MAX_TOOL_OUTPUT_BYTES],
                        }
                        truncated = True

                    self.tool_trace.append({
                        "name": tool_name,
                        "iteration": self.iteration_count,
                        "arguments": self._sanitize_args(arguments),
                        "output": stored_output,
                        "output_truncated": truncated,
                        "output_size_bytes": output_size,
                        "elapsed_seconds": round(elapsed, 3),
                        "status": status,
                        "error": error,
                        "tool_call_id": tool_call.id,
                    })

                    # Send the FULL (untruncated) result back to the LLM
                    # so its downstream reasoning is not degraded.
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": result_json,
                    })
            else:
                # Final non-tool message: parse and return.
                elapsed_total = time.time() - start_time
                return {
                    "evaluation": self.parse_output(assistant_message.content),
                    "metadata": {
                        "tools_called": self.tools_called,
                        "tool_trace": self.tool_trace,
                        "iteration_count": self.iteration_count,
                        "total_time_seconds": round(elapsed_total, 2),
                        "tool_timeout_seconds": TOOL_TIMEOUT_SEC,
                    },
                }

        # Exceeded max iterations
        elapsed_total = time.time() - start_time
        LOGGER.warning(
            "persona=%s exceeded MAX_ITERATIONS=%d",
            self.persona_name, self.MAX_ITERATIONS,
        )
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
                "tool_trace": self.tool_trace,
                "iteration_count": self.iteration_count,
                "total_time_seconds": round(elapsed_total, 2),
                "tool_timeout_seconds": TOOL_TIMEOUT_SEC,
                "error": "max_iterations_exceeded",
            },
        }

    def _invoke_with_timeout(self, tool_name, arguments):
        """
        Run execute_tool under a per-call wall-clock cap. Returns:
            (result_dict, status, error_str_or_None, elapsed_seconds)

        status is one of:
            "ok"       tool completed cleanly
            "timeout"  exceeded TOOL_TIMEOUT_SEC
            "error"    tool raised an exception

        On timeout, the worker thread is abandoned (not killed - Python
        can't kill threads). Selenium/Playwright subprocesses will leak
        until the parent process exits. Acceptable for a research run
        that terminates within hours.
        """
        start = time.time()
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self.execute_tool, tool_name, arguments)
                try:
                    result = future.result(timeout=TOOL_TIMEOUT_SEC)
                    elapsed = time.time() - start
                    return result, "ok", None, elapsed
                except FuturesTimeoutError:
                    elapsed = time.time() - start
                    return (
                        {
                            "error": (
                                f"Tool '{tool_name}' timed out after "
                                f"{TOOL_TIMEOUT_SEC}s"
                            ),
                            "tool_name": tool_name,
                            "status": "timeout",
                        },
                        "timeout",
                        f"timeout after {TOOL_TIMEOUT_SEC}s",
                        elapsed,
                    )
        except Exception as e:
            elapsed = time.time() - start
            return (
                {
                    "error": str(e),
                    "tool_name": tool_name,
                    "status": "failed",
                },
                "error",
                str(e),
                elapsed,
            )

    def _sanitize_args(self, arguments):
        """
        Trim the 'html' argument from stored arguments since it's already
        available at the row level via html_path.
        """
        if not isinstance(arguments, dict):
            return arguments
        clean = {}
        for k, v in arguments.items():
            if k == "html" and isinstance(v, str):
                clean[k] = f"<html {len(v)} bytes; see html_path>"
            else:
                clean[k] = v
        return clean

    # ------------------------------------------------------------------ #
    #  Abstract methods                                                    #
    # ------------------------------------------------------------------ #

    def get_system_prompt(self):
        raise NotImplementedError

    def get_tools(self):
        raise NotImplementedError

    def execute_tool(self, tool_name, arguments):
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    #  JSON parsing                                                        #
    # ------------------------------------------------------------------ #

    def parse_output(self, text):
        if not text:
            return {
                "label": "error",
                "severity": "N/A",
                "issues": [],
                "overall_assessment": "LLM returned empty content.",
            }
        clean = text.strip()
        if "```json" in clean:
            clean = clean.split("```json", 1)[1].split("```", 1)[0]
        elif "```" in clean:
            clean = clean.split("```", 1)[1].split("```", 1)[0]
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
