"""Unit tests for `otari policy check` / `otari policy generate` (Phase 3).

`policy check` is an HTTP client (see its docstring in `cli.py`), so these mock
`urllib.request.urlopen` and `claude_transcript.extract_excerpt` rather than exercising
a real server - route-level behavior is covered by `tests/integration/test_policy_check_route.py`.
`policy generate` mirrors the coverage the deleted `tests/unit/test_generate_policy_from_plan.py`
had, adapted to `CliRunner`.
"""

from __future__ import annotations

import io
import json
import subprocess
import urllib.error
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from gateway.core.config import GatewayConfig

import otari_agent_gates.cli as gateway_cli
from otari_agent_gates.headless import ClaudeHeadlessResult


def _fake_result(text: str) -> ClaudeHeadlessResult:
    return ClaudeHeadlessResult(
        text=text,
        total_cost_usd=None,
        input_tokens=None,
        output_tokens=None,
        cache_read_input_tokens=None,
        cache_creation_input_tokens=None,
    )


class _FakeResponse:
    def __init__(self, status: int, body: dict[str, Any]) -> None:
        self.status = status
        self._body = json.dumps(body).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def _stub_config(monkeypatch: pytest.MonkeyPatch, *, host: str = "127.0.0.1", master_key: str = "mk") -> None:
    monkeypatch.setattr(
        gateway_cli, "load_config", lambda _path: GatewayConfig(host=host, port=8000, master_key=master_key)
    )


def _stub_excerpt(monkeypatch: pytest.MonkeyPatch, excerpt: str = "some transcript text") -> None:
    monkeypatch.setattr("otari_agent_gates.transcript.extract_excerpt", lambda *_a, **_k: excerpt)


def _write_transcript(tmp_path: Path) -> str:
    path = tmp_path / "session.jsonl"
    path.write_text('{"type": "user", "message": {"role": "user", "content": "go"}}\n', encoding="utf-8")
    return str(path)


def _write_transcript_with_uuid(tmp_path: Path, uuid: str) -> str:
    path = tmp_path / "session.jsonl"
    path.write_text(
        json.dumps({"type": "user", "message": {"role": "user", "content": "go"}, "uuid": uuid}) + "\n",
        encoding="utf-8",
    )
    return str(path)


def test_policy_check_compliant_exits_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_config(monkeypatch)
    _stub_excerpt(monkeypatch)
    body = {"policy": "p", "checked": True, "compliant": True, "violations": [], "guidance": ""}
    monkeypatch.setattr("urllib.request.urlopen", lambda *_a, **_k: _FakeResponse(200, body))

    result = CliRunner().invoke(gateway_cli.policy, ["check", "p", "--claude-transcript", _write_transcript(tmp_path)])
    assert result.exit_code == 0
    assert json.loads(result.output) == body


def test_policy_check_noncompliant_exits_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_config(monkeypatch)
    _stub_excerpt(monkeypatch)
    body = {"policy": "p", "checked": True, "compliant": False, "violations": ["bad"], "guidance": "fix"}
    monkeypatch.setattr("urllib.request.urlopen", lambda *_a, **_k: _FakeResponse(200, body))

    result = CliRunner().invoke(gateway_cli.policy, ["check", "p", "--claude-transcript", _write_transcript(tmp_path)])
    assert result.exit_code == 1
    assert json.loads(result.output)["compliant"] is False


def test_policy_check_unknown_policy_exits_two(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_config(monkeypatch)
    _stub_excerpt(monkeypatch)

    def fake_urlopen(*_a: Any, **_k: Any) -> Any:
        raise urllib.error.HTTPError("http://x", 404, "not found", None, io.BytesIO(b"{}"))  # type: ignore[arg-type]

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = CliRunner().invoke(
        gateway_cli.policy, ["check", "does-not-exist", "--claude-transcript", _write_transcript(tmp_path)]
    )
    assert result.exit_code == 2


def test_policy_check_unavailable_block_exits_two(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_config(monkeypatch)
    _stub_excerpt(monkeypatch)

    def fake_urlopen(*_a: Any, **_k: Any) -> Any:
        raise urllib.error.HTTPError("http://x", 502, "bad gateway", None, io.BytesIO(b"{}"))  # type: ignore[arg-type]

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = CliRunner().invoke(gateway_cli.policy, ["check", "p", "--claude-transcript", _write_transcript(tmp_path)])
    assert result.exit_code == 2


def test_policy_check_unrecognized_4xx_exits_two_not_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A 422 (or 401, or any status this code has no explicit branch for) has a JSON dict
    body just as often as a real verdict does - it must never fall through to the success
    path and default `compliant` to True, which would silently wave through a client-side
    bug (an unrecognized request field, an expired key) as a clean, compliant run."""
    _stub_config(monkeypatch)
    _stub_excerpt(monkeypatch)

    def fake_urlopen(*_a: Any, **_k: Any) -> Any:
        body = json.dumps({"detail": [{"type": "extra_forbidden", "loc": ["body", "turn_id"]}]}).encode()
        raise urllib.error.HTTPError("http://x", 422, "unprocessable", None, io.BytesIO(body))  # type: ignore[arg-type]

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = CliRunner().invoke(gateway_cli.policy, ["check", "p", "--claude-transcript", _write_transcript(tmp_path)])
    assert result.exit_code == 2


def test_policy_check_connection_error_exits_two(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_config(monkeypatch)
    _stub_excerpt(monkeypatch)

    def fake_urlopen(*_a: Any, **_k: Any) -> Any:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = CliRunner().invoke(gateway_cli.policy, ["check", "p", "--claude-transcript", _write_transcript(tmp_path)])
    assert result.exit_code == 2


def test_policy_check_default_url_derived_from_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_config(monkeypatch, host="0.0.0.0", master_key="the-master-key")
    _stub_excerpt(monkeypatch)
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, **_k: Any) -> _FakeResponse:
        captured["url"] = request.full_url
        captured["auth_header"] = request.get_header("Otari-key")
        return _FakeResponse(200, {"policy": "p", "checked": True, "compliant": True, "violations": [], "guidance": ""})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = CliRunner().invoke(gateway_cli.policy, ["check", "p", "--claude-transcript", _write_transcript(tmp_path)])
    assert result.exit_code == 0
    # 0.0.0.0 is not connectable, so the derived default substitutes 127.0.0.1.
    assert captured["url"] == "http://127.0.0.1:8000/api/v1/plugins/agent-gates/policy-checks/p/check"
    assert captured["auth_header"] == "the-master-key"


def test_policy_check_url_and_api_key_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_config(monkeypatch)
    _stub_excerpt(monkeypatch)
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, **_k: Any) -> _FakeResponse:
        captured["url"] = request.full_url
        captured["auth_header"] = request.get_header("Otari-key")
        return _FakeResponse(200, {"policy": "p", "checked": True, "compliant": True, "violations": [], "guidance": ""})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = CliRunner().invoke(
        gateway_cli.policy,
        [
            "check",
            "p",
            "--claude-transcript",
            _write_transcript(tmp_path),
            "--url",
            "http://otari.example.com:9000",
            "--api-key",
            "override-key",
        ],
    )
    assert result.exit_code == 0
    assert captured["url"] == "http://otari.example.com:9000/api/v1/plugins/agent-gates/policy-checks/p/check"
    assert captured["auth_header"] == "override-key"


def test_policy_check_sends_the_transcripts_latest_entry_uuid_as_turn_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_config(monkeypatch)
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, **_k: Any) -> _FakeResponse:
        captured["body"] = json.loads(request.data.decode())
        return _FakeResponse(200, {"policy": "p", "checked": True, "compliant": True, "violations": [], "guidance": ""})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = CliRunner().invoke(
        gateway_cli.policy,
        [
            "check",
            "p",
            "--claude-transcript",
            _write_transcript_with_uuid(tmp_path, "the-latest-uuid"),
        ],
    )
    assert result.exit_code == 0
    assert captured["body"]["turn_id"] == "the-latest-uuid"


def test_policy_check_sends_the_current_branch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_config(monkeypatch)
    _stub_excerpt(monkeypatch)
    monkeypatch.setattr(gateway_cli, "_current_branch_label", lambda _path: "feature-branch")
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, **_k: Any) -> _FakeResponse:
        captured["body"] = json.loads(request.data.decode())
        return _FakeResponse(200, {"policy": "p", "checked": True, "compliant": True, "violations": [], "guidance": ""})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = CliRunner().invoke(
        gateway_cli.policy,
        ["check", "p", "--claude-transcript", _write_transcript(tmp_path)],
    )
    assert result.exit_code == 0
    assert captured["body"]["branch"] == "feature-branch"


def _write_transcript_with_bash_call(tmp_path: Path) -> str:
    path = tmp_path / "session.jsonl"
    entries = [
        {"type": "user", "message": {"role": "user", "content": "go"}},
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "make lint"}}],
            },
        },
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok", "is_error": False}],
            },
        },
    ]
    path.write_text("\n".join(json.dumps(entry) for entry in entries), encoding="utf-8")
    return str(path)


def test_policy_check_sends_executed_commands_extracted_from_the_transcript(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_config(monkeypatch)
    _stub_excerpt(monkeypatch)
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, **_k: Any) -> _FakeResponse:
        captured["body"] = json.loads(request.data.decode())
        return _FakeResponse(200, {"policy": "p", "checked": True, "compliant": True, "violations": [], "guidance": ""})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = CliRunner().invoke(
        gateway_cli.policy,
        ["check", "p", "--claude-transcript", _write_transcript_with_bash_call(tmp_path)],
    )
    assert result.exit_code == 0
    assert captured["body"]["executed_commands"] == [{"command": "make lint", "is_error": False}]


def _write_transcript_with_edit_and_nested_memory(tmp_path: Path) -> str:
    path = tmp_path / "session.jsonl"
    entries = [
        {"type": "attachment", "attachment": {"type": "nested_memory", "path": "/repo/web/AGENTS.md"}},
        {"type": "user", "message": {"role": "user", "content": "go"}},
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "t1",
                        "name": "Edit",
                        "input": {"file_path": "/repo/web/src/App.tsx"},
                    }
                ],
            },
        },
    ]
    path.write_text("\n".join(json.dumps(entry) for entry in entries), encoding="utf-8")
    return str(path)


def test_policy_check_sends_edited_and_loaded_context_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_config(monkeypatch)
    _stub_excerpt(monkeypatch)
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, **_k: Any) -> _FakeResponse:
        captured["body"] = json.loads(request.data.decode())
        return _FakeResponse(200, {"policy": "p", "checked": True, "compliant": True, "violations": [], "guidance": ""})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = CliRunner().invoke(
        gateway_cli.policy,
        ["check", "p", "--claude-transcript", _write_transcript_with_edit_and_nested_memory(tmp_path)],
    )
    assert result.exit_code == 0
    assert captured["body"]["edited_paths"] == ["/repo/web/src/App.tsx"]
    assert captured["body"]["loaded_context_paths"] == ["/repo/web/AGENTS.md"]


# --------------------------------------------------------------------------- #
# Repo-scoped gates file: --gates-file and auto-discovery (Phase 5)
# --------------------------------------------------------------------------- #

_GATES_YAML = """
on_unavailable: block
gates:
  - type: deterministic
    name: no-todo
    pattern: TODO
    mode: must_not_match
    message: no TODOs
"""


def _completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["git"], returncode=returncode, stdout=stdout, stderr="")


def test_current_branch_label_reads_abbrev_ref(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(argv: list[str], **_k: Any) -> subprocess.CompletedProcess[str]:
        assert argv[-2:] == ["--abbrev-ref", "HEAD"]
        return _completed("feature-branch\n")

    monkeypatch.setattr("otari_agent_gates.cli.subprocess.run", fake_run)
    monkeypatch.setattr("otari_agent_gates.cli.shutil.which", lambda _name: "/usr/bin/git")
    assert gateway_cli._current_branch_label(tmp_path) == "feature-branch"


def test_current_branch_label_treats_detached_head_as_unknown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("otari_agent_gates.cli.subprocess.run", lambda *_a, **_k: _completed("HEAD\n"))
    monkeypatch.setattr("otari_agent_gates.cli.shutil.which", lambda _name: "/usr/bin/git")
    assert gateway_cli._current_branch_label(tmp_path) is None


def test_current_branch_label_no_git_returns_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("otari_agent_gates.cli.shutil.which", lambda _name: None)
    assert gateway_cli._current_branch_label(tmp_path) is None


def test_git_toplevel_reads_show_toplevel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(argv: list[str], **_k: Any) -> subprocess.CompletedProcess[str]:
        assert argv[-1:] == ["--show-toplevel"]
        return _completed("/repo\n")

    monkeypatch.setattr("otari_agent_gates.cli.subprocess.run", fake_run)
    monkeypatch.setattr("otari_agent_gates.cli.shutil.which", lambda _name: "/usr/bin/git")
    assert gateway_cli._git_toplevel(tmp_path) == Path("/repo")


def test_git_toplevel_no_git_returns_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("otari_agent_gates.cli.shutil.which", lambda _name: None)
    assert gateway_cli._git_toplevel(tmp_path) is None


def test_relativize_paths_strips_the_repo_toplevel_prefix() -> None:
    paths = ["/repo/src/gateway/cli.py", "/repo/web/src/App.tsx"]
    assert gateway_cli._relativize_paths(paths, Path("/repo")) == [
        "src/gateway/cli.py",
        "web/src/App.tsx",
    ]


def test_relativize_paths_leaves_a_path_outside_the_toplevel_unchanged() -> None:
    paths = ["/elsewhere/file.py"]
    assert gateway_cli._relativize_paths(paths, Path("/repo")) == ["/elsewhere/file.py"]


def test_relativize_paths_passes_through_unchanged_when_toplevel_is_unknown() -> None:
    paths = ["/repo/src/gateway/cli.py"]
    assert gateway_cli._relativize_paths(paths, None) == paths


def testfind_gates_file_at_the_starting_directory(tmp_path: Path) -> None:
    (tmp_path / ".otari-gates.yml").write_text(_GATES_YAML, encoding="utf-8")
    assert gateway_cli.find_gates_file(tmp_path) == tmp_path / ".otari-gates.yml"


def testfind_gates_file_walks_upward(tmp_path: Path) -> None:
    (tmp_path / ".otari-gates.yml").write_text(_GATES_YAML, encoding="utf-8")
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    assert gateway_cli.find_gates_file(nested) == tmp_path / ".otari-gates.yml"


def testfind_gates_file_returns_none_when_absent(tmp_path: Path) -> None:
    assert gateway_cli.find_gates_file(tmp_path) is None


def test_policy_check_explicit_gates_file_sends_inline_spec(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_config(monkeypatch)
    _stub_excerpt(monkeypatch)
    gates_file = tmp_path / "repo-gates.yml"
    gates_file.write_text(_GATES_YAML, encoding="utf-8")
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, **_k: Any) -> _FakeResponse:
        captured["body"] = json.loads(request.data.decode())
        return _FakeResponse(
            200, {"policy": "my-repo", "checked": True, "compliant": True, "violations": [], "guidance": ""}
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = CliRunner().invoke(
        gateway_cli.policy,
        [
            "check",
            "my-repo",
            "--claude-transcript",
            _write_transcript(tmp_path),
            "--gates-file",
            str(gates_file),
        ],
    )
    assert result.exit_code == 0
    assert captured["body"]["spec"]["on_unavailable"] == "block"
    assert captured["body"]["spec"]["gates"][0]["name"] == "no-todo"


def test_policy_check_auto_discovers_gates_file_from_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_config(monkeypatch)
    _stub_excerpt(monkeypatch)
    (tmp_path / ".otari-gates.yml").write_text(_GATES_YAML, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, **_k: Any) -> _FakeResponse:
        captured["body"] = json.loads(request.data.decode())
        return _FakeResponse(
            200, {"policy": "my-repo", "checked": True, "compliant": True, "violations": [], "guidance": ""}
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = CliRunner().invoke(
        gateway_cli.policy, ["check", "my-repo", "--claude-transcript", _write_transcript(tmp_path)]
    )
    assert result.exit_code == 0
    assert "spec" in captured["body"]


def test_policy_check_with_no_gates_file_sends_no_inline_spec(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Baseline: with no --gates-file and none discoverable, the request looks exactly
    like it did before this feature - no `spec` key at all, so the server falls back to
    its config/DB lookup unchanged."""
    _stub_config(monkeypatch)
    _stub_excerpt(monkeypatch)
    monkeypatch.chdir(tmp_path)  # no .otari-gates.yml here
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, **_k: Any) -> _FakeResponse:
        captured["body"] = json.loads(request.data.decode())
        return _FakeResponse(200, {"policy": "p", "checked": True, "compliant": True, "violations": [], "guidance": ""})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = CliRunner().invoke(gateway_cli.policy, ["check", "p", "--claude-transcript", _write_transcript(tmp_path)])
    assert result.exit_code == 0
    assert "spec" not in captured["body"]


def test_policy_check_malformed_gates_file_exits_two_with_no_network_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_config(monkeypatch)
    _stub_excerpt(monkeypatch)
    gates_file = tmp_path / "bad-gates.yml"
    gates_file.write_text("gates: [{type: deterministic, name: x}]\n", encoding="utf-8")  # missing pattern/message

    def fail_if_called(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("urlopen should not be called for a gates file that fails validation")

    monkeypatch.setattr("urllib.request.urlopen", fail_if_called)

    result = CliRunner().invoke(
        gateway_cli.policy,
        [
            "check",
            "p",
            "--claude-transcript",
            _write_transcript(tmp_path),
            "--gates-file",
            str(gates_file),
        ],
    )
    assert result.exit_code == 2


# --------------------------------------------------------------------------- #
# policy generate
# --------------------------------------------------------------------------- #


def test_slugify() -> None:
    assert gateway_cli._slugify("A B") == "a-b"
    assert gateway_cli._slugify("") == "criterion"


def test_normalize_criteria_dedupes_slugs_and_caps_count() -> None:
    raw = [{"name": "A B", "description": "x"}, {"name": "A B", "description": "y"}, {"name": "C", "description": "z"}]
    criteria = gateway_cli._normalize_criteria(raw, max_criteria=2)
    assert [c.name for c in criteria] == ["a-b", "a-b-2"]


def test_normalize_criteria_rejects_non_list() -> None:
    assert gateway_cli._normalize_criteria({"not": "a list"}, max_criteria=10) == []


def test_normalize_criteria_accepts_a_well_formed_command_classification() -> None:
    raw = [
        {
            "name": "ran-lint",
            "description": "make lint was run and passed",
            "gate_type": "command",
            "pattern": "make lint",
            "mode": "must_run_and_succeed",
        }
    ]
    criteria = gateway_cli._normalize_criteria(raw, max_criteria=10)
    assert criteria == [
        gateway_cli.Criterion(
            name="ran-lint",
            description="make lint was run and passed",
            gate_type="command",
            pattern="make lint",
            mode="must_run_and_succeed",
        )
    ]


def test_normalize_criteria_accepts_a_command_classification_with_an_optional_paths_list() -> None:
    raw = [
        {
            "name": "web-lint",
            "description": "pnpm --dir web run lint was run for frontend changes",
            "gate_type": "command",
            "pattern": "pnpm --dir web run lint",
            "mode": "must_run_and_succeed",
            "paths": ["web/*"],
        }
    ]
    criteria = gateway_cli._normalize_criteria(raw, max_criteria=10)
    assert criteria[0].gate_type == "command"
    assert criteria[0].paths == ["web/*"]


def test_normalize_criteria_accepts_a_well_formed_scoped_guidance_classification() -> None:
    raw = [
        {
            "name": "web-agents-md",
            "description": "web/AGENTS.md read before editing the dashboard",
            "gate_type": "scoped_guidance",
            "directory": "web/",
        }
    ]
    criteria = gateway_cli._normalize_criteria(raw, max_criteria=10)
    assert criteria[0].gate_type == "scoped_guidance"
    assert criteria[0].directory == "web/"


def test_normalize_criteria_falls_back_to_llm_judge_when_a_mechanical_field_is_missing() -> None:
    """A command classification missing `pattern`/`mode` would silently mis-evaluate every
    run if trusted as-is - falls back to the always-valid llm_judge shape instead."""
    raw = [{"name": "ran-lint", "description": "make lint was run", "gate_type": "command"}]
    criteria = gateway_cli._normalize_criteria(raw, max_criteria=10)
    assert criteria == [gateway_cli.Criterion(name="ran-lint", description="make lint was run")]


def test_normalize_criteria_falls_back_to_llm_judge_for_an_unknown_gate_type() -> None:
    raw = [{"name": "a", "description": "b", "gate_type": "something_future_versions_might_add"}]
    criteria = gateway_cli._normalize_criteria(raw, max_criteria=10)
    assert criteria == [gateway_cli.Criterion(name="a", description="b")]


def test_render_policy_yaml_subscription_backend_omits_judge_model() -> None:
    criteria = [gateway_cli.Criterion(name="a", description="Never force-push.")]
    text = gateway_cli.render_policy_yaml(criteria, judge_backend="subscription")
    parsed = _load_yaml(text)
    gate = parsed["gates"][0]
    assert gate["judge_backend"] == "subscription"
    assert "judge_model" not in gate


def test_render_policy_yaml_provider_backend_includes_judge_model() -> None:
    criteria = [gateway_cli.Criterion(name="a", description="Never force-push.")]
    text = gateway_cli.render_policy_yaml(criteria, judge_backend="provider", judge_model="ollama:llama3.1")
    parsed = _load_yaml(text)
    gate = parsed["gates"][0]
    assert gate["judge_backend"] == "provider"
    assert gate["judge_model"] == "ollama:llama3.1"


def test_render_policy_yaml_renders_a_command_criterion_as_a_command_gate() -> None:
    criteria = [
        gateway_cli.Criterion(
            name="ran-lint",
            description="run make lint",
            gate_type="command",
            pattern="make lint",
            mode="must_run_and_succeed",
        )
    ]
    text = gateway_cli.render_policy_yaml(criteria)
    gate = _load_yaml(text)["gates"][0]
    assert gate == {
        "type": "command",
        "name": "ran-lint",
        "pattern": "make lint",
        "mode": "must_run_and_succeed",
        "message": "run make lint",
    }


def test_render_policy_yaml_renders_a_paths_conditioned_command_criterion() -> None:
    criteria = [
        gateway_cli.Criterion(
            name="web-lint",
            description="run pnpm --dir web run lint for frontend changes",
            gate_type="command",
            pattern="pnpm --dir web run lint",
            mode="must_run_and_succeed",
            paths=["web/*"],
        )
    ]
    text = gateway_cli.render_policy_yaml(criteria)
    gate = _load_yaml(text)["gates"][0]
    assert gate == {
        "type": "command",
        "name": "web-lint",
        "pattern": "pnpm --dir web run lint",
        "mode": "must_run_and_succeed",
        "paths": ["web/*"],
        "message": "run pnpm --dir web run lint for frontend changes",
    }


def test_render_policy_yaml_renders_a_scoped_guidance_criterion() -> None:
    criteria = [
        gateway_cli.Criterion(
            name="web-agents-md",
            description="read web/AGENTS.md first",
            gate_type="scoped_guidance",
            directory="web/",
        )
    ]
    text = gateway_cli.render_policy_yaml(criteria)
    gate = _load_yaml(text)["gates"][0]
    assert gate == {
        "type": "scoped_guidance",
        "name": "web-agents-md",
        "directory": "web/",
        "message": "read web/AGENTS.md first",
    }


def test_render_policy_yaml_renders_an_edited_path_criterion() -> None:
    criteria = [
        gateway_cli.Criterion(
            name="no-changelog-edits",
            description="do not hand-edit CHANGELOG.md",
            gate_type="edited_path",
            pattern="CHANGELOG.md",
            mode="must_not_edit",
        )
    ]
    text = gateway_cli.render_policy_yaml(criteria)
    gate = _load_yaml(text)["gates"][0]
    assert gate == {
        "type": "edited_path",
        "name": "no-changelog-edits",
        "pattern": "CHANGELOG.md",
        "mode": "must_not_edit",
        "message": "do not hand-edit CHANGELOG.md",
    }


def _load_yaml(text: str) -> Any:
    import yaml

    return yaml.safe_load(text)


def test_decompose_plan_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake_run(_prompt: str, **_kwargs: object) -> ClaudeHeadlessResult:
        calls["n"] += 1
        if calls["n"] == 1:
            return _fake_result("not json")
        return _fake_result(json.dumps([{"name": "a", "description": "b"}]))

    monkeypatch.setattr("otari_agent_gates.headless.run_claude_headless", fake_run)
    criteria = gateway_cli.decompose_plan("some plan text", max_criteria=5)
    assert criteria == [gateway_cli.Criterion(name="a", description="b")]
    assert calls["n"] == 2


def test_policy_generate_requires_judge_model_for_provider_backend(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.md"
    plan_path.write_text("# Plan\n", encoding="utf-8")
    result = CliRunner().invoke(gateway_cli.policy, ["generate", str(plan_path), "--judge-backend", "provider"])
    assert result.exit_code != 0


def test_policy_generate_writes_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan_path = tmp_path / "my-plan.md"
    plan_path.write_text("# Plan\n\nDo the thing.\n", encoding="utf-8")
    monkeypatch.setattr(
        "otari_agent_gates.headless.run_claude_headless",
        lambda *_a, **_k: _fake_result(json.dumps([{"name": "a", "description": "Do the thing."}])),
    )
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(gateway_cli.policy, ["generate", str(plan_path)])
    assert result.exit_code == 0

    yaml_out = tmp_path / ".otari-gates.yml"
    assert yaml_out.is_file()
    parsed = _load_yaml(yaml_out.read_text(encoding="utf-8"))
    gates = parsed["gates"]
    assert gates[0]["rules"] == "Do the thing."
    assert gates[0]["judge_backend"] == "subscription"


def test_policy_generate_writes_a_mechanical_gate_when_classified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_path = tmp_path / "my-plan.md"
    plan_path.write_text("# Plan\n\nAlways run make lint.\n", encoding="utf-8")
    monkeypatch.setattr(
        "otari_agent_gates.headless.run_claude_headless",
        lambda *_a, **_k: _fake_result(
            json.dumps(
                [
                    {
                        "name": "ran-lint",
                        "description": "make lint was run and passed",
                        "gate_type": "command",
                        "pattern": "make lint",
                        "mode": "must_run_and_succeed",
                    }
                ]
            )
        ),
    )
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(gateway_cli.policy, ["generate", str(plan_path)])
    assert result.exit_code == 0

    yaml_out = tmp_path / ".otari-gates.yml"
    gates = _load_yaml(yaml_out.read_text(encoding="utf-8"))["gates"]
    assert gates[0]["type"] == "command"
    assert gates[0]["pattern"] == "make lint"
    assert "judge_backend" not in gates[0]


def test_decomposition_prompt_forbids_double_star_globs() -> None:
    """`CommandGateSpec.paths` is matched with `fnmatch`, where `*` already crosses `/` and `**`
    is not "any depth" the way it is in a real .gitignore or a GitHub Actions workflow - a
    generated pattern like `web/**/*.ts`, written assuming GHA semantics, would silently never
    match a file directly under web/ itself. Regression test for that footgun: the prompt must
    keep telling the model not to do this, not just show a `["web/*"]` example and hope it infers
    the rule.
    """
    prompt = gateway_cli._DECOMPOSITION_PROMPT_TEMPLATE
    assert "never `**`" in prompt
    assert "web/**/*.ts" in prompt or "any depth" in prompt


def test_policy_generate_dry_run_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan_path = tmp_path / "my-plan.md"
    plan_path.write_text("# Plan\n", encoding="utf-8")
    monkeypatch.setattr(
        "otari_agent_gates.headless.run_claude_headless",
        lambda *_a, **_k: _fake_result(json.dumps([{"name": "a", "description": "d"}])),
    )

    result = CliRunner().invoke(gateway_cli.policy, ["generate", str(plan_path), "--dry-run"])
    assert result.exit_code == 0
    assert not (tmp_path / ".otari-gates.yml").exists()
    assert "a: d" in result.output


def test_policy_generate_missing_plan_file_errors() -> None:
    result = CliRunner().invoke(gateway_cli.policy, ["generate", "/nonexistent/plan.md"])
    assert result.exit_code != 0


def test_policy_give_up_sends_session_id_and_detected_repo_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_config(monkeypatch)
    monkeypatch.setattr(gateway_cli, "_git_toplevel", lambda _path: Path("/repo/otari"))
    monkeypatch.setattr(gateway_cli, "_current_branch_label", lambda _path: "feature-a")
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, **_k: Any) -> _FakeResponse:
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode())
        return _FakeResponse(204, {})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = CliRunner().invoke(gateway_cli.policy, ["give-up", "p", "--session-id", "sess-1"])
    assert result.exit_code == 0
    assert captured["url"].endswith("/api/v1/plugins/agent-gates/policy-checks/p/give-up")
    assert captured["body"] == {"session_id": "sess-1", "repo": "otari", "branch": "feature-a"}


def test_policy_give_up_requires_session_id() -> None:
    result = CliRunner().invoke(gateway_cli.policy, ["give-up", "p"])
    assert result.exit_code != 0


def test_policy_give_up_http_error_exits_two(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_config(monkeypatch)

    def fake_urlopen(*_a: Any, **_k: Any) -> Any:
        raise urllib.error.HTTPError("url", 404, "not found", None, io.BytesIO(b"{}"))  # type: ignore[arg-type]

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = CliRunner().invoke(gateway_cli.policy, ["give-up", "p", "--session-id", "sess-1"])
    assert result.exit_code == 2


def test_policy_give_up_connection_error_exits_two(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_config(monkeypatch)

    def fake_urlopen(*_a: Any, **_k: Any) -> Any:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = CliRunner().invoke(gateway_cli.policy, ["give-up", "p", "--session-id", "sess-1"])
    assert result.exit_code == 2
