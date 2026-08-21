"""
llm_client1.py

Provider adapter for the A11yAgents / AgentA11y study.

Normalizes OpenAI chat-completions and Anthropic messages behind a single
interface so the agentic loop in personas/base_agent.py and the single-shot
call in conditions/condition_b_persona_llm.py run unchanged across providers.

Supported models:
    gpt-4o                (OpenAI direct)
    gpt-5.2               (Azure OpenAI — routes through Azure when AZURE_OPENAI_ENDPOINT set)
    claude-sonnet-4-6     (Anthropic direct, or Azure Anthropic passthrough)
    claude-opus-4-8       (Anthropic direct, or Azure Anthropic passthrough)

Azure routing: if the environment variable AZURE_ANTHROPIC_ENDPOINT is set,
claude-* models route through Azure AI Foundry's Anthropic-native endpoint
using AZURE_ANTHROPIC_API_KEY. If unset, they use direct Anthropic with
ANTHROPIC_API_KEY. The rest of the codebase (personas, conditions, runner)
does not need to know or care.

Set these env vars in .env:

  For Azure Anthropic (claude-* models):
    AZURE_ANTHROPIC_ENDPOINT=https://YOUR-RESOURCE.services.ai.azure.com/anthropic
    AZURE_ANTHROPIC_API_KEY=YOUR_KEY

  For Azure OpenAI (gpt-* models):
    AZURE_OPENAI_ENDPOINT=https://YOUR-RESOURCE.services.ai.azure.com
    AZURE_OPENAI_API_KEY=YOUR_KEY              (can be same key as above)
    AZURE_OPENAI_API_VERSION=2025-01-01-preview (optional, this is the default)

  Both can share the same Azure resource and key — the endpoint suffix differs.

Model string vs deployment name: the model string you pass in (e.g.
claude-sonnet-4-6) is used both as the local identifier and as the Azure
deployment name. If Azure gave you a different deployment name than the
canonical model name, set AZURE_ANTHROPIC_DEPLOYMENT_<MODEL>=<deployment>,
where <MODEL> is the model string with '-' replaced by '_' and uppercased.
Example: AZURE_ANTHROPIC_DEPLOYMENT_CLAUDE_SONNET_4_6=my-sonnet.

Adapter contract:

    client = make_client("claude-sonnet-4-6", api_key)

    resp = client.chat(system=..., messages=[...], tools=[...],
                       temperature=0, max_tokens=4096)
    # resp = {
    #     "text": str or None,           final assistant text, None if tool turn
    #     "tool_calls": [                 empty list if no tools requested
    #         {"id": str, "name": str, "arguments": dict}, ...
    #     ],
    #     "assistant_msg": provider-native message to append back,
    #     "usage": {"input_tokens": int, "output_tokens": int},
    # }

    client.append_assistant(messages, resp["assistant_msg"])
    client.append_tool_result(messages, call_id, tool_name, result_json_str)

`tools` is always passed in OpenAI function-calling format, i.e. the shape
the six personas1/*_agent.py files already return from get_tools(). The
Anthropic adapter converts it internally, so no persona file needs editing.

Key provider differences this module hides:
  1. System prompt: OpenAI takes a system message; Anthropic takes a
     top-level `system=` argument.
  2. Tool schema: OpenAI nests under function.parameters; Anthropic uses a
     flat name/description/input_schema.
  3. Tool calls: OpenAI returns message.tool_calls with JSON-string
     arguments; Anthropic returns tool_use content blocks with dict input.
  4. Tool results: OpenAI wants one {"role": "tool"} message per call;
     Anthropic wants ALL tool_result blocks for a turn batched into a
     single user message.
  5. max_tokens is required by Anthropic. `seed` does not exist there.
  6. Opus 4.8 does not accept temperature (extended thinking manages
     its own sampling); we omit it for opus-4-* models.
"""

import json
import os


# --------------------------------------------------------------------------- #
#  Factory                                                                     #
# --------------------------------------------------------------------------- #

OPENAI_PREFIXES = ("gpt-", "o1", "o3", "o4", "o5")
ANTHROPIC_PREFIXES = ("claude-",)


def _using_azure_anthropic():
    """Return True if Azure Anthropic env vars are set."""
    return bool(os.environ.get("AZURE_ANTHROPIC_ENDPOINT"))


def make_client(model, api_key=None):
    """Return the right adapter for a model string."""
    if model.startswith(ANTHROPIC_PREFIXES):
        if _using_azure_anthropic():
            key = api_key or os.environ.get("AZURE_ANTHROPIC_API_KEY")
            if not key:
                raise RuntimeError(
                    f"Model '{model}' via Azure needs AZURE_ANTHROPIC_API_KEY. "
                    "Add it to .env."
                )
            endpoint = os.environ["AZURE_ANTHROPIC_ENDPOINT"]
            return AzureAnthropicAdapter(model, key, endpoint)

        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                f"Model '{model}' needs ANTHROPIC_API_KEY (or set "
                f"AZURE_ANTHROPIC_ENDPOINT + AZURE_ANTHROPIC_API_KEY to "
                f"route through Azure). Add to .env."
            )
        return AnthropicAdapter(model, key)

    if model.startswith(OPENAI_PREFIXES):
        if _using_azure_openai():
            key = (
                api_key
                or os.environ.get("AZURE_OPENAI_API_KEY")
                or os.environ.get("AZURE_ANTHROPIC_API_KEY")  # shared key fallback
            )
            if not key:
                raise RuntimeError(
                    f"Model '{model}' via Azure needs AZURE_OPENAI_API_KEY "
                    "(or AZURE_ANTHROPIC_API_KEY as fallback). Add to .env."
                )
            endpoint = (
                os.environ.get("AZURE_OPENAI_ENDPOINT")
                or os.environ.get("AZURE_ANTHROPIC_ENDPOINT", "").replace("/anthropic", "")
            )
            return AzureOpenAIAdapter(model, key, endpoint)

        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError(
                f"Model '{model}' needs OPENAI_API_KEY (or set "
                f"AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_API_KEY to route "
                f"through Azure). Add to .env."
            )
        return OpenAIAdapter(model, key)

    raise ValueError(
        f"Unrecognized model '{model}'. Expected one of: gpt-4o, "
        f"claude-sonnet-4-6, claude-opus-4-8."
    )


def key_env_var(model):
    """
    Which env var a given model needs. Used by run_experiment.py to fail
    fast with a helpful message when the key is missing.
    """
    if model.startswith(ANTHROPIC_PREFIXES):
        if _using_azure_anthropic():
            return "AZURE_ANTHROPIC_API_KEY"
        return "ANTHROPIC_API_KEY"
    if model.startswith(OPENAI_PREFIXES):
        if _using_azure_openai():
            # Return whichever Azure key var is actually set
            if os.environ.get("AZURE_OPENAI_API_KEY"):
                return "AZURE_OPENAI_API_KEY"
            if os.environ.get("AZURE_ANTHROPIC_API_KEY"):
                return "AZURE_ANTHROPIC_API_KEY"
    return "OPENAI_API_KEY"


def _azure_deployment_for(model):
    """
    Look up the Azure deployment name for a given model string. If not set
    via env var, use the model string itself (Azure often lets you name
    the deployment identically to the model).
    """
    key = "AZURE_ANTHROPIC_DEPLOYMENT_" + model.upper().replace("-", "_")
    return os.environ.get(key, model)




def _using_azure_openai():
    """Return True if any Azure endpoint is configured (OpenAI-specific or shared Anthropic)."""
    return bool(
        os.environ.get("AZURE_OPENAI_ENDPOINT")
        or os.environ.get("AZURE_ANTHROPIC_ENDPOINT")
    )


def _azure_openai_deployment_for(model):
    """
    Look up the Azure OpenAI deployment name for a given model string.
    Falls back to the model string itself if no override is set.
    Example override: AZURE_OPENAI_DEPLOYMENT_GPT_5_2=my-gpt5-deployment
    """
    key = "AZURE_OPENAI_DEPLOYMENT_" + model.upper().replace("-", "_").replace(".", "_")
    return os.environ.get(key, model)

# --------------------------------------------------------------------------- #
#  OpenAI                                                                      #
# --------------------------------------------------------------------------- #

class OpenAIAdapter:
    provider = "openai"

    # Deterministic decoding. OpenAI does not guarantee reproducibility even
    # with seed + temperature=0, but this minimizes variance.
    SEED = 42

    # Models that require max_completion_tokens instead of max_tokens.
    # GPT-5.x series and o1/o3/o4 reasoning models use the new param.
    COMPLETION_TOKENS_PREFIXES = ("gpt-5", "o1", "o3", "o4", "o5")

    def __init__(self, model, api_key):
        import openai
        self.model = model
        self.client = openai.OpenAI(api_key=api_key)

    def _uses_completion_tokens(self):
        return any(self.model.startswith(p) for p in self.COMPLETION_TOKENS_PREFIXES)

    def chat(self, system, messages, tools=None, temperature=0, max_tokens=4096):
        # GPT-5.x and o-series models use max_completion_tokens instead of
        # max_tokens. Detect by model name prefix.
        tokens_key = "max_completion_tokens" if self._uses_completion_tokens() else "max_tokens"
        kwargs = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}] + list(messages),
            "temperature": temperature,
            tokens_key: max_tokens,
            "seed": self.SEED,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = self.client.chat.completions.create(**kwargs)
        msg = response.choices[0].message

        calls = []
        for tc in (msg.tool_calls or []):
            try:
                args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, TypeError):
                args = {}
            calls.append({
                "id": tc.id,
                "name": tc.function.name,
                "arguments": args,
            })

        usage = getattr(response, "usage", None)
        return {
            "text": msg.content,
            "tool_calls": calls,
            "assistant_msg": msg,
            "usage": {
                "input_tokens": getattr(usage, "prompt_tokens", None),
                "output_tokens": getattr(usage, "completion_tokens", None),
            },
        }

    def append_assistant(self, messages, assistant_msg):
        messages.append(assistant_msg)

    def append_tool_result(self, messages, call_id, name, content_json):
        messages.append({
            "role": "tool",
            "tool_call_id": call_id,
            "name": name,
            "content": content_json,
        })


# --------------------------------------------------------------------------- #
#  Anthropic (direct)                                                          #
# --------------------------------------------------------------------------- #

class AnthropicAdapter:
    provider = "anthropic"

    # Opus 4.x models reject the temperature parameter (extended thinking
    # manages sampling itself). Match by prefix so future opus versions
    # inherit the same behavior.
    OPUS_PREFIXES = ("claude-opus-4-8", "claude-opus-4-7", "claude-opus-4.8", "claude-opus-4.7")

    def __init__(self, model, api_key, client=None):
        import anthropic
        self.model = model
        self.client = client or anthropic.Anthropic(api_key=api_key)
        # Accumulates tool_result blocks for the CURRENT turn. Reset every
        # time a new assistant message is appended.
        self._pending_results = []

    # ---- schema conversion ---------------------------------------------- #

    @staticmethod
    def _convert_tools(tools):
        """
        OpenAI function-calling schema -> Anthropic tool schema.

        In:  {"type": "function",
              "function": {"name", "description", "parameters"}}
        Out: {"name", "description", "input_schema"}
        """
        converted = []
        for t in tools or []:
            fn = t.get("function", t) if isinstance(t, dict) else t
            schema = fn.get("parameters") or {
                "type": "object",
                "properties": {},
            }
            converted.append({
                "name": fn["name"],
                "description": (fn.get("description") or "").strip(),
                "input_schema": schema,
            })
        return converted

    @staticmethod
    def _block_to_dict(block):
        """Normalize an SDK content block to a plain dict."""
        if hasattr(block, "model_dump"):
            return block.model_dump(exclude_none=True)
        if hasattr(block, "dict"):
            return block.dict(exclude_none=True)
        return dict(block)

    def _accepts_temperature(self):
        return not any(p in self.model for p in self.OPUS_PREFIXES)

    # ---- main call -------------------------------------------------------- #

    def chat(self, system, messages, tools=None, temperature=0, max_tokens=4096):
        kwargs = {
            "model": self.model,
            "system": system,
            "messages": list(messages),
            "max_tokens": max_tokens,
        }
        # Only include temperature for models that accept it. Opus 4.x rejects it.
        if self._accepts_temperature():
            kwargs["temperature"] = temperature
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        response = self.client.messages.create(**kwargs)

        text_parts = []
        calls = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                calls.append({
                    "id": block.id,
                    "name": block.name,
                    "arguments": block.input or {},
                })

        assistant_msg = {
            "role": "assistant",
            "content": [self._block_to_dict(b) for b in response.content],
        }

        usage = getattr(response, "usage", None)
        return {
            "text": "".join(text_parts) if text_parts else None,
            "tool_calls": calls,
            "assistant_msg": assistant_msg,
            "usage": {
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
            },
        }

    # ---- message assembly ------------------------------------------------- #

    def append_assistant(self, messages, assistant_msg):
        messages.append(assistant_msg)
        # New turn begins; previous tool_result batch is closed.
        self._pending_results = []

    def append_tool_result(self, messages, call_id, name, content_json):
        """
        Anthropic requires every tool_result for a turn in ONE user message.
        The caller invokes this once per tool call, so accumulate and rewrite
        the trailing user message in place.
        """
        self._pending_results.append({
            "type": "tool_result",
            "tool_use_id": call_id,
            "content": content_json,
        })

        trailing_is_our_batch = (
            messages
            and messages[-1].get("role") == "user"
            and isinstance(messages[-1].get("content"), list)
            and len(self._pending_results) > 1
        )
        if trailing_is_our_batch:
            messages[-1]["content"] = list(self._pending_results)
        else:
            messages.append({
                "role": "user",
                "content": list(self._pending_results),
            })



# --------------------------------------------------------------------------- #
#  OpenAI (via Azure AI Foundry / Azure OpenAI Service)                        #
# --------------------------------------------------------------------------- #

class AzureOpenAIAdapter(OpenAIAdapter):
    """
    Routes gpt-* models through Azure OpenAI / Azure AI Foundry.

    Azure OpenAI uses the same request/response shape as direct OpenAI but:
      - Requires a deployment name in the URL path instead of a model name
        in the request body (though sending model= is also accepted)
      - Uses api-key header instead of Authorization: Bearer
      - Uses a versioned endpoint with ?api-version=
      - GPT-5.x models require max_completion_tokens instead of max_tokens

    The Azure OpenAI Python SDK handles all of this transparently when
    initialized with azure_endpoint + api_key + api_version.

    Env vars:
        AZURE_OPENAI_ENDPOINT    https://YOUR-RESOURCE.services.ai.azure.com
        AZURE_OPENAI_API_KEY     your key (can be same as AZURE_ANTHROPIC_API_KEY)
        AZURE_OPENAI_API_VERSION api version (default: 2025-01-01-preview)

    Deployment name override:
        AZURE_OPENAI_DEPLOYMENT_GPT_5_2=my-deployment-name
        (if unset, the model string is used as the deployment name)
    """

    provider = "azure_openai"

    DEFAULT_API_VERSION = "2025-01-01-preview"

    def __init__(self, model, api_key, endpoint):
        import openai
        deployment = _azure_openai_deployment_for(model)
        api_version = os.environ.get(
            "AZURE_OPENAI_API_VERSION", self.DEFAULT_API_VERSION
        )
        # Resolve endpoint: strip any path suffix so we get the bare
        # resource URL (e.g. https://resource.services.ai.azure.com).
        # The caller may pass the Anthropic endpoint which has /anthropic.
        base_endpoint = endpoint.rstrip("/")
        for suffix in ("/anthropic", "/openai"):
            if base_endpoint.endswith(suffix):
                base_endpoint = base_endpoint[: -len(suffix)]

        self.model = deployment        # deployment name used in requests
        self.canonical_model = model   # original string for logging
        self.deployment = deployment
        self.endpoint = base_endpoint
        self.api_version = api_version
        self.client = openai.AzureOpenAI(
            azure_endpoint=base_endpoint,
            api_key=api_key,
            api_version=api_version,
        )

    def chat(self, system, messages, tools=None, temperature=0, max_tokens=4096):
        # Always use max_completion_tokens for Azure OpenAI GPT-5.x;
        # fall back to max_tokens for older deployments.
        tokens_key = "max_completion_tokens" if self._uses_completion_tokens() else "max_tokens"
        kwargs = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}] + list(messages),
            tokens_key: max_tokens,
            "seed": self.SEED,
        }
        # GPT-5.x and o-series do not support temperature
        if not self._uses_completion_tokens():
            kwargs["temperature"] = temperature
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = self.client.chat.completions.create(**kwargs)
        msg = response.choices[0].message

        calls = []
        for tc in (msg.tool_calls or []):
            try:
                import json as _json
                args = _json.loads(tc.function.arguments)
            except Exception:
                args = {}
            calls.append({
                "id": tc.id,
                "name": tc.function.name,
                "arguments": args,
            })

        usage = getattr(response, "usage", None)
        return {
            "text": msg.content,
            "tool_calls": calls,
            "assistant_msg": msg,
            "usage": {
                "input_tokens": getattr(usage, "prompt_tokens", None),
                "output_tokens": getattr(usage, "completion_tokens", None),
            },
        }

    # append_assistant and append_tool_result are inherited from OpenAIAdapter
    # unchanged — Azure OpenAI uses identical message format.

# --------------------------------------------------------------------------- #
#  Anthropic (via Azure AI Foundry passthrough)                                #
# --------------------------------------------------------------------------- #

class AzureAnthropicAdapter(AnthropicAdapter):
    """
    Azure AI Foundry exposes Claude at an Anthropic-compatible endpoint:
        https://<RESOURCE>.services.ai.azure.com/anthropic

    The Anthropic Python SDK accepts a base_url parameter for exactly this
    case. The request/response shape is identical to direct Anthropic, so
    we inherit all of AnthropicAdapter and just override construction.

    Azure uses the deployment name in the "model" field of each request,
    not the canonical model string. If Azure gave you a deployment named
    differently from the model, set AZURE_ANTHROPIC_DEPLOYMENT_<MODEL> in
    the environment (see _azure_deployment_for).
    """

    provider = "azure_anthropic"

    def __init__(self, model, api_key, endpoint):
        import anthropic
        deployment = _azure_deployment_for(model)
        # Azure endpoint must not include trailing slash for the SDK.
        base_url = endpoint.rstrip("/")
        client = anthropic.Anthropic(
            api_key=api_key,
            base_url=base_url,
        )
        # Store the deployment as self.model so requests use it
        super().__init__(deployment, api_key, client=client)
        # But keep the ORIGINAL model string accessible for logging so
        # results files show "claude-sonnet-4-6", not the deployment name.
        self.canonical_model = model
        self.deployment = deployment
        self.endpoint = base_url


# --------------------------------------------------------------------------- #
#  Self test                                                                   #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv

    load_dotenv()
    model = sys.argv[1] if len(sys.argv) > 1 else "gpt-4o"

    client = make_client(model)
    info = f"Adapter: {client.provider}  Model: {client.model}"
    if hasattr(client, "endpoint"):
        info += f"  Endpoint: {client.endpoint}"
    if hasattr(client, "canonical_model") and client.canonical_model != client.model:
        info += f"  (canonical: {client.canonical_model})"
    print(info)

    demo_tools = [{
        "type": "function",
        "function": {
            "name": "count_images",
            "description": "Counts img elements in an HTML string.",
            "parameters": {
                "type": "object",
                "properties": {"html": {"type": "string"}},
                "required": ["html"],
            },
        },
    }]

    messages = [{
        "role": "user",
        "content": "Count the images in <img src=a><img src=b>, then reply DONE.",
    }]

    resp = client.chat(
        system="You are a test harness. Use the tool, then reply DONE.",
        messages=messages,
        tools=demo_tools,
        max_tokens=512,
    )
    print("tool_calls:", resp["tool_calls"])

    if resp["tool_calls"]:
        client.append_assistant(messages, resp["assistant_msg"])
        for call in resp["tool_calls"]:
            client.append_tool_result(
                messages, call["id"], call["name"], json.dumps({"count": 2})
            )
        resp = client.chat(
            system="You are a test harness. Use the tool, then reply DONE.",
            messages=messages,
            tools=demo_tools,
            max_tokens=512,
        )

    print("final text:", resp["text"])
    print("usage:", resp["usage"])
    print("ROUNDTRIP OK")
