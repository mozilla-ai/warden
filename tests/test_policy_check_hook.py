"""Unit tests for the Claude Code Stop hook script (Phase 3: a thin dispatcher).

Loaded from its file path (it is a standalone script, not part of the `gateway`
package) via the same pattern as `tests/unit/test_code_execution_conformance_script.py`.
`main()`'s only external call - `subprocess.run(["otari", "warden", "check", ...])` -
is monkeypatched throughout; no real `otari` invocation happens here. Transcript
extraction now lives in `otari_warden.transcript` and is tested there.
"""

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

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "src" / "otari_warden" / "hooks" / "policy_check_hook.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("policy_check_hook", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


hook = _load()


class _FakeCompleted:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _stdin_json(payload: dict[str, Any]) -> io.StringIO:
    return io.StringIO(json.dumps(payload))


def _base_payload(session_id: str, transcript_path: str = "/some/transcript.jsonl") -> dict[str, Any]:
    return {"session_id": session_id, "transcript_path": transcript_path}


def test_main_rechecks_a_stop_flagged_stop_hook_active(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A stop that follows an earlier block is the turn that needs checking, not one to wave through."""
    monkeypatch.setenv("OTARI_POLICY_NAME", "p")
    monkeypatch.setattr(hook.tempfile, "gettempdir", lambda: str(tmp_path))
    calls: list[list[str]] = []

    def _record_call(argv: list[str], **_kwargs: Any) -> _FakeCompleted:
        calls.append(argv)
        return _FakeCompleted(0, json.dumps({"policy": "p", "compliant": True, "gates": []}))

    monkeypatch.setattr(hook.subprocess, "run", _record_call)
    payload = _base_payload("s1")
    payload["stop_hook_active"] = True
    monkeypatch.setattr(sys, "stdin", _stdin_json(payload))
    assert hook.main() == 0
    assert len(calls) == 1
    assert calls[0][1:4] == ["warden", "check", "p"]


def test_main_missing_policy_name_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTARI_POLICY_NAME", raising=False)

    def _fail_if_called(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("should not call otari when OTARI_POLICY_NAME is unset")

    monkeypatch.setattr(hook.subprocess, "run", _fail_if_called)
    monkeypatch.setattr(sys, "stdin", _stdin_json(_base_payload("s2")))
    assert hook.main() == 0


def test_main_gives_up_after_max_attempts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTARI_POLICY_NAME", "p")
    monkeypatch.setattr(hook.tempfile, "gettempdir", lambda: str(tmp_path))

    # `otari warden check` is never called once the attempt cap is reached, but a give-up
    # marker is - the one call that should happen here, not the real check.
    calls: list[list[str]] = []

    def _record_call(argv: list[str], **_kwargs: Any) -> _FakeCompleted:
        calls.append(argv)
        return _FakeCompleted(0)

    monkeypatch.setattr(hook.subprocess, "run", _record_call)
    state_path = hook._state_path("s3")
    state_path.write_text(json.dumps({"attempts": 3}), encoding="utf-8")

    monkeypatch.setattr(sys, "stdin", _stdin_json(_base_payload("s3")))
    assert hook.main() == 0
    assert not state_path.exists()
    assert len(calls) == 1
    assert calls[0][1:4] == ["warden", "give-up", "p"]
    assert calls[0][-2:] == ["--session-id", "s3"]


def test_main_give_up_call_failing_does_not_change_the_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OTARI_POLICY_NAME", "p")
    monkeypatch.setattr(hook.tempfile, "gettempdir", lambda: str(tmp_path))

    def _raise(*_args: Any, **_kwargs: Any) -> None:
        raise subprocess.TimeoutExpired(cmd="otari", timeout=10)

    monkeypatch.setattr(hook.subprocess, "run", _raise)
    hook._state_path("s3b").write_text(json.dumps({"attempts": 3}), encoding="utf-8")

    monkeypatch.setattr(sys, "stdin", _stdin_json(_base_payload("s3b")))
    assert hook.main() == 0


def test_main_cli_exit_zero_clears_state_and_exits_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTARI_POLICY_NAME", "p")
    monkeypatch.setattr(hook.tempfile, "gettempdir", lambda: str(tmp_path))
    body = json.dumps({"policy": "p", "checked": True, "compliant": True, "violations": [], "guidance": ""})
    monkeypatch.setattr(hook.subprocess, "run", lambda *a, **k: _FakeCompleted(0, stdout=body))

    monkeypatch.setattr(sys, "stdin", _stdin_json(_base_payload("s4")))
    assert hook.main() == 0
    assert not hook._state_path("s4").exists()


def test_main_cli_exit_zero_prints_a_clear_pass_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A compliant check must not be silent - the user should see visible confirmation a
    check ran and passed, not just the absence of a block."""
    monkeypatch.setenv("OTARI_POLICY_NAME", "p")
    monkeypatch.setattr(hook.tempfile, "gettempdir", lambda: str(tmp_path))
    body = json.dumps(
        {
            "policy": "p",
            "checked": True,
            "compliant": True,
            "violations": [],
            "guidance": "",
            "gates": [{"name": "g1", "type": "command", "passed": True, "skipped": False}],
        }
    )
    monkeypatch.setattr(hook.subprocess, "run", lambda *a, **k: _FakeCompleted(0, stdout=body))

    monkeypatch.setattr(sys, "stdin", _stdin_json(_base_payload("s4b")))
    assert hook.main() == 0
    err = capsys.readouterr().err
    assert "✅" in err
    assert "p" in err
    assert "1 gate" in err


def test_main_cli_exit_one_blocks_with_violations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("OTARI_POLICY_NAME", "p")
    monkeypatch.setattr(hook.tempfile, "gettempdir", lambda: str(tmp_path))
    body = json.dumps(
        {
            "policy": "p",
            "checked": True,
            "compliant": False,
            "violations": ["missed a rule"],
            "guidance": "fix it",
            "gates": [
                {"name": "g1", "type": "command", "passed": False, "skipped": False},
                {"name": "g2", "type": "llm_judge", "passed": False, "skipped": True},
            ],
        }
    )
    monkeypatch.setattr(hook.subprocess, "run", lambda *a, **k: _FakeCompleted(1, stdout=body))

    monkeypatch.setattr(sys, "stdin", _stdin_json(_base_payload("s5")))
    assert hook.main() == 2
    err = capsys.readouterr().err
    assert "❌" in err
    assert "2 gates" in err
    assert "1 failed" in err
    assert "1 skipped" in err
    assert "missed a rule" in err
    assert "fix it" in err
    assert hook._load_attempts(hook._state_path("s5")) == 1


def test_main_cli_exit_two_fail_open_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTARI_POLICY_NAME", "p")
    monkeypatch.delenv("OTARI_POLICY_CHECK_FAIL_MODE", raising=False)
    monkeypatch.setattr(hook.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(
        hook.subprocess, "run", lambda *a, **k: _FakeCompleted(2, stdout=json.dumps({"error": "not configured"}))
    )

    monkeypatch.setattr(sys, "stdin", _stdin_json(_base_payload("s6")))
    assert hook.main() == 0


def test_main_cli_exit_two_fail_closed_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("OTARI_POLICY_NAME", "p")
    monkeypatch.setenv("OTARI_POLICY_CHECK_FAIL_MODE", "closed")
    monkeypatch.setattr(hook.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(
        hook.subprocess, "run", lambda *a, **k: _FakeCompleted(2, stdout=json.dumps({"error": "unreachable"}))
    )

    monkeypatch.setattr(sys, "stdin", _stdin_json(_base_payload("s7")))
    assert hook.main() == 2
    assert "unverified" in capsys.readouterr().err


def test_main_otari_binary_missing_exits_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTARI_POLICY_NAME", "p")
    monkeypatch.setattr(hook.tempfile, "gettempdir", lambda: str(tmp_path))

    def fake_run(*_a: Any, **_k: Any) -> None:
        raise FileNotFoundError("no such file: otari")

    monkeypatch.setattr(hook.subprocess, "run", fake_run)

    monkeypatch.setattr(sys, "stdin", _stdin_json(_base_payload("s8")))
    assert hook.main() == 0


def test_main_otari_timeout_honors_fail_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTARI_POLICY_NAME", "p")
    monkeypatch.setenv("OTARI_POLICY_CHECK_FAIL_MODE", "closed")
    monkeypatch.setattr(hook.tempfile, "gettempdir", lambda: str(tmp_path))

    def fake_run(*_a: Any, **_k: Any) -> None:
        raise subprocess.TimeoutExpired(cmd="otari", timeout=1)

    monkeypatch.setattr(hook.subprocess, "run", fake_run)

    monkeypatch.setattr(sys, "stdin", _stdin_json(_base_payload("s9")))
    assert hook.main() == 2


def test_status_line_with_no_gates_falls_back_to_the_policy_name() -> None:
    assert hook._status_line({"policy": "p"}, "p") == "p"


def test_status_line_summarizes_gate_counts() -> None:
    body = {
        "policy": "p",
        "gates": [
            {"name": "a", "passed": True, "skipped": False},
            {"name": "b", "passed": False, "skipped": False},
            {"name": "c", "passed": False, "skipped": True},
        ],
    }
    assert hook._status_line(body, "p") == "p: 3 gates, 1 failed, 1 skipped"


def test_main_no_transcript_path_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTARI_POLICY_NAME", "p")

    def _fail_if_called(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("should not call otari with no transcript path")

    monkeypatch.setattr(hook.subprocess, "run", _fail_if_called)
    monkeypatch.setattr(sys, "stdin", _stdin_json({"session_id": "s10"}))
    assert hook.main() == 0
