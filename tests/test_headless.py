"""Unit tests for `otari_agent_gates.headless`. `subprocess.run` is monkeypatched throughout; no real `claude` runs."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from otari_agent_gates import headless as cli


class _FakeCompleted:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_run_claude_headless_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(argv: list[str], **kwargs: Any) -> _FakeCompleted:
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return _FakeCompleted(
            stdout=(
                '{"result": "hello", "session_id": "s1", "total_cost_usd": 0.0077, '
                '"usage": {"input_tokens": 10, "output_tokens": 40, "cache_read_input_tokens": 200, '
                '"cache_creation_input_tokens": 50}}'
            )
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = cli.run_claude_headless("do the thing", binary="/usr/local/bin/claude")

    assert result.text == "hello"
    assert result.total_cost_usd == 0.0077
    assert result.input_tokens == 10
    assert result.output_tokens == 40
    assert result.cache_read_input_tokens == 200
    assert result.cache_creation_input_tokens == 50
    assert captured["argv"] == [
        "/usr/local/bin/claude",
        "-p",
        "do the thing",
        "--safe-mode",
        "--output-format",
        "json",
    ]
    assert captured["kwargs"]["text"] is True
    assert captured["kwargs"]["check"] is False
    assert "shell" not in captured["kwargs"]


def test_run_claude_headless_passes_model_flag_when_given(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(argv: list[str], **kwargs: Any) -> _FakeCompleted:
        captured["argv"] = argv
        return _FakeCompleted(stdout='{"result": "hello"}')

    monkeypatch.setattr(subprocess, "run", fake_run)
    cli.run_claude_headless("do the thing", model="claude-haiku-4-5-20251001", binary="/usr/local/bin/claude")

    assert captured["argv"] == [
        "/usr/local/bin/claude",
        "-p",
        "do the thing",
        "--safe-mode",
        "--output-format",
        "json",
        "--model",
        "claude-haiku-4-5-20251001",
    ]


def test_run_claude_headless_omits_model_flag_when_not_given(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(argv: list[str], **kwargs: Any) -> _FakeCompleted:
        captured["argv"] = argv
        return _FakeCompleted(stdout='{"result": "hello"}')

    monkeypatch.setattr(subprocess, "run", fake_run)
    cli.run_claude_headless("do the thing", binary="/usr/local/bin/claude")

    assert "--model" not in captured["argv"]


def test_run_claude_headless_missing_usage_fields_default_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompleted(stdout='{"result": "hello"}'))
    result = cli.run_claude_headless("do the thing", binary="/usr/local/bin/claude")
    assert result.text == "hello"
    assert result.total_cost_usd is None
    assert result.input_tokens is None
    assert result.output_tokens is None
    assert result.cache_read_input_tokens is None
    assert result.cache_creation_input_tokens is None


def test_run_claude_headless_no_binary_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTARI_CLAUDE_CLI_PATH", raising=False)
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(cli.ClaudeCliNotFoundError):
        cli.run_claude_headless("prompt")


def test_run_claude_headless_nonzero_exit_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompleted(returncode=1, stderr="boom"))
    with pytest.raises(cli.ClaudeCliCallError, match="exited 1"):
        cli.run_claude_headless("prompt", binary="/bin/claude")


def test_run_claude_headless_non_json_stdout_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompleted(stdout="not json"))
    with pytest.raises(cli.ClaudeCliCallError, match="non-JSON"):
        cli.run_claude_headless("prompt", binary="/bin/claude")


def test_run_claude_headless_missing_result_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompleted(stdout="{}"))
    with pytest.raises(cli.ClaudeCliCallError, match="no usable"):
        cli.run_claude_headless("prompt", binary="/bin/claude")


def test_run_claude_headless_timeout_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*_a: Any, **_k: Any) -> _FakeCompleted:
        raise subprocess.TimeoutExpired(cmd="claude", timeout=1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(cli.ClaudeCliCallError, match="timed out"):
        cli.run_claude_headless("prompt", binary="/bin/claude", timeout=1)


def test_find_claude_binary_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_binary = tmp_path / "claude"
    fake_binary.write_text("#!/bin/sh\n")
    monkeypatch.setenv("OTARI_CLAUDE_CLI_PATH", str(fake_binary))
    assert cli.find_claude_binary() == str(fake_binary)


def test_find_claude_binary_env_override_unresolvable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTARI_CLAUDE_CLI_PATH", "/nonexistent/claude")
    assert cli.find_claude_binary() is None


def test_find_claude_binary_falls_back_to_which(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTARI_CLAUDE_CLI_PATH", raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}" if name == "claude" else None)
    assert cli.find_claude_binary() == "/usr/bin/claude"


def test_extract_json_plain() -> None:
    assert cli.extract_json('{"compliant": true}') == {"compliant": True}


def test_extract_json_fenced() -> None:
    text = '```json\n{"compliant": false, "violation": "x"}\n```'
    assert cli.extract_json(text) == {"compliant": False, "violation": "x"}


def test_extract_json_fenced_no_language_tag() -> None:
    text = '```\n{"compliant": true}\n```'
    assert cli.extract_json(text) == {"compliant": True}


def test_extract_json_malformed_returns_none() -> None:
    assert cli.extract_json("not json at all") is None
