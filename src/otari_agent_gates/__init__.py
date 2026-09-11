"""Agent Gates: an Otari plugin that checks a coding agent's turn against a repo's stated rules.

Otari discovers this package through the ``otari.plugins`` entry point (or a
drop-in copy in its plugins directory), reads ``otari-plugin.toml``, and calls
``register``. Everything the plugin contributes goes through the context it is
handed: two routers under ``/api/v1/plugins/agent-gates``, the ``otari policy``
command group, a migration directory run against the plugin's own version
table, and a traffic observer. The ``plugins.agent-gates`` config block is
validated here and kept in ``otari_agent_gates.settings`` for the service to
read; a dashboard edit re-validates it through ``on_settings_change``.

Everything imported from the gateway comes from ``gateway.plugins.api``, the
one module Otari keeps stable for plugins.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gateway.plugins.api import PluginContext

__version__ = "0.1.0"


def register(ctx: PluginContext) -> None:
    """Otari's entry point into the plugin."""
    # Imported here rather than at module top so that importing the package (which
    # the migration env and the pretooluse path do) stays light.
    from otari_agent_gates import settings
    from otari_agent_gates.cli import policy
    from otari_agent_gates.routes import operator_router, router

    config = settings.configure(ctx.config)
    if hasattr(ctx, "on_settings_change"):
        ctx.on_settings_change(settings.configure)
    ctx.add_router(router)
    ctx.add_router(operator_router)
    ctx.add_cli(policy)
    ctx.add_migrations(Path(__file__).parent / "migrations")
    # Only where the config names something to check, and only on an Otari that
    # has the traffic seam; an older gateway still gets the hook-driven half.
    if config.traffic.active and hasattr(ctx, "add_traffic_observer"):
        from otari_agent_gates.observer import AgentGatesObserver

        ctx.add_traffic_observer(AgentGatesObserver())
