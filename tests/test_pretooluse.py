"""``otari policy pretooluse`` and the thin hook script that shells out to it."""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from click.testing import CliRunner

from otari_agent_gates import cli as gates_cli

_HOOK_PATH = Path(__file__).resolve().parents[1] / "src" / "otari_agent_gates" / "hooks" / "pretooluse_hook.py"

_GATES = """
on_unavailable: block
gates:
  - type: command
    name: no-force-push
    pattern: "git\\\\s+push\\\\b.*?(?:--force(?!-)\\\\b|(?<!\\\\S)-f\\\\b)"
    mode: must_not_run
    message: "Never force-push."
  - type: command
    name: web-lint
    pattern: "pnpm --dir web run lint"
    mode: must_run_and_succeed
    message: "Run the web lint."
  - type: command
    name: only-when-web-changed
    pattern: "rm -rf"
    mode: must_not_run
    paths: ["web/*"]
    message: "Conditional gates are not enforced here."
"""


def _load_hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pretooluse_hook", _HOOK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _payload(command: str, tool: str = "Bash") -> str:
    return json.dumps({"tool_name": tool, "tool_input": {"command": command}, "session_id": "s"})


@pytest.fixture
def gates_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / ".otari-gates.yml").write_text(_GATES, encoding="utf-8")
    nested = tmp_path / "src" / "deep"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    return tmp_path


def test_pretooluse_denies_a_banned_command(gates_dir: Path) -> None:
    result = CliRunner().invoke(gates_cli.policy, ["pretooluse"], input=_payload("git push --force origin main"))
    assert result.exit_code == 2
    decision = json.loads(result.stderr.strip())
    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert decision["systemMessage"] == "Never force-push."


def test_pretooluse_allows_a_quoted_mention(gates_dir: Path) -> None:
    result = CliRunner().invoke(gates_cli.policy, ["pretooluse"], input=_payload('echo "git push --force"'))
    assert result.exit_code == 0


def test_pretooluse_ignores_gates_it_cannot_enforce(gates_dir: Path) -> None:
    result = CliRunner().invoke(gates_cli.policy, ["pretooluse"], input=_payload("rm -rf web/dist"))
    assert result.exit_code == 0


def test_pretooluse_allows_other_tools_and_malformed_input(gates_dir: Path) -> None:
    assert (
        CliRunner().invoke(gates_cli.policy, ["pretooluse"], input=_payload("git push -f", tool="Edit")).exit_code == 0
    )
    assert CliRunner().invoke(gates_cli.policy, ["pretooluse"], input="not json").exit_code == 0


def test_pretooluse_fails_open_without_a_gates_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(gates_cli.policy, ["pretooluse"], input=_payload("git push --force"))
    assert result.exit_code == 0


def test_pretooluse_fails_open_on_an_invalid_gates_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".otari-gates.yml").write_text("gates: []\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(gates_cli.policy, ["pretooluse"], input=_payload("git push --force"))
    assert result.exit_code == 0


class _Completed:
    def __init__(self, returncode: int, stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = ""
        self.stderr = stderr


def test_hook_forwards_stdin_and_relays_a_deny(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    hook = _load_hook()
    seen: dict[str, Any] = {}

    def fake_run(argv: list[str], **kwargs: Any) -> _Completed:
        seen["argv"] = argv
        seen["input"] = kwargs["input"]
        return _Completed(2, stderr='{"hookSpecificOutput": {"permissionDecision": "deny"}, "systemMessage": "no"}\n')

    monkeypatch.setattr(hook.subprocess, "run", fake_run)
    monkeypatch.setenv("OTARI_CLI_PATH", "/opt/otari")
    monkeypatch.setattr(sys, "stdin", io.StringIO(_payload("git push -f")))
    assert hook.main() == 2
    assert seen["argv"] == ["/opt/otari", "policy", "pretooluse"]
    assert json.loads(seen["input"])["tool_input"]["command"] == "git push -f"
    assert json.loads(capsys.readouterr().err)["systemMessage"] == "no"


def test_hook_fails_open_when_otari_is_missing_or_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    hook = _load_hook()
    monkeypatch.setattr(sys, "stdin", io.StringIO(_payload("git push -f")))
    monkeypatch.setattr(hook.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    assert hook.main() == 0

    monkeypatch.setattr(sys, "stdin", io.StringIO(_payload("git push -f")))
    monkeypatch.setattr(
        hook.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("otari", 1))
    )
    assert hook.main() == 0

    monkeypatch.setattr(sys, "stdin", io.StringIO(_payload("git push -f")))
    monkeypatch.setattr(hook.subprocess, "run", lambda *a, **k: _Completed(0))
    assert hook.main() == 0
