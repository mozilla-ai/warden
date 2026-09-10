"""The plugin seam: registration, config validation, and the migration chain."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import click
import pytest
from alembic import command
from alembic.config import Config
from fastapi import APIRouter

import otari_agent_gates
from otari_agent_gates import settings
from otari_agent_gates.models import AgentGatesConfig

PACKAGE_DIR = Path(otari_agent_gates.__file__).parent


class _FakeContext:
    def __init__(self, config: dict[str, Any]) -> None:
        self.name = "agent-gates"
        self.config = config
        self.container = None
        self.routers: list[APIRouter] = []
        self.cli_groups: list[click.Group] = []
        self.migrations: list[Path] = []

    def add_router(self, router: APIRouter) -> None:
        self.routers.append(router)

    def add_cli(self, group: click.Group) -> None:
        self.cli_groups.append(group)

    def add_migrations(self, path: Path | str) -> None:
        self.migrations.append(Path(path))


@pytest.fixture(autouse=True)
def _reset_settings() -> None:
    settings.current = AgentGatesConfig()


def test_register_contributes_routers_cli_and_migrations() -> None:
    ctx = _FakeContext({"judge_timeout_seconds": 30})
    otari_agent_gates.register(ctx)  # type: ignore[arg-type]

    assert [router.prefix for router in ctx.routers] == ["/policy-checks", "/policy-checks"]
    assert [group.name for group in ctx.cli_groups] == ["policy"]
    assert sorted(ctx.cli_groups[0].commands) == ["check", "generate", "give-up", "pretooluse"]
    assert ctx.migrations == [PACKAGE_DIR / "migrations"]
    assert (ctx.migrations[0] / "env.py").is_file()
    assert settings.current.judge_timeout_seconds == 30


def test_register_rejects_an_unknown_config_key() -> None:
    with pytest.raises(ValueError, match="enabled"):
        otari_agent_gates.register(_FakeContext({"enabled": True}))  # type: ignore[arg-type]


def test_manifest_matches_the_package() -> None:
    import tomllib

    manifest = tomllib.loads((PACKAGE_DIR / "otari-plugin.toml").read_text(encoding="utf-8"))["plugin"]
    assert manifest["name"] == "agent-gates"
    assert manifest["package"] == "otari_agent_gates"
    assert manifest["version"] == otari_agent_gates.__version__
    assert (PACKAGE_DIR / manifest["ui"]["path"] / "index.html").is_file()


def test_migration_chain_builds_both_tables_on_sqlite(tmp_path: Path) -> None:
    database = tmp_path / "plugin.db"
    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", str(PACKAGE_DIR / "migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{database}")
    alembic_cfg.attributes["configure_logger"] = False

    command.upgrade(alembic_cfg, "head")

    connection = sqlite3.connect(database)
    tables = {row[0] for row in connection.execute("select name from sqlite_master where type='table'")}
    assert {"policy_check_records", "policy_check_policies", "alembic_version_agent_gates"} <= tables
    assert "alembic_version" not in tables
    assert connection.execute("select version_num from alembic_version_agent_gates").fetchall() == [("0001_initial",)]
    record_columns = {row[1] for row in connection.execute("pragma table_info(policy_check_records)")}
    assert {
        "id",
        "policy_name",
        "session_id",
        "turn_id",
        "repo",
        "branch",
        "checked",
        "compliant",
        "violations",
        "guidance",
        "gates",
        "total_cost_usd",
        "total_input_tokens",
        "total_output_tokens",
        "gave_up",
        "dismissed_at",
        "created_at",
    } == record_columns

    command.downgrade(alembic_cfg, "base")
    tables = {row[0] for row in connection.execute("select name from sqlite_master where type='table'")}
    assert "policy_check_records" not in tables and "policy_check_policies" not in tables
