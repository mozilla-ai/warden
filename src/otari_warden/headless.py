"""Shell out to the locally installed ``claude`` CLI in headless mode.

Two callers: the ``subscription`` judge backend in ``service.py`` (run inside the
gateway process, so that process must sit on the same machine as the ``claude``
login) and ``otari warden generate``. Both want a one-shot ``claude -p`` call
whose reply parses as JSON, billed to whatever session is already logged in.

Every invocation passes ``--safe-mode``, not ``--bare``. Both suppress hook
discovery for the subprocess's own session, which is what stops a check made from
inside a Claude Code ``Stop`` hook from re-triggering that same hook. ``--bare``
additionally restricts auth to an API key, which defeats the point of riding a
Pro/Max login; ``--safe-mode`` leaves auth alone.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_CLAUDE_BINARY_ENV = "OTARI_CLAUDE_CLI_PATH"
_DEFAULT_TIMEOUT_SECONDS = 120
_MAX_JUDGE_ATTEMPTS = 2

# The smallest current model. Judging one stated rule is a narrow task, and every
# judge gate is a real subscription call, so the default is the model that needs the
# least. A gate may still name a bigger one through judge_model.
DEFAULT_SUBSCRIPTION_MODEL = "claude-haiku-4-5-20251001"


class ClaudeCliNotFoundError(RuntimeError):
    """``claude`` is not on PATH, and no ``OTARI_CLAUDE_CLI_PATH`` override resolves either."""


class ClaudeCliCallError(RuntimeError):
    """The subprocess ran but failed: non-zero exit, timeout, or an unusable envelope."""

    def __init__(self, message: str, *, returncode: int | None = None, stderr: str = "") -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


def find_claude_binary() -> str | None:
    """``OTARI_CLAUDE_CLI_PATH`` override if set and resolvable, else ``claude`` on PATH."""
    override = os.environ.get(_CLAUDE_BINARY_ENV)
    if override:
        return override if (shutil.which(override) or Path(override).is_file()) else None
    return shutil.which("claude")


@dataclass(frozen=True)
class ClaudeHeadlessResult:
    """One ``claude -p`` call's reply text, with the usage and cost the envelope itself reports.

    The cost is what the tokens would have cost metered through the API. A subscription
    call has no marginal dollar cost, so it is shown as an equivalent, not a bill.
    """

    text: str
    total_cost_usd: float | None
    input_tokens: int | None
    output_tokens: int | None
    cache_read_input_tokens: int | None
    cache_creation_input_tokens: int | None


def run_claude_headless(
    prompt: str,
    *,
    model: str | None = None,
    timeout: int = _DEFAULT_TIMEOUT_SECONDS,
    binary: str | None = None,
) -> ClaudeHeadlessResult:
    """Run ``claude -p <prompt> --safe-mode --output-format json`` and return its ``result``.

    ``model`` is passed as the CLI's own ``--model`` flag when given. Raises
    ``ClaudeCliNotFoundError`` if no binary resolves and ``ClaudeCliCallError`` for a
    non-zero exit, a timeout, non-JSON stdout, or an envelope with no usable ``result``.
    """
    resolved = binary or find_claude_binary()
    if not resolved:
        raise ClaudeCliNotFoundError("claude CLI not found on PATH")

    argv = [resolved, "-p", prompt, "--safe-mode", "--output-format", "json"]
    if model:
        argv.extend(["--model", model])

    try:
        completed = subprocess.run(  # noqa: S603 argv list, never shell=True; the prompt is its own element
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ClaudeCliCallError(f"claude CLI timed out after {timeout}s") from exc
    except OSError as exc:
        raise ClaudeCliCallError(f"failed to launch claude CLI: {exc}") from exc

    if completed.returncode != 0:
        raise ClaudeCliCallError(
            f"claude CLI exited {completed.returncode}",
            returncode=completed.returncode,
            stderr=completed.stderr[:2000],
        )
    try:
        envelope = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ClaudeCliCallError(f"claude CLI produced non-JSON stdout: {exc}") from exc

    result = envelope.get("result") if isinstance(envelope, dict) else None
    if not isinstance(result, str) or not result.strip():
        raise ClaudeCliCallError("claude CLI envelope had no usable 'result' field")

    usage = envelope.get("usage") if isinstance(envelope, dict) else None
    usage = usage if isinstance(usage, dict) else {}
    total_cost_usd = envelope.get("total_cost_usd") if isinstance(envelope, dict) else None
    return ClaudeHeadlessResult(
        text=result,
        total_cost_usd=total_cost_usd if isinstance(total_cost_usd, (int, float)) else None,
        input_tokens=usage.get("input_tokens") if isinstance(usage.get("input_tokens"), int) else None,
        output_tokens=usage.get("output_tokens") if isinstance(usage.get("output_tokens"), int) else None,
        cache_read_input_tokens=(
            usage.get("cache_read_input_tokens") if isinstance(usage.get("cache_read_input_tokens"), int) else None
        ),
        cache_creation_input_tokens=(
            usage.get("cache_creation_input_tokens")
            if isinstance(usage.get("cache_creation_input_tokens"), int)
            else None
        ),
    )


def extract_json(text: str) -> Any | None:
    """Best-effort JSON extraction from a ``claude -p`` result string.

    Strips a fence if the whole reply is wrapped in one, then ``json.loads``. No
    "find JSON in prose" fallback: every prompt asks for JSON only, and a reply that
    ignores that is better retried than guessed at. Returns ``None`` on failure.
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            lines = lines[1:-1]
            if lines and lines[0].strip().lower() == "json":
                lines = lines[1:]
            stripped = "\n".join(lines).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return None
