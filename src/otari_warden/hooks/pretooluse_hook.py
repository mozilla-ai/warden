#!/usr/bin/env python3
"""Claude Code ``PreToolUse`` hook: deny a Bash call that matches a banned command gate.

A thin dispatcher: forwards the hook's JSON payload on stdin to ``otari warden
pretooluse``, which reads every ``must_not_run`` command gate from the discovered
``.otari-gates.yml`` and denies a match with that gate's own message. One
declaration then serves both the Stop-hook backstop and this prospective block.

Standard library only, so it can be copied to any machine that has Claude Code
and the ``otari`` CLI. Fails open on everything unexpected (``otari`` missing, a
timeout, malformed stdin): a bug in a prevention hook must never make Claude
Code itself unusable. Only an explicit deny from ``otari`` blocks the call.

Wiring, in ``.claude/settings.json`` or ``.claude/settings.local.json``::

    {
      "hooks": {
        "PreToolUse": [
          {
            "matcher": "Bash",
            "hooks": [
              {"type": "command", "command": "python3 /path/to/pretooluse_hook.py"}
            ]
          }
        ]
      }
    }

Environment variables:

- ``OTARI_CLI_PATH`` (optional): override for a non-PATH ``otari`` install.
"""

from __future__ import annotations

import os
import subprocess
import sys

_TIMEOUT_SECONDS = 15


def main() -> int:
    payload = sys.stdin.read()
    if not payload.strip():
        return 0
    otari_binary = os.environ.get("OTARI_CLI_PATH", "otari")
    try:
        completed = subprocess.run(  # noqa: S603 argv list, never shell=True
            [otari_binary, "warden", "pretooluse"],
            input=payload,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return 0
    if completed.returncode == 2 and completed.stderr.strip():
        # The deny JSON otari printed is what Claude Code reads, so it goes through verbatim.
        print(completed.stderr.strip(), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
