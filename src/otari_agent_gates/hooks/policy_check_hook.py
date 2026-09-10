#!/usr/bin/env python3
"""Claude Code ``Stop`` hook: block a turn that did not follow the stated rules.

A thin dispatcher: reads the hook's JSON payload from stdin and hands the
transcript path to ``otari policy check``, which does everything else against a
running ``otari serve``. This script owns only what is specific to being a Claude
Code hook: the ``stop_hook_active`` loop guard and the per-session retry cap.

On a non-compliant verdict it exits 2 with the violations on stderr, which Claude
Code feeds back to the model and keeps the session going: an automatic retry
loop with no human relaying anything. On a compliant verdict, an unconfigured
policy, or an unreachable gateway in the default fail-open mode, it exits 0. When
the retry cap is reached it records a ``gave_up`` marker via ``otari policy
give-up`` (best-effort, never blocking) so that moment leaves a trace.

Standard library only, so it can be copied to any machine that has Claude Code
and the ``otari`` CLI. Wiring, in ``~/.claude/settings.json``::

    {
      "hooks": {
        "Stop": [
          {
            "hooks": [
              {"type": "command", "command": "python3 /path/to/policy_check_hook.py"}
            ]
          }
        ]
      }
    }

Environment variables:

- ``OTARI_POLICY_NAME`` (required): which policy to check against. With a repo's
  own ``.otari-gates.yml`` this is only the label recorded in history.
- ``OTARI_CLI_PATH`` (optional): override for a non-PATH ``otari`` install.
- ``OTARI_POLICY_CHECK_MAX_ATTEMPTS`` (default ``3``): retry cap for one session,
  on top of Claude Code's own ``stop_hook_active`` guard.
- ``OTARI_POLICY_CHECK_FAIL_MODE`` (``open`` default, or ``closed``): what to do
  when ``otari policy check`` could not perform the check at all (exit code 2),
  as opposed to reporting non-compliant (exit code 1). ``open`` never blocks a
  session over a check that could not run; ``closed`` is hard enforcement.

``otari policy check`` resolves the gateway URL and API key from the ``config.yml``
it finds, normally the one ``otari serve`` was started with, so this hook passes
none of that through. A missing env var or a missing ``otari`` binary is treated
as "not set up yet": warn and exit 0.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

_DEFAULT_MAX_ATTEMPTS = 3
_REQUEST_TIMEOUT_SECONDS = 180  # a subscription-backend check shells out to claude itself


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    if payload.get("stop_hook_active"):
        return 0

    session_id = str(payload.get("session_id", "unknown"))
    transcript_path = payload.get("transcript_path")
    if not transcript_path:
        return 0

    policy_name = os.environ.get("OTARI_POLICY_NAME")
    if not policy_name:
        _warn("not configured (OTARI_POLICY_NAME missing), skipping")
        return 0

    max_attempts = _int_env("OTARI_POLICY_CHECK_MAX_ATTEMPTS", _DEFAULT_MAX_ATTEMPTS)
    fail_mode = os.environ.get("OTARI_POLICY_CHECK_FAIL_MODE", "open")

    state_path = _state_path(session_id)
    attempts = _load_attempts(state_path)
    if attempts >= max_attempts:
        _warn(f"{attempts} prior block(s) for this session, giving up")
        state_path.unlink(missing_ok=True)
        _record_give_up(policy_name, session_id)
        return 0

    otari_binary = os.environ.get("OTARI_CLI_PATH", "otari")
    try:
        completed = subprocess.run(  # noqa: S603 argv list, never shell=True
            [
                otari_binary,
                "policy",
                "check",
                policy_name,
                "--claude-transcript",
                transcript_path,
                "--session-id",
                session_id,
            ],
            capture_output=True,
            text=True,
            timeout=_REQUEST_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        _warn(f"otari CLI not found ({otari_binary!r}), skipping")
        return 0
    except subprocess.TimeoutExpired:
        return _handle_could_not_check(state_path, attempts, fail_mode, "otari policy check timed out")

    body = _decode_json(completed.stdout)

    if completed.returncode == 0:
        state_path.unlink(missing_ok=True)
        print(f"✅ Policy check passed ({_status_line(body, policy_name)})", file=sys.stderr)
        return 0
    if completed.returncode == 1:
        _save_attempts(state_path, attempts + 1)
        body_dict = body if isinstance(body, dict) else {}
        print(f"❌ Policy check failed ({_status_line(body_dict, policy_name)})", file=sys.stderr)
        _print_block_instructions(body_dict)
        return 2

    detail = (body or {}).get("error") if isinstance(body, dict) else completed.stderr.strip()
    return _handle_could_not_check(state_path, attempts, fail_mode, detail or "otari policy check failed")


def _status_line(body: Any, policy_name: str) -> str:
    """The one-line "<policy>: N gates, F failed, S skipped" summary shown on pass and fail."""
    if not isinstance(body, dict):
        return policy_name
    name = body.get("policy", policy_name)
    gates = body.get("gates") or []
    if not gates:
        return str(name)
    failed = sum(1 for gate in gates if not gate.get("passed", True) and not gate.get("skipped", False))
    skipped = sum(1 for gate in gates if gate.get("skipped", False))
    parts = [f"{len(gates)} gate{'s' if len(gates) != 1 else ''}"]
    if failed:
        parts.append(f"{failed} failed")
    if skipped:
        parts.append(f"{skipped} skipped")
    return f"{name}: {', '.join(parts)}"


def _record_give_up(policy_name: str, session_id: str) -> None:
    """Best-effort: giving up already means "let the session finish", so a failure to record it
    must never change that outcome. A short timeout, since this posts one small marker.
    """
    otari_binary = os.environ.get("OTARI_CLI_PATH", "otari")
    try:
        subprocess.run(  # noqa: S603 argv list, never shell=True
            [otari_binary, "policy", "give-up", policy_name, "--session-id", session_id],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def _handle_could_not_check(state_path: Path, attempts: int, fail_mode: str, detail: str) -> int:
    if fail_mode != "closed":
        _warn(f"⚠️  could not check ({detail}), skipping (fail-open)")
        return 0
    _save_attempts(state_path, attempts + 1)
    print(
        "⚠️  The policy check service could not be reached, so this turn's compliance with "
        "project rules is unverified. Do not stop yet: retry the check once, or explicitly state "
        "why you are confident this turn complied before finishing.",
        file=sys.stderr,
    )
    return 2


def _print_block_instructions(body: dict[str, Any]) -> None:
    lines = [
        "Your last turn did not comply with this project's stated rules. "
        "Before finishing, fix the following and then continue:"
    ]
    lines.extend(f"- {violation}" for violation in body.get("violations", []) or [])
    guidance = body.get("guidance")
    if guidance:
        lines.append(str(guidance))
    print("\n".join(lines), file=sys.stderr)


def _decode_json(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _state_path(session_id: str) -> Path:
    safe_id = "".join(char if char.isalnum() or char in "-_" else "_" for char in session_id)
    return Path(tempfile.gettempdir()) / f"otari-policy-check-{safe_id}.json"


def _load_attempts(state_path: Path) -> int:
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        return int(data.get("attempts", 0))
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return 0


def _save_attempts(state_path: Path, attempts: int) -> None:
    try:
        state_path.write_text(json.dumps({"attempts": attempts}), encoding="utf-8")
    except OSError:
        pass


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _warn(message: str) -> None:
    print(f"policy_check_hook: {message}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
