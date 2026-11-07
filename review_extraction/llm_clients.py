"""Claude backends exposing the small slice of the OpenAI Responses API used by DualAgentExtractor.

DualAgentExtractor only calls ``client.responses.create(model=, input=[system, user], text={"format": {...}})``
and reads ``output_text`` and ``usage``. The clients below mimic that surface so the pipeline stays unchanged:

- ``ClaudeCliClient``: runs ``claude -p`` (Claude Code, billed against a Claude Pro/Max subscription).
- ``AnthropicApiClient``: uses the Anthropic API (pay per token) through forced tool use.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from types import SimpleNamespace
from typing import Any

BACKENDS = ("openai", "claude-cli", "anthropic")

CLAUDE_DEFAULT_MODELS = {
    "model": "claude-sonnet-5-5",
    "validator_model": "claude-sonnet-5-5",
    "fallback_model": "claude-opus-5-5",
    "fallback_validator_model": "claude-opus-5-5",
}


class LLMRequestError(RuntimeError):
    """User-facing failure of a Claude backend (login, limits, quota)."""


def find_claude_executable() -> str:
    explicit = os.getenv("CLAUDE_CLI_PATH")
    if explicit:
        return explicit
    found = shutil.which("claude")
    if found:
        return found
    raise LLMRequestError(
        "Claude Code CLI not found. Install it, run `claude` once to log in with your subscription, "
        "or set CLAUDE_CLI_PATH to the claude executable."
    )


class _Responses:
    def __init__(self, owner: Any) -> None:
        self._owner = owner

    def create(self, *, model: str, input: list[dict[str, str]], text: dict[str, Any], **_: Any) -> object:
        system = "\n\n".join(m["content"] for m in input if m["role"] == "system")
        user = "\n\n".join(m["content"] for m in input if m["role"] != "system")
        schema = text["format"]["schema"]
        return self._owner.complete(model=model, system=system, user=user, schema=schema)


class ClaudeCliClient:
    def __init__(self, executable: str | None = None, timeout: float = 900, effort: str | None = None) -> None:
        self.executable = executable or find_claude_executable()
        self.timeout = timeout
        self.effort = effort or os.getenv("CLAUDE_EFFORT") or None
        self.responses = _Responses(self)

    def complete(self, *, model: str, system: str, user: str, schema: dict[str, Any]) -> object:
        cmd = [
            self.executable,
            "-p",
            "--model", model,
            "--output-format", "json",
            "--json-schema", json.dumps(schema, separators=(",", ":")),
            "--tools", "",
            "--disable-slash-commands",
            "--no-session-persistence",
            "--setting-sources", "",
            "--system-prompt", system,
        ]
        if self.effort:
            cmd += ["--effort", self.effort]
        prompt = user + "\n\nReturn only the JSON object that matches the required schema."
        try:
            proc = subprocess.run(
                cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                timeout=self.timeout, cwd=os.path.expanduser("~"),
            )
        except subprocess.TimeoutExpired as exc:
            raise LLMRequestError(f"claude CLI timed out after {self.timeout}s.") from exc
        return parse_cli_output(proc.stdout, proc.returncode, proc.stderr)


def parse_cli_output(stdout: str, returncode: int, stderr: str = "") -> object:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise LLMRequestError(f"Unreadable claude CLI output (exit {returncode}): {(stderr or stdout)[:500]}") from exc
    if payload.get("is_error") or returncode != 0:
        message = str(payload.get("result") or stderr or "unknown error")
        hint = ""
        lowered = message.lower()
        if "login" in lowered or "logged in" in lowered:
            hint = " Run `claude` interactively once and log in with /login."
        elif "limit" in lowered or "quota" in lowered or "usage" in lowered:
            hint = " Subscription limit reached: wait for the reset, then rerun the same command (existing JSON is reused)."
        raise LLMRequestError(f"claude CLI error: {message}.{hint}")
    structured = payload.get("structured_output")
    output_text = json.dumps(structured) if structured is not None else str(payload.get("result") or "")
    usage = payload.get("usage") or {}
    cache_read = int(usage.get("cache_read_input_tokens") or 0)
    cache_write = int(usage.get("cache_creation_input_tokens") or 0)
    input_tokens = int(usage.get("input_tokens") or 0) + cache_read + cache_write
    output_tokens = int(usage.get("output_tokens") or 0)
    return SimpleNamespace(
        output_text=output_text,
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            input_tokens_details=SimpleNamespace(cached_tokens=cache_read),
        ),
    )


class AnthropicApiClient:
    """Anthropic API via forced tool use (untested without an API key)."""

    def __init__(self, client: Any | None = None, max_tokens: int = 16000) -> None:
        if client is None:
            try:
                import anthropic
            except ImportError as exc:
                raise LLMRequestError('The anthropic SDK is required: pip install -e ".[anthropic]"') from exc
            client = anthropic.Anthropic()
        self.client = client
        self.max_tokens = max_tokens
        self.responses = _Responses(self)

    def complete(self, *, model: str, system: str, user: str, schema: dict[str, Any]) -> object:
        tool = {"name": "return_result", "description": "Return the structured result.", "input_schema": schema}
        try:
            message = self.client.messages.create(
                model=model,
                max_tokens=self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                tools=[tool],
                tool_choice={"type": "tool", "name": "return_result"},
            )
        except Exception as exc:
            if exc.__class__.__name__ in {"RateLimitError", "AuthenticationError", "PermissionDeniedError"}:
                raise LLMRequestError(f"Anthropic API error ({exc.__class__.__name__}): {exc}") from exc
            raise
        block = next((b for b in message.content if getattr(b, "type", None) == "tool_use"), None)
        if block is None:
            raise LLMRequestError("Anthropic response contained no structured result.")
        usage = message.usage
        cache_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        cache_write = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
        input_tokens = int(usage.input_tokens) + cache_read + cache_write
        output_tokens = int(usage.output_tokens)
        return SimpleNamespace(
            output_text=json.dumps(block.input),
            usage=SimpleNamespace(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                input_tokens_details=SimpleNamespace(cached_tokens=cache_read),
            ),
        )


def make_client(backend: str) -> Any | None:
    """Return a client for DualAgentExtractor, or None to use the default OpenAI client."""
    if backend == "claude-cli":
        return ClaudeCliClient()
    if backend == "anthropic":
        return AnthropicApiClient()
    return None
