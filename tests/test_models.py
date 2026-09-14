"""Unit tests for `PolicyCheckSpec` / gate validation - fail closed at config-load time."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from otari_warden.models import (
    CommandGateSpec,
    DeterministicGateSpec,
    EditedPathGateSpec,
    GateSpec,
    JudgeGateSpec,
    PolicyCheckSpec,
    ScopedGuidanceGateSpec,
)


def test_judge_gate_rejects_both_rules_and_rules_file() -> None:
    with pytest.raises(ValidationError, match="exactly one of"):
        JudgeGateSpec(name="a", judge_model="ollama:llama3.1", rules="text", rules_file="AGENTS.md")


def test_judge_gate_rejects_neither_rules_nor_rules_file() -> None:
    with pytest.raises(ValidationError, match="exactly one of"):
        JudgeGateSpec(name="a", judge_model="ollama:llama3.1")


def test_judge_gate_rejects_missing_rules_file(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.md"
    with pytest.raises(ValidationError, match="does not exist"):
        JudgeGateSpec(name="a", judge_model="ollama:llama3.1", rules_file=str(missing))


def test_judge_gate_reads_rules_file(tmp_path: Path) -> None:
    rules_file = tmp_path / "AGENTS.md"
    rules_file.write_text("Never force-push.\n", encoding="utf-8")
    gate = JudgeGateSpec(name="a", judge_model="ollama:llama3.1", rules_file=str(rules_file))
    assert gate.rules == "Never force-push."


def test_judge_gate_provider_backend_requires_judge_model() -> None:
    with pytest.raises(ValidationError, match="judge_model is required"):
        JudgeGateSpec(name="a", rules="text")


def test_judge_gate_subscription_backend_accepts_an_explicit_model() -> None:
    """judge_model on a subscription gate picks the local claude CLI's own --model,
    not a resolved provider - allowed, not required, unlike the provider backend."""
    gate = JudgeGateSpec(name="a", judge_backend="subscription", judge_model="sonnet", rules="text")
    assert gate.judge_model == "sonnet"


def test_judge_gate_subscription_backend_needs_no_judge_model() -> None:
    gate = JudgeGateSpec(name="a", judge_backend="subscription", rules="text")
    assert gate.judge_model is None


def test_policy_requires_at_least_one_gate() -> None:
    with pytest.raises(ValidationError):
        PolicyCheckSpec(gates=[])


def test_gate_list_parses_mixed_discriminated_union() -> None:
    spec = PolicyCheckSpec.model_validate(
        {
            "gates": [
                {"type": "deterministic", "name": "a", "pattern": "x", "message": "no x"},
                {"type": "command", "name": "c", "pattern": "make lint", "message": "run make lint"},
                {"type": "edited_path", "name": "e", "pattern": "CHANGELOG.md", "message": "no hand edits"},
                {"type": "llm_judge", "name": "b", "judge_model": "ollama:llama3.1", "rules": "r"},
            ]
        }
    )
    assert isinstance(spec.gates[0], DeterministicGateSpec)
    assert isinstance(spec.gates[1], CommandGateSpec)
    assert isinstance(spec.gates[2], EditedPathGateSpec)
    assert isinstance(spec.gates[3], JudgeGateSpec)


def test_command_gate_defaults_to_must_run_and_succeed() -> None:
    gate = CommandGateSpec(name="c", pattern="make lint", message="run make lint")
    assert gate.mode == "must_run_and_succeed"


def test_command_gate_paths_defaults_to_unconditional() -> None:
    gate = CommandGateSpec(name="c", pattern="make lint", message="run make lint")
    assert gate.paths is None


def test_command_gate_accepts_an_optional_paths_list() -> None:
    gate = CommandGateSpec(name="c", pattern="pnpm run lint", paths=["web/*"], message="run pnpm lint")
    assert gate.paths == ["web/*"]


def test_scoped_guidance_gate_parses() -> None:
    spec = PolicyCheckSpec.model_validate(
        {
            "gates": [
                {
                    "type": "scoped_guidance",
                    "name": "web-agents-md",
                    "directory": "web/",
                    "message": "read web/AGENTS.md before editing the dashboard",
                }
            ]
        }
    )
    assert isinstance(spec.gates[0], ScopedGuidanceGateSpec)
    assert spec.gates[0].directory == "web/"


def test_edited_path_gate_defaults_to_must_not_edit() -> None:
    gate = EditedPathGateSpec(name="e", pattern="CHANGELOG.md", message="do not hand-edit CHANGELOG.md")
    assert gate.mode == "must_not_edit"


def test_gate_type_field_rejects_unknown_discriminator() -> None:
    adapter: TypeAdapter[GateSpec] = TypeAdapter(GateSpec)
    with pytest.raises(ValidationError):
        adapter.validate_python({"type": "regex", "name": "a", "pattern": "x", "message": "no x"})
