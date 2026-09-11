"""Evaluate gates on inference traffic, through Otari's plugin traffic seam.

The Stop hook sees a turn after it ended, from the transcript on the developer's
machine. This sees the same turn on the wire: the agent's next request carries
every tool call it made and every result it got back, and the model's response
carries the tool call it wants to make next. Nothing is installed on the client,
and every agent that talks to its model through Otari is covered.

Only the mechanical gates run here, ``command`` and ``edited_path``: they need
what the wire carries and nothing else. A ``scoped_guidance`` gate needs the
loaded-context list, a ``deterministic`` gate the rendered transcript, and a
judge gate a model call per request, so those stay with the hook.

Decisions are recorded, not applied: Otari writes what this annotates onto the
usage row, and a ``deny`` is written there as ``would_deny``.
"""

from __future__ import annotations

import re
import time
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from gateway.plugins.api import RequestDecision, ToolCallDecision, logger

from otari_agent_gates import settings
from otari_agent_gates.models import CommandGateSpec, EditedPathGateSpec, PolicyCheckSpec
from otari_agent_gates.service import (
    ExecutedCommand,
    _command_gate_failed,
    _edited_path_gate_failed,
    path_matches_any_glob,
)
from otari_agent_gates.transcript import strip_inert_shell_regions

if TYPE_CHECKING:
    from gateway.plugins.api import RequestEvent, ToolCallEvent, Turn

_EDIT_TOOL_PATH_FIELDS = {"Edit": "file_path", "Write": "file_path", "NotebookEdit": "notebook_path"}
_SPEC_CACHE_SECONDS = 60.0


def _path_variants(path: str) -> list[str]:
    """The path as given plus every shorter suffix, so ``src/*`` matches ``/home/x/repo/src/a.py``.

    The wire does not say where the repository root is, so a gate's glob is
    tried against each suffix rather than requiring a relativized path.
    """
    parts = PurePosixPath(path.replace("\\", "/")).parts
    if parts and parts[0] == "/":
        parts = parts[1:]
    return ["/".join(parts[index:]) for index in range(len(parts))] or [path]


def _matches_any(path: str, patterns: list[str]) -> bool:
    return any(path_matches_any_glob(variant, patterns) for variant in _path_variants(path))


def _executed_commands(turn: Turn) -> list[ExecutedCommand]:
    results = {result.call_id: result for result in turn.results}
    commands: list[ExecutedCommand] = []
    for call in turn.tool_calls:
        if call.name != "Bash":
            continue
        command = call.arguments.get("command")
        if not isinstance(command, str):
            continue
        result = results.get(call.id)
        if result is None:
            # No result came back for it: it never ran, or ran outside this turn.
            continue
        commands.append(ExecutedCommand(command=strip_inert_shell_regions(command), is_error=result.is_error))
    return commands


def _edited_paths(turn: Turn) -> list[str]:
    paths: list[str] = []
    for call in turn.tool_calls:
        field = _EDIT_TOOL_PATH_FIELDS.get(call.name)
        if field is None:
            continue
        value = call.arguments.get(field)
        if isinstance(value, str) and value:
            paths.append(value)
    return paths


class _PathsAwareCommandGate:
    """A command gate whose ``paths`` condition is matched on path suffixes."""

    def __init__(self, gate: CommandGateSpec) -> None:
        self.gate = gate

    def failed(self, commands: list[ExecutedCommand], edited: list[str]) -> bool:
        gate = self.gate
        if gate.paths is not None and not any(_matches_any(path, gate.paths) for path in edited):
            return False
        return _command_gate_failed(gate.model_copy(update={"paths": None}), commands, edited)


class AgentGatesObserver:
    """The traffic observer ``register`` adds when the config names something to check."""

    def __init__(self) -> None:
        self._cached: tuple[float, str | None, PolicyCheckSpec | None] | None = None

    async def _spec(self) -> tuple[str | None, PolicyCheckSpec | None]:
        traffic = settings.current.traffic
        if traffic.gates:
            return None, PolicyCheckSpec(gates=traffic.gates)
        if not traffic.policy:
            return None, None
        now = time.monotonic()
        if self._cached is not None and now - self._cached[0] < _SPEC_CACHE_SECONDS:
            return self._cached[1], self._cached[2]
        spec = await _load_stored_policy(traffic.policy)
        self._cached = (now, traffic.policy, spec)
        return traffic.policy, spec

    async def on_request(self, event: RequestEvent) -> RequestDecision | None:
        turn = event.conversation.last_turn
        if turn is None or not turn.tool_calls:
            return None
        policy, spec = await self._spec()
        if spec is None:
            return None
        commands = _executed_commands(turn)
        edited = _edited_paths(turn)
        fired: list[str] = []
        messages: list[str] = []
        checked = 0
        for gate in spec.gates:
            if isinstance(gate, CommandGateSpec):
                checked += 1
                if _PathsAwareCommandGate(gate).failed(commands, edited):
                    fired.append(gate.name)
                    messages.append(gate.message)
            elif isinstance(gate, EditedPathGateSpec):
                checked += 1
                if _edited_path_gate_failed(gate, [variant for path in edited for variant in _path_variants(path)]):
                    fired.append(gate.name)
                    messages.append(gate.message)
        return RequestDecision(
            annotations={
                "policy": policy or "inline",
                "session": event.conversation.session_key,
                "checked": checked,
                "commands": len(commands),
                "fired": fired,
                "messages": messages,
            }
        )

    async def on_tool_call(self, event: ToolCallEvent) -> ToolCallDecision | None:
        if event.tool_call.name != "Bash":
            return None
        command = event.tool_call.arguments.get("command")
        if not isinstance(command, str):
            return None
        _, spec = await self._spec()
        if spec is None:
            return None
        stripped = strip_inert_shell_regions(command)
        for gate in spec.gates:
            if isinstance(gate, CommandGateSpec) and gate.mode == "must_not_run" and gate.paths is None:
                if re.search(gate.pattern, stripped):
                    return ToolCallDecision(deny=gate.message, annotations={"fired": [gate.name]})
        return None


async def _load_stored_policy(name: str) -> PolicyCheckSpec | None:
    """Read a stored policy on a session of the plugin's own; ``None`` when it cannot."""
    try:
        from gateway.core.database import create_session

        from otari_agent_gates.service import get_stored_policy_spec

        async with create_session() as db:
            return await get_stored_policy_spec(db, name)
    except Exception as error:  # noqa: BLE001 the seam fences this too, but say why in our own words
        logger.warning("agent-gates: stored policy %r unavailable for traffic checks: %s", name, error)
        return None


def annotations_summary(annotations: dict[str, Any]) -> str:
    """One line for a log or a listing: which gates fired, if any."""
    fired = annotations.get("fired") or []
    return f"{len(fired)} gate(s) fired: {', '.join(fired)}" if fired else "no gates fired"
