"""
Base class for all persona agents in the A11yAgents / AgentA11y study.

MULTI-MODEL VERSION. The agentic loop no longer calls the OpenAI SDK
directly. It goes through llm_client1.make_client(), which returns either an
OpenAI or an Anthropic adapter depending on the model string. Everything
else about the loop is unchanged, including tool_trace and per-tool timeouts.

Model selection, in priority order:
  1. `model=` kwarg passed to the constructor
  2. A11Y_MODEL environment variable (set by run_experiment.py --model)
  3. "gpt-4o"

The env var is read inside __init__, not at class-body import time, so
run_experiment.py can set it after this module is already imported.

Features retained from the previous version:
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
          "model": str,
          "provider": "openai" | "anthropic",
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
          "usage": {"input_tokens": int, "output_tokens": int},
      }
  }
"""

import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime

# Repo root on the path so `import llm_client1` works regardless of the
# directory the experiment is launched from.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from llm_client1 import make_client


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

# Default model when neither the constructor nor A11Y_MODEL specifies one.
DEFAULT_MODEL = "gpt-4o"


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
    TEMPERATURE = 0

    # Anthropic requires max_tokens. 4096 comfortably fits the persona JSON
    # verdict plus reasoning. Raise if verdicts start getting truncated.
    MAX_TOKENS = int(os.environ.get("A11Y_MAX_TOKENS", "4096"))

    def __init__(self, api_key, persona_name, model=None):
        # Resolved at construction time, not import time, so run_experiment.py
        # can set A11Y_MODEL after importing the conditions module.
        self.model = model or os.environ.get("A11Y_MODEL") or DEFAULT_MODEL
        self.client = make_client(self.model, api_key)
        self.provider = self.client.provider
        self.persona_name = persona_name
        self.tools_called = []
        self.tool_trace = []
        self.iteration_count = 0
        self.usage = {"input_tokens": 0, "output_tokens": 0}

    def _accumulate_usage(self, usage):
        for k in ("input_tokens", "output_tokens"):
            v = (usage or {}).get(k)
            if isinstance(v, int):
                self.usage[k] += v

    def evaluate(self, html):
        system_prompt = self.get_system_prompt()
        messages = [
            {"role": "user", "content": f"Evaluate this HTML:\n\n{html}"},
        ]

        self.tools_called = []
        self.tool_trace = []
        self.iteration_count = 0
        self.usage = {"input_tokens": 0, "output_tokens": 0}
        start_time = time.time()

        for iteration in range(self.MAX_ITERATIONS):
            self.iteration_count = iteration + 1

            response = self.client.chat(
                system=system_prompt,
                messages=messages,
                tools=self.get_tools(),
                temperature=self.TEMPERATURE,
                max_tokens=self.MAX_TOKENS,
            )
            self._accumulate_usage(response.get("usage"))

            if response["tool_calls"]:
                self.client.append_assistant(messages, response["assistant_msg"])

                for tool_call in response["tool_calls"]:
                    tool_name = tool_call["name"]
                    tool_call_id = tool_call["id"]
                    arguments = tool_call["arguments"]
                    self.tools_called.append(tool_name)

                    # Run the tool under a wall-clock timeout so one hung
                    # call cannot block the whole evaluation.
                    result, status, error, elapsed = self._invoke_with_timeout(
                        tool_name, arguments
                    )

                    # Log the outcome
                    LOGGER.info(
                        "model=%s persona=%s tool=%s status=%s elapsed=%.2f iter=%d",
                        self.model, self.persona_name, tool_name, status,
                        elapsed, self.iteration_count,
                    )
                    if status != "ok":
                        LOGGER.warning(
                            "model=%s persona=%s tool=%s failed: %s",
                            self.model, self.persona_name, tool_name, error,
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
                        "tool_call_id": tool_call_id,
                    })

                    # Send the FULL (untruncated) result back to the LLM
                    # so its downstream reasoning is not degraded.
                    self.client.append_tool_result(
                        messages, tool_call_id, tool_name, result_json
                    )
            else:
                # Final non-tool message: parse and return.
                elapsed_total = time.time() - start_time
                return {
                    "evaluation": self.parse_output(response["text"]),
                    "metadata": {
                        "model": self.model,
                        "provider": self.provider,
                        "tools_called": self.tools_called,
                        "tool_trace": self.tool_trace,
                        "iteration_count": self.iteration_count,
                        "total_time_seconds": round(elapsed_total, 2),
                        "tool_timeout_seconds": TOOL_TIMEOUT_SEC,
                        "usage": dict(self.usage),
                    },
                }

        # Exceeded max iterations
        elapsed_total = time.time() - start_time
        LOGGER.warning(
            "model=%s persona=%s exceeded MAX_ITERATIONS=%d",
            self.model, self.persona_name, self.MAX_ITERATIONS,
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
                "model": self.model,
                "provider": self.provider,
                "tools_called": self.tools_called,
                "tool_trace": self.tool_trace,
                "iteration_count": self.iteration_count,
                "total_time_seconds": round(elapsed_total, 2),
                "tool_timeout_seconds": TOOL_TIMEOUT_SEC,
                "usage": dict(self.usage),
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
