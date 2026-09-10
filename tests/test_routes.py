"""Route behavior over a SQLite database, with Otari's auth dependencies overridden.

The plugin's routers are mounted on a bare FastAPI app the way Otari mounts them,
under ``/api/v1/plugins/agent-gates``. The schema comes from the plugin's own
migration chain, so a column the ORM expects and the migration lacks fails here.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from gateway.api.deps import get_config, get_db, require_deployment_operator, verify_api_key_or_master_key
from gateway.core.config import GatewayConfig
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import otari_agent_gates
from otari_agent_gates.routes import operator_router, router

API = "/api/v1/plugins/agent-gates/policy-checks"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    database = tmp_path / "routes.db"
    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", str(Path(otari_agent_gates.__file__).parent / "migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{database}")
    alembic_cfg.attributes["configure_logger"] = False
    command.upgrade(alembic_cfg, "head")

    # NullPool: each request opens and closes its own connection inside the test client's
    # loop, so nothing is left for a later loop to tear down.
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}", poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def _db() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    app = FastAPI()
    api = APIRouter(prefix="/api/v1")
    api.include_router(router, prefix="/plugins/agent-gates")
    api.include_router(operator_router, prefix="/plugins/agent-gates")
    app.include_router(api)
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_config] = lambda: GatewayConfig()
    app.dependency_overrides[require_deployment_operator] = lambda: None
    app.dependency_overrides[verify_api_key_or_master_key] = lambda: (None, True)
    with TestClient(app) as test_client:
        yield test_client


def _inline_spec(**overrides: Any) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "on_unavailable": "block",
        "gates": [
            {
                "type": "command",
                "name": "no-force-push",
                "pattern": r"git\s+push\b.*--force",
                "mode": "must_not_run",
                "message": "Never force-push.",
            }
        ],
    }
    spec.update(overrides)
    return spec


def test_check_with_inline_spec_records_a_history_row(client: TestClient) -> None:
    response = client.post(
        f"{API}/demo/check",
        json={
            "transcript": "[assistant] pushing",
            "session_id": "s1",
            "turn_id": "t1",
            "repo": "demo",
            "branch": "main",
            "executed_commands": [{"command": "git push --force origin main", "is_error": False}],
            "spec": _inline_spec(),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["compliant"] is False
    assert body["violations"] == ["Never force-push."]
    assert [gate["name"] for gate in body["gates"]] == ["no-force-push"]

    history = client.get(f"{API}/history").json()
    assert len(history) == 1
    assert history[0]["policy_name"] == "demo"
    assert history[0]["turn_id"] == "t1"
    assert history[0]["repo"] == "demo"
    assert history[0]["branch"] == "main"
    assert history[0]["created_at"].endswith("+00:00")
    assert client.get(f"{API}/history/count", params={"compliant": "false"}).json() == {"total": 1}


def test_check_without_a_stored_policy_is_404(client: TestClient) -> None:
    response = client.post(f"{API}/missing/check", json={"transcript": "text"})
    assert response.status_code == 404
    assert client.get(f"{API}/history/count").json() == {"total": 0}


def test_stored_policy_round_trip(client: TestClient) -> None:
    created = client.post(f"{API}/policies", json={"name": "stored", **_inline_spec()})
    assert created.status_code == 201
    assert created.json()["gates"] == [
        {"name": "no-force-push", "type": "command", "judge_backend": None, "judge_model": None}
    ]
    assert client.post(f"{API}/policies", json={"name": "stored", **_inline_spec()}).status_code == 409

    detail = client.get(f"{API}/policies/stored").json()
    assert detail["name"] == "stored"
    assert "no-force-push" in detail["yaml"]

    updated = client.put(
        f"{API}/policies/stored",
        json={
            "on_unavailable": "monitor",
            "gates": [{"type": "edited_path", "name": "no-changelog", "pattern": r"CHANGELOG\.md$", "message": "No."}],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["on_unavailable"] == "monitor"

    check = client.post(f"{API}/stored/check", json={"transcript": "edited", "edited_paths": ["CHANGELOG.md"]})
    assert check.status_code == 200
    assert check.json()["violations"] == ["No."]

    assert [policy["name"] for policy in client.get(f"{API}/policies").json()] == ["stored"]
    assert client.delete(f"{API}/policies/stored").status_code == 204
    assert client.delete(f"{API}/policies/stored").status_code == 404
    assert client.get(f"{API}/policies").json() == []


def test_give_up_dismiss_and_grouped_summaries(client: TestClient) -> None:
    for repo, branch in (("alpha", "main"), ("alpha", "feature"), ("beta", "main")):
        client.post(
            f"{API}/demo/check",
            json={
                "transcript": "ok",
                "session_id": f"{repo}-{branch}",
                "repo": repo,
                "branch": branch,
                "spec": _inline_spec(),
            },
        )
    assert client.post(f"{API}/demo/give-up", json={"session_id": "alpha-main", "repo": "alpha"}).status_code == 204

    session = client.get(f"{API}/history", params={"session_id": "alpha-main"}).json()
    assert [row["gave_up"] for row in session] == [True, False]
    assert session[0]["gates"] is None and session[0]["compliant"] is False

    repos = {row["repo"]: row["run_count"] for row in client.get(f"{API}/repos").json()}
    assert repos == {"alpha": 3, "beta": 1}
    branches = {row["branch"]: row["run_count"] for row in client.get(f"{API}/branches").json()}
    assert branches == {"main": 2, "feature": 1}
    sessions = client.get(f"{API}/sessions").json()
    assert sessions[0]["session_id"] == "alpha-main"
    assert sessions[0]["run_count"] == 2
    assert sessions[0]["last_compliant"] is False

    dismissed = client.post(f"{API}/history/{session[0]['id']}/dismiss")
    assert dismissed.status_code == 200
    assert dismissed.json()["dismissed_at"] is not None
    assert client.post(f"{API}/history/nope/dismiss").status_code == 404

    assert client.delete(f"{API}/history", params={"older_than_days": 1}).json() == {"deleted": 0}
    assert client.delete(f"{API}/history").status_code == 422
