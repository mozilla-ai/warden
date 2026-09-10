"""The traffic observer: gates evaluated on what the wire carries."""

from __future__ import annotations

from typing import Any

import pytest
from gateway.plugins.traffic import (
    Caller,
    Conversation,
    RequestEvent,
    ToolCall,
    ToolCallEvent,
    ToolResult,
    Turn,
)

from otari_agent_gates import settings
from otari_agent_gates.models import PolicyCheckSpec
from otari_agent_gates.observer import AgentGatesObserver, _path_variants

CALLER = Caller(api_key_id="k", user_id="u", workspace_id="w", organization_id="o")

GATES: list[dict[str, Any]] = [
    {
        "type": "command",
        "name": "no-force-push",
        "pattern": r"git\s+push\b.*--force",
        "mode": "must_not_run",
        "message": "Never force-push.",
    },
    {
        "type": "command",
        "name": "tests-ran",
        "pattern": "pytest",
        "mode": "must_run_and_succeed",
        "paths": ["src/*"],
        "message": "Run pytest after editing src.",
    },
    {
        "type": "edited_path",
        "name": "claude-md-untouched",
        "pattern": r"CLAUDE\.md$",
        "mode": "must_not_edit",
        "message": "Never edit CLAUDE.md.",
    },
]


@pytest.fixture(autouse=True)
def _inline_gates() -> Any:
    settings.configure({"traffic": {"gates": GATES}})
    yield
    settings.configure({})


def _conversation(turn: Turn | None) -> Conversation:
    return Conversation(api="messages", model="m", system="", turns=(turn,) if turn else (), session_key="s-1")


def _bash(call_id: str, command: str) -> ToolCall:
    return ToolCall(id=call_id, name="Bash", arguments={"command": command})


@pytest.mark.asyncio
async def test_a_turn_with_no_tool_calls_is_not_judged() -> None:
    observer = AgentGatesObserver()

    assert await observer.on_request(RequestEvent(CALLER, _conversation(Turn(text="hi")))) is None
    assert await observer.on_request(RequestEvent(CALLER, _conversation(None))) is None


@pytest.mark.asyncio
async def test_a_force_push_that_ran_fires_the_gate() -> None:
    observer = AgentGatesObserver()
    turn = Turn(
        text="",
        tool_calls=(_bash("c1", "git push --force origin main"),),
        results=(ToolResult(call_id="c1", content="ok"),),
    )

    decision = await observer.on_request(RequestEvent(CALLER, _conversation(turn)))

    assert decision is not None
    assert decision.annotations["fired"] == ["no-force-push"]
    assert decision.annotations["messages"] == ["Never force-push."]
    assert decision.annotations["policy"] == "inline"
    assert decision.annotations["session"] == "s-1"
    assert decision.annotations["commands"] == 1


@pytest.mark.asyncio
async def test_a_call_with_no_result_never_ran() -> None:
    observer = AgentGatesObserver()
    turn = Turn(text="", tool_calls=(_bash("c1", "git push --force origin main"),), results=())

    decision = await observer.on_request(RequestEvent(CALLER, _conversation(turn)))

    assert decision is not None
    assert decision.annotations["fired"] == []
    assert decision.annotations["commands"] == 0


@pytest.mark.asyncio
async def test_paths_conditions_match_on_path_suffixes() -> None:
    observer = AgentGatesObserver()
    edit = ToolCall(id="e1", name="Edit", arguments={"file_path": "/home/dev/repo/src/app.py"})
    unrelated = Turn(text="", tool_calls=(edit, _bash("c1", "ls")), results=(ToolResult("c1", "a b"),))
    tested = Turn(
        text="",
        tool_calls=(edit, _bash("c1", "uv run pytest -q")),
        results=(ToolResult("c1", "2 passed"),),
    )

    without = await observer.on_request(RequestEvent(CALLER, _conversation(unrelated)))
    with_tests = await observer.on_request(RequestEvent(CALLER, _conversation(tested)))

    assert without is not None and without.annotations["fired"] == ["tests-ran"]
    assert with_tests is not None and with_tests.annotations["fired"] == []


@pytest.mark.asyncio
async def test_an_edited_path_gate_sees_absolute_paths() -> None:
    observer = AgentGatesObserver()
    turn = Turn(text="", tool_calls=(ToolCall("e1", "Write", {"file_path": "/repo/CLAUDE.md", "content": "x"}),))

    decision = await observer.on_request(RequestEvent(CALLER, _conversation(turn)))

    assert decision is not None
    assert decision.annotations["fired"] == ["claude-md-untouched"]


@pytest.mark.asyncio
async def test_a_proposed_force_push_is_denied_and_other_calls_pass() -> None:
    observer = AgentGatesObserver()
    conversation = _conversation(None)

    denied = await observer.on_tool_call(ToolCallEvent(CALLER, conversation, _bash("n1", "git push --force")))
    allowed = await observer.on_tool_call(ToolCallEvent(CALLER, conversation, _bash("n2", "git push")))
    not_bash = await observer.on_tool_call(ToolCallEvent(CALLER, conversation, ToolCall("n3", "Edit", {})))

    assert denied is not None and denied.deny == "Never force-push."
    assert denied.annotations == {"fired": ["no-force-push"]}
    assert allowed is None
    assert not_bash is None


@pytest.mark.asyncio
async def test_quoted_data_does_not_trigger_a_deny() -> None:
    observer = AgentGatesObserver()

    decision = await observer.on_tool_call(
        ToolCallEvent(CALLER, _conversation(None), _bash("n1", "echo 'never run git push --force'"))
    )

    assert decision is None


@pytest.mark.asyncio
async def test_nothing_configured_means_nothing_checked() -> None:
    settings.configure({})
    observer = AgentGatesObserver()
    turn = Turn(text="", tool_calls=(_bash("c1", "git push --force"),), results=(ToolResult("c1", "ok"),))

    assert await observer.on_request(RequestEvent(CALLER, _conversation(turn))) is None
    assert (
        await observer.on_tool_call(ToolCallEvent(CALLER, _conversation(None), _bash("n", "git push --force"))) is None
    )


@pytest.mark.asyncio
async def test_a_stored_policy_is_read_and_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    settings.configure({"traffic": {"policy": "team-rules"}})
    loads: list[str] = []

    async def fake_load(name: str) -> PolicyCheckSpec:
        loads.append(name)
        return PolicyCheckSpec.model_validate({"gates": GATES[:1]})

    monkeypatch.setattr("otari_agent_gates.observer._load_stored_policy", fake_load)
    observer = AgentGatesObserver()
    turn = Turn(text="", tool_calls=(_bash("c1", "git push --force"),), results=(ToolResult("c1", "ok"),))

    first = await observer.on_request(RequestEvent(CALLER, _conversation(turn)))
    second = await observer.on_request(RequestEvent(CALLER, _conversation(turn)))

    assert first is not None and first.annotations["policy"] == "team-rules"
    assert first.annotations["fired"] == ["no-force-push"]
    assert second is not None
    assert loads == ["team-rules"]


def test_path_variants_walk_the_suffixes() -> None:
    assert _path_variants("/home/dev/repo/src/app.py") == [
        "home/dev/repo/src/app.py",
        "dev/repo/src/app.py",
        "repo/src/app.py",
        "src/app.py",
        "app.py",
    ]
    assert _path_variants("src/app.py") == ["src/app.py", "app.py"]
