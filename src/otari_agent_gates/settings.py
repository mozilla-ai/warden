"""The plugin's validated config block, set once by ``register`` and read by the service.

Module-level state on purpose: Otari hands a plugin its ``plugins.<name>`` block
once, at load time, and the routes and service run in the same process.
"""

from __future__ import annotations

from typing import Any

from otari_agent_gates.models import AgentGatesConfig

current = AgentGatesConfig()


def configure(raw: dict[str, Any]) -> AgentGatesConfig:
    """Validate ``raw`` (the ``plugins.agent-gates`` block) and make it the active config."""
    global current  # noqa: PLW0603
    current = AgentGatesConfig.model_validate(raw)
    return current
