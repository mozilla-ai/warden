"""The plugin's API, mounted by Otari under ``/api/v1/plugins/agent-gates``.

``router`` carries the two data-plane actions (``check`` and ``give-up``), which
authenticate with an Otari API key or the master key like any other data-plane
call and are what ``otari policy check`` talks to. ``operator_router`` carries the
policy and history reads and writes the dashboard uses, behind
``require_deployment_operator``, so the two auth rules live on two routers rather
than one overriding the other per route.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, cast

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, status
from gateway.plugins.api import (
    APIKey,
    GatewayConfig,
    get_config,
    get_db,
    require_deployment_operator,
    verify_api_key_or_master_key,
)
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from otari_agent_gates.models import JudgeGateSpec, PolicyCheckRecord, PolicyCheckSpec
from otari_agent_gates.service import (
    ExecutedCommand,
    GateOutcome,
    PolicyCheckUnavailableError,
    create_stored_policy,
    delete_history_older_than,
    delete_stored_policy,
    dismiss_history_entry,
    evaluate_policy,
    get_stored_policy_spec,
    list_branch_summaries,
    list_repo_summaries,
    list_session_summaries,
    list_stored_policies,
    record_give_up,
    record_policy_check,
    update_stored_policy,
)

ROUTER_PREFIX = "/policy-checks"

router = APIRouter(prefix=ROUTER_PREFIX, tags=["agent-gates"])
operator_router = APIRouter(
    prefix=ROUTER_PREFIX,
    tags=["agent-gates"],
    dependencies=[Depends(require_deployment_operator)],
)


def _utc_iso(value: datetime) -> str:
    """Serialize a stored timestamp as unambiguous UTC ISO-8601.

    SQLite returns a timezone-aware column naive, and a naive ``isoformat()`` has no offset,
    so a browser would read it in its own zone.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


class PolicyCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transcript: str = Field(min_length=1, description="Pre-extracted transcript excerpt for the current turn.")
    session_id: str | None = Field(default=None, max_length=200, description="Opaque correlation id.")
    turn_id: str | None = Field(
        default=None,
        max_length=200,
        description="The transcript's most recent entry uuid at check time, so retries within one session "
        "stay individually traceable.",
    )
    repo: str | None = Field(
        default=None,
        max_length=200,
        description="Basename of the git repo the CLI ran in, when it could tell.",
    )
    branch: str | None = Field(
        default=None,
        max_length=200,
        description="The git branch the CLI ran on, when it could tell.",
    )
    executed_commands: list[ExecutedCommand] = Field(
        default_factory=list,
        description="Every Bash command the current turn ran, extracted client-side from the transcript's "
        "structured tool_use/tool_result blocks. Powers command gates.",
    )
    edited_paths: list[str] = Field(
        default_factory=list,
        description="Repo-relative paths this turn's Edit/Write/NotebookEdit calls touched. Powers "
        "scoped_guidance and edited_path gates, and a command gate's paths condition.",
    )
    loaded_context_paths: list[str] = Field(
        default_factory=list,
        description="Every path Claude Code injected as a nested_memory attachment, anywhere in the session. "
        "Powers scoped_guidance gates.",
    )
    spec: PolicyCheckSpec | None = Field(
        default=None,
        description="An inline spec, such as a repo's own .otari-gates.yml discovered by the CLI. When set, "
        "policy_name is only a label recorded on the history row and no stored policy is looked up. "
        "Absent, the stored policy named policy_name is used.",
    )


class PolicyCheckResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy: str
    checked: bool = Field(
        description="False only when a judge gate was unreachable and this reflects on_unavailable=monitor."
    )
    compliant: bool
    violations: list[str] = Field(default_factory=list)
    guidance: str = ""
    gates: list[GateOutcome] = Field(default_factory=list, description="Each gate's own outcome.")


@router.post("/{policy_name}/check", response_model=PolicyCheckResponse)
async def check_policy(
    policy_name: str,
    body: PolicyCheckRequest,
    auth_result: Annotated[tuple[APIKey | None, bool], Depends(verify_api_key_or_master_key)],
    config: Annotated[GatewayConfig, Depends(get_config)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PolicyCheckResponse:
    """Check a transcript excerpt against a policy and record the verdict.

    An inline ``spec`` wins outright; otherwise the stored policy named ``policy_name`` is
    used, and 404 if there is none. 502 when a judge gate is unreachable under
    ``on_unavailable=block``; nothing is recorded in that case.
    """
    spec: PolicyCheckSpec | None = body.spec
    if spec is None:
        spec = await get_stored_policy_spec(db, policy_name)
        if spec is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"policy check {policy_name!r} is not configured")

    try:
        result = await evaluate_policy(
            config,
            spec,
            policy_name=policy_name,
            transcript_excerpt=body.transcript,
            executed_commands=body.executed_commands,
            edited_paths=body.edited_paths,
            loaded_context_paths=body.loaded_context_paths,
        )
    except PolicyCheckUnavailableError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=exc.public_detail) from exc

    await record_policy_check(
        db,
        policy_name=policy_name,
        session_id=body.session_id,
        turn_id=body.turn_id,
        repo=body.repo,
        branch=body.branch,
        result=result,
    )
    return PolicyCheckResponse(**result)


class PolicyCheckGiveUpRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(
        min_length=1,
        max_length=200,
        description="Which session's retry loop this is. Required: a give-up marker only means something "
        "on one session's timeline.",
    )
    repo: str | None = Field(default=None, max_length=200)
    branch: str | None = Field(default=None, max_length=200)


@router.post("/{policy_name}/give-up", status_code=status.HTTP_204_NO_CONTENT)
async def give_up_policy_check(
    policy_name: str,
    body: PolicyCheckGiveUpRequest,
    auth_result: Annotated[tuple[APIKey | None, bool], Depends(verify_api_key_or_master_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Record that a session's Stop-hook retry loop ended without reaching compliant.

    Called by ``otari policy give-up`` when the hook's attempt cap is hit. No policy lookup:
    nothing is evaluated, so ``policy_name`` is recorded purely as a label.
    """
    await record_give_up(db, policy_name=policy_name, session_id=body.session_id, repo=body.repo, branch=body.branch)


# --------------------------------------------------------------------------- #
# Operator reads and writes: stored policies, and check history
# --------------------------------------------------------------------------- #


class PolicyGateSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: str
    judge_backend: str | None = None
    judge_model: str | None = None


class ConfiguredPolicySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    on_unavailable: str
    gates: list[PolicyGateSummary]


def _gate_summaries(spec: PolicyCheckSpec) -> list[PolicyGateSummary]:
    return [
        PolicyGateSummary(
            name=gate.name,
            type=gate.type,
            judge_backend=gate.judge_backend if isinstance(gate, JudgeGateSpec) else None,
            judge_model=gate.judge_model if isinstance(gate, JudgeGateSpec) else None,
        )
        for gate in spec.gates
    ]


@operator_router.get("/policies")
async def list_configured_policies(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ConfiguredPolicySummary]:
    """Every stored policy. A repo's own ``.otari-gates.yml`` never appears here: it is sent inline per check."""
    stored = await list_stored_policies(db)
    return [
        ConfiguredPolicySummary(name=name, on_unavailable=spec.on_unavailable, gates=_gate_summaries(spec))
        for name, spec in stored.items()
    ]


class PolicyDetailResponse(PolicyCheckSpec):
    """The full spec for one policy, plus the same spec rendered as YAML.

    The YAML reflects the policy's current definition, not necessarily what was in effect
    when a past run checked against it; nothing snapshots a policy per run.
    """

    name: str
    yaml: str


@operator_router.get("/policies/{policy_name}")
async def get_policy_detail(
    policy_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PolicyDetailResponse:
    """One stored policy in full, for the gate editor. 404 if it is not stored."""
    spec = await get_stored_policy_spec(db, policy_name)
    if spec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"policy check {policy_name!r} is not configured")
    return PolicyDetailResponse(
        name=policy_name,
        gates=spec.gates,
        on_unavailable=spec.on_unavailable,
        yaml=yaml.safe_dump(spec.model_dump(mode="json", exclude_none=True), sort_keys=False),
    )


class CreatePolicyRequest(PolicyCheckSpec):
    name: str = Field(min_length=1)


@operator_router.post("/policies", status_code=status.HTTP_201_CREATED)
async def create_policy(
    body: CreatePolicyRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConfiguredPolicySummary:
    """Create a stored policy. 409 if the name is already in use."""
    existing = await get_stored_policy_spec(db, body.name)
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"a policy named {body.name!r} already exists")
    spec = PolicyCheckSpec(gates=body.gates, on_unavailable=body.on_unavailable)
    await create_stored_policy(db, name=body.name, spec=spec)
    return ConfiguredPolicySummary(name=body.name, on_unavailable=spec.on_unavailable, gates=_gate_summaries(spec))


@operator_router.put("/policies/{policy_name}")
async def update_policy(
    policy_name: str,
    body: PolicyCheckSpec,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConfiguredPolicySummary:
    """Overwrite a stored policy's whole gate list and on_unavailable. 404 if it is not stored.

    There is no single-gate write: evaluation order and the short-circuit rule are
    properties of the whole list, so the dashboard splices one gate and writes the list back.
    """
    row = await update_stored_policy(db, name=policy_name, spec=body)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"{policy_name!r} is not a stored policy")
    return ConfiguredPolicySummary(name=policy_name, on_unavailable=body.on_unavailable, gates=_gate_summaries(body))


@operator_router.delete("/policies/{policy_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(
    policy_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a stored policy. 404 if it is not stored."""
    deleted = await delete_stored_policy(db, name=policy_name)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"{policy_name!r} is not a stored policy")


class RepoSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repo: str
    run_count: int
    total_cost_usd: float | None = Field(
        default=None, description="Sum of every run's own total_cost_usd in this repo. Null if none reported any."
    )
    total_input_tokens: int | None = None
    total_output_tokens: int | None = None
    last_run_at: str
    last_compliant: bool
    last_checked: bool
    last_policy_name: str


class BranchSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch: str
    run_count: int
    total_cost_usd: float | None = Field(
        default=None, description="Sum of every run's own total_cost_usd on this branch. Null if none reported any."
    )
    total_input_tokens: int | None = None
    total_output_tokens: int | None = None
    last_run_at: str
    last_compliant: bool
    last_checked: bool
    last_policy_name: str


@operator_router.get("/repos")
async def list_policy_check_repos(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[RepoSummary]:
    """One row per repo that has ever recorded a check, newest run first. ``/history?repo=`` drills in."""
    summaries = await list_repo_summaries(db)
    return [
        RepoSummary(
            repo=cast("str", summary["repo"]),
            run_count=cast("int", summary["run_count"]),
            total_cost_usd=cast("float | None", summary["total_cost_usd"]),
            total_input_tokens=cast("int | None", summary["total_input_tokens"]),
            total_output_tokens=cast("int | None", summary["total_output_tokens"]),
            last_run_at=_utc_iso(cast("datetime", summary["last_run_at"])),
            last_compliant=cast("bool", summary["last_compliant"]),
            last_checked=cast("bool", summary["last_checked"]),
            last_policy_name=cast("str", summary["last_policy_name"]),
        )
        for summary in summaries
    ]


@operator_router.get("/branches")
async def list_policy_check_branches(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[BranchSummary]:
    """One row per git branch that has ever recorded a check, newest run first. ``/history?branch=`` drills in."""
    summaries = await list_branch_summaries(db)
    return [
        BranchSummary(
            branch=cast("str", summary["branch"]),
            run_count=cast("int", summary["run_count"]),
            total_cost_usd=cast("float | None", summary["total_cost_usd"]),
            total_input_tokens=cast("int | None", summary["total_input_tokens"]),
            total_output_tokens=cast("int | None", summary["total_output_tokens"]),
            last_run_at=_utc_iso(cast("datetime", summary["last_run_at"])),
            last_compliant=cast("bool", summary["last_compliant"]),
            last_checked=cast("bool", summary["last_checked"]),
            last_policy_name=cast("str", summary["last_policy_name"]),
        )
        for summary in summaries
    ]


class SessionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    run_count: int
    repo: str | None = Field(default=None, description="The last attempt's own repo, when it could tell.")
    branch: str | None = Field(default=None, description="The last attempt's own git branch, when it could tell.")
    total_cost_usd: float | None = Field(
        default=None,
        description="Sum of every attempt's own total_cost_usd in this session. Null if none reported any.",
    )
    total_input_tokens: int | None = None
    total_output_tokens: int | None = None
    last_run_at: str
    last_compliant: bool
    last_checked: bool
    last_policy_name: str


@operator_router.get("/sessions")
async def list_policy_check_sessions(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[SessionSummary]:
    """One row per Claude Code session that has ever recorded a check, newest run first.

    ``run_count`` is how many attempts the Stop-hook retry loop took and ``last_compliant``
    whether it converged. ``/history?session_id=`` tells that loop's attempt-by-attempt story.
    """
    summaries = await list_session_summaries(db)
    return [
        SessionSummary(
            session_id=cast("str", summary["session_id"]),
            run_count=cast("int", summary["run_count"]),
            repo=cast("str | None", summary["last_repo"]),
            branch=cast("str | None", summary["last_branch"]),
            total_cost_usd=cast("float | None", summary["total_cost_usd"]),
            total_input_tokens=cast("int | None", summary["total_input_tokens"]),
            total_output_tokens=cast("int | None", summary["total_output_tokens"]),
            last_run_at=_utc_iso(cast("datetime", summary["last_run_at"])),
            last_compliant=cast("bool", summary["last_compliant"]),
            last_checked=cast("bool", summary["last_checked"]),
            last_policy_name=cast("str", summary["last_policy_name"]),
        )
        for summary in summaries
    ]


class PolicyCheckHistoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    policy_name: str
    session_id: str | None
    turn_id: str | None = Field(
        default=None,
        description="The transcript's most recent entry uuid at check time. Null for a row recorded without one.",
    )
    repo: str | None = Field(
        default=None,
        description="Basename of the git repo the CLI ran in. Null when the CLI ran outside a git repo.",
    )
    branch: str | None = Field(
        default=None,
        description="The git branch the CLI ran on. Null when the CLI ran outside a git repo.",
    )
    checked: bool
    compliant: bool
    violations: list[str]
    guidance: str
    gates: list[GateOutcome] | None = Field(
        default=None,
        description="Each gate's own outcome. Null (not empty) for a row recorded without a breakdown.",
    )
    total_cost_usd: float | None = Field(
        default=None,
        description="Sum of every subscription-backend judge gate's own reported cost for this run. Null "
        "when nothing in the run reported usage.",
    )
    total_input_tokens: int | None = None
    total_output_tokens: int | None = None
    gave_up: bool = Field(
        default=False,
        description="A terminal marker the Stop hook wrote when its retry cap was reached, not a real "
        "evaluation; `gates` is null here too.",
    )
    dismissed_at: str | None = Field(
        default=None, description="When an operator acknowledged this row from the dashboard. Never auto-set."
    )
    created_at: str

    @classmethod
    def from_model(cls, record: PolicyCheckRecord) -> PolicyCheckHistoryEntry:
        return cls(
            id=record.id,
            policy_name=record.policy_name,
            session_id=record.session_id,
            turn_id=record.turn_id,
            repo=record.repo,
            branch=record.branch,
            checked=record.checked,
            compliant=record.compliant,
            violations=record.violations,
            guidance=record.guidance,
            gates=cast("list[GateOutcome] | None", record.gates),
            total_cost_usd=record.total_cost_usd,
            total_input_tokens=record.total_input_tokens,
            total_output_tokens=record.total_output_tokens,
            gave_up=record.gave_up,
            dismissed_at=_utc_iso(record.dismissed_at) if record.dismissed_at is not None else None,
            created_at=_utc_iso(record.created_at),
        )


class PolicyCheckHistoryCount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int


def _history_filters(
    *,
    policy_name: str | None,
    compliant: bool | None,
    session_id: str | None,
    repo: str | None,
    branch: str | None = None,
) -> list[Any]:
    conditions: list[Any] = []
    if policy_name is not None:
        conditions.append(PolicyCheckRecord.policy_name == policy_name)
    if compliant is not None:
        conditions.append(PolicyCheckRecord.compliant.is_(compliant))
    if session_id is not None:
        conditions.append(PolicyCheckRecord.session_id == session_id)
    if repo is not None:
        conditions.append(PolicyCheckRecord.repo == repo)
    if branch is not None:
        conditions.append(PolicyCheckRecord.branch == branch)
    return conditions


@operator_router.get("/history")
async def list_policy_check_history(
    db: Annotated[AsyncSession, Depends(get_db)],
    policy_name: str | None = Query(default=None, description="Filter to one policy."),
    compliant: bool | None = Query(default=None, description="Filter to compliant or non-compliant checks."),
    session_id: str | None = Query(default=None, description="Filter to one session."),
    repo: str | None = Query(default=None, description="Filter to one repo."),
    branch: str | None = Query(default=None, description="Filter to one git branch."),
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[PolicyCheckHistoryEntry]:
    """Past policy checks, newest first. Bare array; see ``/history/count`` for the total."""
    conditions = _history_filters(
        policy_name=policy_name, compliant=compliant, session_id=session_id, repo=repo, branch=branch
    )
    stmt = (
        select(PolicyCheckRecord)
        .where(*conditions)
        .order_by(PolicyCheckRecord.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return [PolicyCheckHistoryEntry.from_model(record) for record in result.scalars().all()]


@operator_router.get("/history/count")
async def count_policy_check_history(
    db: Annotated[AsyncSession, Depends(get_db)],
    policy_name: str | None = Query(default=None),
    compliant: bool | None = Query(default=None),
    session_id: str | None = Query(default=None),
    repo: str | None = Query(default=None),
    branch: str | None = Query(default=None),
) -> PolicyCheckHistoryCount:
    """Total rows matching the same filters ``/history`` accepts."""
    conditions = _history_filters(
        policy_name=policy_name, compliant=compliant, session_id=session_id, repo=repo, branch=branch
    )
    stmt = select(func.count()).select_from(PolicyCheckRecord).where(*conditions)
    total = await db.scalar(stmt)
    return PolicyCheckHistoryCount(total=total or 0)


@operator_router.get("/history/{record_id}")
async def get_policy_check_history_entry(
    record_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PolicyCheckHistoryEntry:
    """One history row. 404 if the id is unknown."""
    record = await db.get(PolicyCheckRecord, record_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"policy check history entry {record_id!r} not found")
    return PolicyCheckHistoryEntry.from_model(record)


@operator_router.post("/history/{record_id}/dismiss")
async def dismiss_policy_check_history_entry(
    record_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PolicyCheckHistoryEntry:
    """Acknowledge one history row. One-way, and it does not change the verdict."""
    record = await dismiss_history_entry(db, record_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"policy check history entry {record_id!r} not found")
    return PolicyCheckHistoryEntry.from_model(record)


class DeleteHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deleted: int


@operator_router.delete("/history")
async def delete_old_policy_check_history(
    db: Annotated[AsyncSession, Depends(get_db)],
    older_than_days: Annotated[int, Query(ge=1)],
) -> DeleteHistoryResponse:
    """Delete every history row older than ``older_than_days``. The cutoff is required, never defaulted."""
    deleted = await delete_history_older_than(db, older_than_days=older_than_days)
    return DeleteHistoryResponse(deleted=deleted)
