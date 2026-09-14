"""The plugin's validated config block, set once by ``register`` and read by the service.

Module-level state on purpose: Otari hands a plugin its ``plugins.<name>`` block
once, at load time, and the routes and service run in the same process.
"""

from __future__ import annotations

from typing import Any

from otari_warden.models import WardenConfig

current = WardenConfig()


def configure(raw: dict[str, Any]) -> WardenConfig:
    """Validate ``raw`` (the ``plugins.warden`` block) and make it the active config."""
    global current  # noqa: PLW0603
    current = WardenConfig.model_validate(raw)
    return current
