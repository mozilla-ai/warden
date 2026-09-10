"""Unit tests for the two-phase (deterministic then judge) gate evaluation."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from gateway.core.config import GatewayConfig
from sqlalchemy.exc import SQLAlchemyError

from otari_agent_gates import headless as claude_headless
from otari_agent_gates.headless import ClaudeCliCallError
from otari_agent_gates.models import (
    CommandGateSpec,
    DeterministicGateSpec,
    EditedPathGateSpec,
    JudgeGateSpec,
    PolicyCheckSpec,
    ScopedGuidanceGateSpec,
)
from otari_agent_gates.service import (
    ExecutedCommand,
    PolicyCheckUnavailableError,
    PolicyVerdict,
    check_policy_compliance,
    evaluate_policy,
    record_give_up,
    record_policy_check,
)

_JUDGE_GATE = JudgeGateSpec(
    name="agents-md-compliance",
    judge_model="ollama:llama3.1",
    rules="Never force-push.",
)
_JUDGE_GATE_2 = JudgeGateSpec(
    name="tests-required",
    judge_model="ollama:llama3.1",
    rules="Always add tests for new behavior.",
)
_SUBSCRIPTION_GATE = JudgeGateSpec(
    name="subscription-check",
    judge_backend="subscription",
    rules="Never force-push.",
)
_SUBSCRIPTION_GATE_2 = JudgeGateSpec(
    name="subscription-check-2",
    judge_backend="subscription",
    rules="Always add tests for new behavior.",
)


def _claude_result(
    text: str,
    *,
    total_cost_usd: float | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> claude_headless.ClaudeHeadlessResult:
    return claude_headless.ClaudeHeadlessResult(
        text=text,
        total_cost_usd=total_cost_usd,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=None,
        cache_creation_input_tokens=None,
    )


def _completion(verdict: PolicyVerdict) -> object:
    message = type("Message", (), {"parsed": verdict})()
    choice = type("Choice", (), {"message": message})()
    return type("Completion", (), {"choices": [choice]})()


@pytest.fixture
def config() -> GatewayConfig:
    return GatewayConfig()


@pytest.mark.asyncio
async def test_deterministic_gate_short_circuits_judge_call(config: GatewayConfig) -> None:
    spec = PolicyCheckSpec(
        gates=[
            DeterministicGateSpec(name="no-force-push", pattern="git push --force", message="no force push"),
            _JUDGE_GATE,
        ]
    )
    with patch("otari_agent_gates.service.acompletion", new_callable=AsyncMock) as mock_completion:
        verdict, gates = await check_policy_compliance(
            config, spec, policy_name="p", transcript_excerpt="ran: git push --force origin main"
        )
    assert verdict.compliant is False
    assert verdict.violations == ["no force push"]
    mock_completion.assert_not_called()

    # The run's own "jobs": the failed deterministic gate, and the judge gate
    # reported skipped rather than silently dropped from the list.
    assert len(gates) == 2
    deterministic, judge = gates
    assert deterministic.name == "no-force-push"
    assert deterministic.type == "deterministic"
    assert deterministic.passed is False
    assert deterministic.skipped is False
    assert deterministic.violations == ["no force push"]
    assert judge.name == _JUDGE_GATE.name
    assert judge.type == "llm_judge"
    assert judge.passed is False
    assert judge.skipped is True


@pytest.mark.asyncio
async def test_command_gate_short_circuits_judge_call(config: GatewayConfig) -> None:
    spec = PolicyCheckSpec(
        gates=[
            CommandGateSpec(name="ran-lint", pattern="make lint", message="run make lint"),
            _JUDGE_GATE,
        ]
    )
    with patch("otari_agent_gates.service.acompletion", new_callable=AsyncMock) as mock_completion:
        verdict, gates = await check_policy_compliance(
            config, spec, policy_name="p", transcript_excerpt="irrelevant", executed_commands=[]
        )
    assert verdict.compliant is False
    assert verdict.violations == ["run make lint"]
    mock_completion.assert_not_called()

    assert len(gates) == 2
    command, judge = gates
    assert command.name == "ran-lint"
    assert command.type == "command"
    assert command.passed is False
    assert command.skipped is False
    assert judge.skipped is True


@pytest.mark.asyncio
async def test_command_gate_must_run_and_succeed_passes_on_a_clean_run(config: GatewayConfig) -> None:
    spec = PolicyCheckSpec(gates=[CommandGateSpec(name="ran-lint", pattern="make lint", message="run make lint")])
    verdict, gates = await check_policy_compliance(
        config,
        spec,
        policy_name="p",
        transcript_excerpt="irrelevant",
        executed_commands=[ExecutedCommand(command="make lint 2>&1 | tail -20", is_error=False)],
    )
    assert verdict.compliant is True
    assert gates[0].passed is True


@pytest.mark.asyncio
async def test_command_gate_must_run_and_succeed_fails_when_the_command_errored(config: GatewayConfig) -> None:
    spec = PolicyCheckSpec(gates=[CommandGateSpec(name="ran-lint", pattern="make lint", message="run make lint")])
    verdict, gates = await check_policy_compliance(
        config,
        spec,
        policy_name="p",
        transcript_excerpt="irrelevant",
        executed_commands=[ExecutedCommand(command="make lint", is_error=True)],
    )
    assert verdict.compliant is False
    assert gates[0].passed is False


@pytest.mark.asyncio
async def test_command_gate_must_not_run_fails_even_if_the_command_errored(config: GatewayConfig) -> None:
    """`must_not_run` bans the attempt itself - unlike `must_run_and_succeed`, whether it
    errored is irrelevant. A failed `git push --force` still means the agent tried."""
    spec = PolicyCheckSpec(
        gates=[
            CommandGateSpec(
                name="no-force-push",
                pattern="git push --force",
                mode="must_not_run",
                message="never force-push",
            )
        ]
    )
    verdict, gates = await check_policy_compliance(
        config,
        spec,
        policy_name="p",
        transcript_excerpt="irrelevant",
        executed_commands=[ExecutedCommand(command="git push --force origin main", is_error=True)],
    )
    assert verdict.compliant is False
    assert gates[0].passed is False


@pytest.mark.asyncio
async def test_command_gate_ignores_the_pattern_merely_discussed_in_the_transcript(config: GatewayConfig) -> None:
    """The whole point of a command gate over a deterministic (transcript-text) one: it only
    looks at commands that actually ran, so text merely mentioning the banned string - the
    false-positive mode that got the old no-force-push deterministic gate removed - does not
    trip it."""
    spec = PolicyCheckSpec(
        gates=[
            CommandGateSpec(
                name="no-force-push",
                pattern="git push --force",
                mode="must_not_run",
                message="never force-push",
            )
        ]
    )
    verdict, gates = await check_policy_compliance(
        config,
        spec,
        policy_name="p",
        transcript_excerpt="ran: git push --force origin main",  # discussed in prose, never executed
        executed_commands=[ExecutedCommand(command="git status", is_error=False)],
    )
    assert verdict.compliant is True
    assert gates[0].passed is True


@pytest.mark.asyncio
async def test_command_gate_with_paths_passes_when_nothing_matched(
    config: GatewayConfig,
) -> None:
    """A paths-conditioned command gate only applies when a matching path was actually
    touched this turn - a backend-only turn must not be required to have run the frontend
    lint command."""
    gate = CommandGateSpec(
        name="web-lint",
        pattern="pnpm --dir web run lint",
        paths=["web/*"],
        message="run pnpm --dir web run lint for frontend changes",
    )
    verdict, gates = await check_policy_compliance(
        config,
        PolicyCheckSpec(gates=[gate]),
        policy_name="p",
        transcript_excerpt="irrelevant",
        executed_commands=[],
        edited_paths=["src/gateway/cli.py"],
    )
    assert verdict.compliant is True
    assert gates[0].passed is True


@pytest.mark.asyncio
async def test_command_gate_with_paths_fails_when_matched_but_command_never_ran(
    config: GatewayConfig,
) -> None:
    gate = CommandGateSpec(
        name="web-lint",
        pattern="pnpm --dir web run lint",
        paths=["web/*"],
        message="run pnpm --dir web run lint for frontend changes",
    )
    verdict, gates = await check_policy_compliance(
        config,
        PolicyCheckSpec(gates=[gate]),
        policy_name="p",
        transcript_excerpt="irrelevant",
        executed_commands=[],
        edited_paths=["web/src/App.tsx"],
    )
    assert verdict.compliant is False
    assert gates[0].passed is False


@pytest.mark.asyncio
async def test_command_gate_with_paths_passes_when_matched_and_command_ran(
    config: GatewayConfig,
) -> None:
    gate = CommandGateSpec(
        name="web-lint",
        pattern="pnpm --dir web run lint",
        paths=["web/*"],
        message="run pnpm --dir web run lint for frontend changes",
    )
    verdict, gates = await check_policy_compliance(
        config,
        PolicyCheckSpec(gates=[gate]),
        policy_name="p",
        transcript_excerpt="irrelevant",
        executed_commands=[ExecutedCommand(command="pnpm --dir web run lint", is_error=False)],
        edited_paths=["web/src/App.tsx"],
    )
    assert verdict.compliant is True
    assert gates[0].passed is True


@pytest.mark.asyncio
async def test_command_gate_with_paths_matches_any_of_multiple_patterns(
    config: GatewayConfig,
) -> None:
    gate = CommandGateSpec(
        name="lint",
        pattern="make lint",
        paths=["src/gateway/*", "tests/*", "scripts/*"],
        message="run make lint",
    )
    verdict, gates = await check_policy_compliance(
        config,
        PolicyCheckSpec(gates=[gate]),
        policy_name="p",
        transcript_excerpt="irrelevant",
        executed_commands=[],
        edited_paths=["tests/unit/test_cli_policy.py"],
    )
    assert verdict.compliant is False
    assert gates[0].passed is False


_SCOPED_GATE = ScopedGuidanceGateSpec(
    name="web-agents-md", directory="web/", message="read web/AGENTS.md before editing the dashboard"
)


@pytest.mark.asyncio
async def test_scoped_guidance_gate_passes_when_nothing_in_the_directory_was_touched(config: GatewayConfig) -> None:
    verdict, gates = await check_policy_compliance(
        config,
        PolicyCheckSpec(gates=[_SCOPED_GATE]),
        policy_name="p",
        transcript_excerpt="irrelevant",
        edited_paths=["src/gateway/cli.py"],
        loaded_context_paths=[],
    )
    assert verdict.compliant is True
    assert gates[0].passed is True


@pytest.mark.asyncio
async def test_scoped_guidance_gate_fails_when_the_directory_was_touched_but_not_loaded(
    config: GatewayConfig,
) -> None:
    verdict, gates = await check_policy_compliance(
        config,
        PolicyCheckSpec(gates=[_SCOPED_GATE]),
        policy_name="p",
        transcript_excerpt="irrelevant",
        edited_paths=["web/src/features/policies/GateForm.tsx"],
        loaded_context_paths=[],
    )
    assert verdict.compliant is False
    assert gates[0].passed is False


@pytest.mark.asyncio
async def test_scoped_guidance_gate_passes_when_loaded_earlier_in_the_session(config: GatewayConfig) -> None:
    """`loaded_context_paths` is session-wide, not turn-scoped - a load from many turns ago
    still counts, matching how Claude Code's own nested_memory injection actually behaves."""
    verdict, gates = await check_policy_compliance(
        config,
        PolicyCheckSpec(gates=[_SCOPED_GATE]),
        policy_name="p",
        transcript_excerpt="irrelevant",
        edited_paths=["web/src/features/policies/GateForm.tsx"],
        loaded_context_paths=["web/AGENTS.md"],
    )
    assert verdict.compliant is True
    assert gates[0].passed is True


_EDITED_PATH_GATE = EditedPathGateSpec(
    name="no-changelog-edits", pattern="CHANGELOG.md", message="CHANGELOG.md is regenerated, not hand-edited"
)


@pytest.mark.asyncio
async def test_edited_path_gate_must_not_edit_passes_when_the_path_is_untouched(config: GatewayConfig) -> None:
    verdict, gates = await check_policy_compliance(
        config,
        PolicyCheckSpec(gates=[_EDITED_PATH_GATE]),
        policy_name="p",
        transcript_excerpt="irrelevant",
        edited_paths=["/repo/src/gateway/cli.py"],
    )
    assert verdict.compliant is True
    assert gates[0].passed is True


@pytest.mark.asyncio
async def test_edited_path_gate_must_not_edit_fails_when_the_path_was_touched(config: GatewayConfig) -> None:
    verdict, gates = await check_policy_compliance(
        config,
        PolicyCheckSpec(gates=[_EDITED_PATH_GATE]),
        policy_name="p",
        transcript_excerpt="irrelevant",
        edited_paths=["/repo/CHANGELOG.md"],
    )
    assert verdict.compliant is False
    assert gates[0].passed is False


@pytest.mark.asyncio
async def test_edited_path_gate_must_edit_fails_unless_the_path_was_touched(config: GatewayConfig) -> None:
    gate = EditedPathGateSpec(name="e", pattern="AGENTS.md", mode="must_edit", message="must update AGENTS.md")
    verdict, gates = await check_policy_compliance(
        config,
        PolicyCheckSpec(gates=[gate]),
        policy_name="p",
        transcript_excerpt="irrelevant",
        edited_paths=["/repo/src/gateway/cli.py"],
    )
    assert verdict.compliant is False
    assert gates[0].passed is False


@pytest.mark.asyncio
async def test_judge_gate_runs_when_deterministic_gates_pass(config: GatewayConfig) -> None:
    spec = PolicyCheckSpec(
        gates=[
            DeterministicGateSpec(name="no-force-push", pattern="git push --force", message="no force push"),
            _JUDGE_GATE,
        ]
    )
    expected = PolicyVerdict(compliant=False, violations=["skipped a rule"], guidance="do the thing")
    with patch("otari_agent_gates.service.acompletion", new_callable=AsyncMock) as mock_completion:
        mock_completion.return_value = _completion(expected)
        verdict, gates = await check_policy_compliance(
            config, spec, policy_name="p", transcript_excerpt="all good here"
        )
    assert verdict == expected
    mock_completion.assert_called_once()

    deterministic, judge = gates
    assert deterministic.passed is True
    assert deterministic.skipped is False
    assert judge.name == _JUDGE_GATE.name
    assert judge.passed is False
    assert judge.skipped is False
    assert judge.violations == ["skipped a rule"]
    assert judge.guidance == "do the thing"


@pytest.mark.asyncio
async def test_judge_retries_once_then_succeeds(config: GatewayConfig) -> None:
    spec = PolicyCheckSpec(gates=[_JUDGE_GATE])
    ok = PolicyVerdict(compliant=True)
    with patch("otari_agent_gates.service.acompletion", new_callable=AsyncMock) as mock_completion:
        mock_completion.side_effect = [RuntimeError("boom"), _completion(ok)]
        verdict, gates = await check_policy_compliance(config, spec, policy_name="p", transcript_excerpt="text")
    assert verdict.compliant is True
    assert len(gates) == 1
    assert gates[0].name == _JUDGE_GATE.name
    assert gates[0].passed is True
    assert gates[0].violations == []
    assert mock_completion.call_count == 2


@pytest.mark.asyncio
async def test_judge_gates_aggregate_violations_from_all_gates(config: GatewayConfig) -> None:
    spec = PolicyCheckSpec(gates=[_JUDGE_GATE, _JUDGE_GATE_2])
    verdict_1 = PolicyVerdict(compliant=False, violations=["force-pushed"], guidance="don't force-push")
    verdict_2 = PolicyVerdict(compliant=False, violations=["no tests added"], guidance="add tests")
    with patch("otari_agent_gates.service.acompletion", new_callable=AsyncMock) as mock_completion:
        mock_completion.side_effect = [_completion(verdict_1), _completion(verdict_2)]
        verdict, gates = await check_policy_compliance(config, spec, policy_name="p", transcript_excerpt="text")
    assert verdict.compliant is False
    assert set(verdict.violations) == {"force-pushed", "no tests added"}
    assert "don't force-push" in verdict.guidance
    assert "add tests" in verdict.guidance
    assert mock_completion.call_count == 2

    # Each judge gate's own outcome is attributed to it by name, not flattened
    # away - this is the whole point of the gates list.
    by_name = {gate.name: gate for gate in gates}
    assert by_name[_JUDGE_GATE.name].violations == ["force-pushed"]
    assert by_name[_JUDGE_GATE_2.name].violations == ["no tests added"]
    assert all(not gate.passed for gate in gates)


@pytest.mark.asyncio
async def test_judge_gates_all_compliant_returns_compliant(config: GatewayConfig) -> None:
    spec = PolicyCheckSpec(gates=[_JUDGE_GATE, _JUDGE_GATE_2])
    ok = PolicyVerdict(compliant=True)
    with patch("otari_agent_gates.service.acompletion", new_callable=AsyncMock) as mock_completion:
        mock_completion.side_effect = [_completion(ok), _completion(ok)]
        verdict, gates = await check_policy_compliance(config, spec, policy_name="p", transcript_excerpt="text")
    assert verdict.compliant is True
    assert verdict.violations == []
    assert mock_completion.call_count == 2
    assert all(gate.passed for gate in gates)


@pytest.mark.asyncio
async def test_judge_raises_unavailable_after_two_failures(config: GatewayConfig) -> None:
    spec = PolicyCheckSpec(gates=[_JUDGE_GATE])
    with patch("otari_agent_gates.service.acompletion", new_callable=AsyncMock) as mock_completion:
        mock_completion.side_effect = RuntimeError("boom")
        with pytest.raises(PolicyCheckUnavailableError) as exc_info:
            await check_policy_compliance(config, spec, policy_name="p", transcript_excerpt="text")
    assert mock_completion.call_count == 2
    assert exc_info.value.public_detail == "policy check 'p' could not be evaluated"


@pytest.mark.asyncio
async def test_subscription_judge_gate_happy_path(config: GatewayConfig) -> None:
    spec = PolicyCheckSpec(gates=[_SUBSCRIPTION_GATE])
    with patch("otari_agent_gates.headless.run_claude_headless") as mock_run:
        mock_run.return_value = _claude_result(
            '{"compliant": false, "violations": ["force-pushed"], "guidance": "don\'t"}',
            total_cost_usd=0.0077,
            input_tokens=10,
            output_tokens=40,
        )
        verdict, gates = await check_policy_compliance(config, spec, policy_name="p", transcript_excerpt="text")
    assert verdict.compliant is False
    assert verdict.violations == ["force-pushed"]
    mock_run.assert_called_once()
    assert gates[0].passed is False
    assert gates[0].violations == ["force-pushed"]
    assert gates[0].total_cost_usd == 0.0077
    assert gates[0].input_tokens == 10
    assert gates[0].output_tokens == 40


@pytest.mark.asyncio
async def test_subscription_judge_gate_defaults_to_the_small_model(config: GatewayConfig) -> None:
    """No judge_model set: falls back to DEFAULT_SUBSCRIPTION_MODEL, not whatever `claude`
    would otherwise pick - judging one rule is a narrow task and every gate is a real
    subscription call, so the default should be the model this needs the least of."""
    spec = PolicyCheckSpec(gates=[_SUBSCRIPTION_GATE])
    with patch("otari_agent_gates.headless.run_claude_headless") as mock_run:
        mock_run.return_value = _claude_result('{"compliant": true}')
        await check_policy_compliance(config, spec, policy_name="p", transcript_excerpt="text")
    assert mock_run.call_args.kwargs["model"] == claude_headless.DEFAULT_SUBSCRIPTION_MODEL


@pytest.mark.asyncio
async def test_subscription_judge_gate_honors_an_explicit_model(config: GatewayConfig) -> None:
    gate = JudgeGateSpec(name="s", judge_backend="subscription", judge_model="sonnet", rules="Never force-push.")
    spec = PolicyCheckSpec(gates=[gate])
    with patch("otari_agent_gates.headless.run_claude_headless") as mock_run:
        mock_run.return_value = _claude_result('{"compliant": true}')
        await check_policy_compliance(config, spec, policy_name="p", transcript_excerpt="text")
    assert mock_run.call_args.kwargs["model"] == "sonnet"


@pytest.mark.asyncio
async def test_subscription_judge_gate_retries_on_malformed_reply(config: GatewayConfig) -> None:
    spec = PolicyCheckSpec(gates=[_SUBSCRIPTION_GATE])
    with patch("otari_agent_gates.headless.run_claude_headless") as mock_run:
        mock_run.side_effect = [_claude_result("not json"), _claude_result('{"compliant": true}')]
        verdict, gates = await check_policy_compliance(config, spec, policy_name="p", transcript_excerpt="text")
    assert verdict.compliant is True
    assert mock_run.call_count == 2
    assert gates[0].passed is True


@pytest.mark.asyncio
async def test_subscription_judge_gate_unavailable_after_two_failures(config: GatewayConfig) -> None:
    spec = PolicyCheckSpec(gates=[_SUBSCRIPTION_GATE])
    with patch("otari_agent_gates.headless.run_claude_headless") as mock_run:
        mock_run.side_effect = ClaudeCliCallError("claude exited 1")
        with pytest.raises(PolicyCheckUnavailableError):
            await check_policy_compliance(config, spec, policy_name="p", transcript_excerpt="text")
    assert mock_run.call_count == 2


@pytest.mark.asyncio
async def test_subscription_judge_gates_run_concurrently_not_sequentially(config: GatewayConfig) -> None:
    """`run_claude_headless` is plain synchronous code around a blocking `subprocess.run`.
    Calling it inline inside the coroutine `asyncio.gather` schedules would block the event
    loop and defeat that concurrency, serializing every subscription-backend judge gate
    despite `gather` - the exact regression this test pins. Each mocked call blocks its
    thread for `_SLEEP_SECONDS`; if the two gates truly overlap the whole check takes about
    one sleep, not the sum of two.
    """
    _SLEEP_SECONDS = 0.2
    spec = PolicyCheckSpec(gates=[_SUBSCRIPTION_GATE, _SUBSCRIPTION_GATE_2])

    def _blocking_compliant_reply(*_args: object, **_kwargs: object) -> claude_headless.ClaudeHeadlessResult:
        time.sleep(_SLEEP_SECONDS)
        return _claude_result('{"compliant": true}')

    with patch("otari_agent_gates.headless.run_claude_headless", side_effect=_blocking_compliant_reply):
        started_at = time.monotonic()
        verdict, _gates = await check_policy_compliance(config, spec, policy_name="p", transcript_excerpt="text")
        elapsed = time.monotonic() - started_at

    assert verdict.compliant is True
    assert elapsed < _SLEEP_SECONDS * 1.5, (
        f"took {elapsed:.2f}s for two {_SLEEP_SECONDS}s gates - ran sequentially, not concurrently"
    )


@pytest.mark.asyncio
async def test_mixed_backend_gates_aggregate_across_both(config: GatewayConfig) -> None:
    spec = PolicyCheckSpec(gates=[_JUDGE_GATE, _SUBSCRIPTION_GATE])
    provider_verdict = PolicyVerdict(compliant=False, violations=["provider-side finding"], guidance="fix provider")
    with (
        patch("otari_agent_gates.service.acompletion", new_callable=AsyncMock) as mock_completion,
        patch("otari_agent_gates.headless.run_claude_headless") as mock_run,
    ):
        mock_completion.return_value = _completion(provider_verdict)
        mock_run.return_value = _claude_result(
            '{"compliant": false, "violations": ["subscription-side finding"], "guidance": "fix sub"}'
        )
        verdict, gates = await check_policy_compliance(config, spec, policy_name="p", transcript_excerpt="text")
    assert verdict.compliant is False
    assert set(verdict.violations) == {"provider-side finding", "subscription-side finding"}
    mock_completion.assert_called_once()
    mock_run.assert_called_once()

    by_name = {gate.name: gate for gate in gates}
    assert by_name[_JUDGE_GATE.name].violations == ["provider-side finding"]
    assert by_name[_SUBSCRIPTION_GATE.name].violations == ["subscription-side finding"]


@pytest.mark.asyncio
async def test_evaluate_policy_block_reraises(config: GatewayConfig) -> None:
    spec = PolicyCheckSpec(gates=[_JUDGE_GATE], on_unavailable="block")
    with patch("otari_agent_gates.service.acompletion", new_callable=AsyncMock) as mock_completion:
        mock_completion.side_effect = RuntimeError("boom")
        with pytest.raises(PolicyCheckUnavailableError):
            await evaluate_policy(config, spec, policy_name="p", transcript_excerpt="text")


@pytest.mark.asyncio
async def test_evaluate_policy_monitor_falls_back(config: GatewayConfig) -> None:
    spec = PolicyCheckSpec(gates=[_JUDGE_GATE], on_unavailable="monitor")
    with patch("otari_agent_gates.service.acompletion", new_callable=AsyncMock) as mock_completion:
        mock_completion.side_effect = RuntimeError("boom")
        result = await evaluate_policy(config, spec, policy_name="p", transcript_excerpt="text")
    assert result == {
        "policy": "p",
        "checked": False,
        "compliant": True,
        "violations": [],
        "guidance": "policy check unavailable; treated as passing (on_unavailable=monitor)",
        "gates": [],
    }


@pytest.mark.asyncio
async def test_evaluate_policy_happy_path(config: GatewayConfig) -> None:
    spec = PolicyCheckSpec(gates=[_JUDGE_GATE])
    verdict = PolicyVerdict(compliant=False, violations=["v"], guidance="g")
    with patch("otari_agent_gates.service.acompletion", new_callable=AsyncMock) as mock_completion:
        mock_completion.return_value = _completion(verdict)
        result = await evaluate_policy(config, spec, policy_name="p", transcript_excerpt="text")
    assert result["policy"] == "p"
    assert result["checked"] is True
    assert result["compliant"] is False
    assert result["violations"] == ["v"]
    assert result["guidance"] == "g"
    assert len(result["gates"]) == 1
    assert result["gates"][0]["name"] == _JUDGE_GATE.name
    assert result["gates"][0]["passed"] is False


@pytest.mark.asyncio
async def test_record_policy_check_inserts_a_row() -> None:
    db = AsyncMock()
    db.add = MagicMock()
    result = {
        "policy": "p",
        "checked": True,
        "compliant": False,
        "violations": ["v"],
        "guidance": "g",
        "gates": [{"name": "g1", "type": "deterministic", "passed": False, "skipped": False, "violations": ["v"]}],
    }

    await record_policy_check(db, policy_name="p", session_id="s1", result=result)

    db.add.assert_called_once()
    added = db.add.call_args.args[0]
    assert added.policy_name == "p"
    assert added.session_id == "s1"
    assert added.checked is True
    assert added.compliant is False
    assert added.violations == ["v"]
    assert added.guidance == "g"
    assert added.gates == result["gates"]
    db.commit.assert_awaited_once()
    db.rollback.assert_not_called()


@pytest.mark.asyncio
async def test_record_policy_check_stores_branch_and_aggregates_gate_usage() -> None:
    db = AsyncMock()
    db.add = MagicMock()
    result = {
        "policy": "p",
        "checked": True,
        "compliant": False,
        "violations": ["v"],
        "guidance": "g",
        "gates": [
            {
                "name": "g1",
                "type": "llm_judge",
                "passed": False,
                "skipped": False,
                "violations": ["v"],
                "total_cost_usd": 0.005,
                "input_tokens": 100,
                "output_tokens": 20,
            },
            {
                "name": "g2",
                "type": "llm_judge",
                "passed": True,
                "skipped": False,
                "violations": [],
                "total_cost_usd": 0.002,
                "input_tokens": 50,
                "output_tokens": 10,
            },
            {"name": "g3", "type": "deterministic", "passed": True, "skipped": False, "violations": []},
        ],
    }

    await record_policy_check(db, policy_name="p", session_id="s1", branch="my-branch", result=result)

    added = db.add.call_args.args[0]
    assert added.branch == "my-branch"
    assert added.total_cost_usd == pytest.approx(0.007)
    assert added.total_input_tokens == 150
    assert added.total_output_tokens == 30


@pytest.mark.asyncio
async def test_record_policy_check_leaves_usage_null_when_no_gate_reported_any() -> None:
    db = AsyncMock()
    db.add = MagicMock()
    result = {
        "policy": "p",
        "checked": True,
        "compliant": True,
        "violations": [],
        "guidance": "",
        "gates": [{"name": "g1", "type": "deterministic", "passed": True, "skipped": False, "violations": []}],
    }

    await record_policy_check(db, policy_name="p", session_id="s1", result=result)

    added = db.add.call_args.args[0]
    assert added.total_cost_usd is None
    assert added.total_input_tokens is None
    assert added.total_output_tokens is None


@pytest.mark.asyncio
async def test_record_policy_check_swallows_db_errors() -> None:
    db = AsyncMock()
    db.add = MagicMock()
    db.commit.side_effect = SQLAlchemyError("boom")
    result = {"policy": "p", "checked": True, "compliant": True, "violations": [], "guidance": "", "gates": []}

    # Must not raise.
    await record_policy_check(db, policy_name="p", session_id=None, result=result)

    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_give_up_inserts_a_terminal_marker() -> None:
    db = AsyncMock()
    db.add = MagicMock()

    await record_give_up(db, policy_name="p", session_id="s1", repo="otari", branch="feature-a")

    db.add.assert_called_once()
    added = db.add.call_args.args[0]
    assert added.policy_name == "p"
    assert added.session_id == "s1"
    assert added.repo == "otari"
    assert added.branch == "feature-a"
    assert added.checked is True
    assert added.compliant is False
    assert added.violations == []
    assert added.gates is None
    assert added.gave_up is True
    db.commit.assert_awaited_once()
    db.rollback.assert_not_called()


@pytest.mark.asyncio
async def test_record_give_up_swallows_db_errors() -> None:
    db = AsyncMock()
    db.add = MagicMock()
    db.commit.side_effect = SQLAlchemyError("boom")

    # Must not raise.
    await record_give_up(db, policy_name="p", session_id="s1", repo=None, branch=None)

    db.rollback.assert_awaited_once()
