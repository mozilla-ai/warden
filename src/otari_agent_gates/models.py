"""Gate and policy schemas, the plugin's config block, and its two tables.

A policy is an ordered list of gates. Four gate types are mechanical: free,
deterministic, evaluated the same way every time, and run first. Any mechanical
failure short-circuits the judge phase, so a policy built only from mechanical
gates never calls a model. Otherwise every ``llm_judge`` gate runs concurrently
and their results aggregate.

The tables live on this module's own ``Base`` rather than the gateway's, so the
gateway's Alembic autogenerate never sees them and this plugin's migration chain
(``migrations/``) is the only thing that manages them.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import JSON, DateTime, Index, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

GATES_FILENAME = ".otari-gates.yml"


class DeterministicGateSpec(BaseModel):
    """A regex check against the transcript excerpt. Free, and never wrong about what it matched."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["deterministic"] = "deterministic"
    name: str = Field(min_length=1)
    pattern: str = Field(min_length=1, description="Regex (re.search) matched against the transcript excerpt.")
    mode: Literal["must_match", "must_not_match"] = Field(
        default="must_not_match",
        description=(
            "'must_not_match' (default) fails the gate when the pattern is found, the common case "
            "(banning a string like a force-push). 'must_match' fails when it is absent, requiring "
            "evidence something happened, like a passing test run."
        ),
    )
    message: str = Field(min_length=1, description="Violation message reported when this gate fails.")


class CommandGateSpec(BaseModel):
    """A regex check against a Bash command the current turn actually ran, and whether it errored.

    Evaluated from the ``executed_commands`` the CLI extracts from the transcript's own
    structured ``tool_use``/``tool_result`` blocks (``transcript.extract_executed_commands``),
    never from rendered prose, so a command the transcript merely discusses cannot trip it.
    A caller that sends no ``executed_commands`` is treated as having run none.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["command"] = "command"
    name: str = Field(min_length=1)
    pattern: str = Field(min_length=1, description="Regex (re.search) matched against an executed command's text.")
    mode: Literal["must_run_and_succeed", "must_not_run"] = Field(
        default="must_run_and_succeed",
        description=(
            "'must_run_and_succeed' (default) fails unless at least one matching command ran and did not "
            "error. 'must_not_run' fails if any matching command ran at all, regardless of outcome."
        ),
    )
    paths: list[str] | None = Field(
        default=None,
        description=(
            "When set, this gate only applies if an edited path this turn matches any of these "
            "fnmatch-style globs, like a GitHub Actions workflow's own `paths:` filter. Matched against "
            "`edited_paths`, which the CLI sends relative to the repo root. Like a shell glob, `*` matches "
            "across `/` too, so `web/*` means anywhere under web/. Unset means the gate always applies."
        ),
    )
    message: str = Field(min_length=1, description="Violation message reported when this gate fails.")


class ScopedGuidanceGateSpec(BaseModel):
    """Checks that a directory's own ``AGENTS.md``/``CLAUDE.md`` was loaded before this turn edited under it.

    Claude Code injects a directory's guidance as a ``nested_memory`` attachment the moment a
    file under it is touched, possibly many turns earlier in the session. So the load is looked
    for across the whole transcript (``loaded_context_paths``) while the edit is checked only in
    the current turn (``edited_paths``). A caller that sends neither is treated as having
    edited and loaded nothing.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["scoped_guidance"] = "scoped_guidance"
    name: str = Field(min_length=1)
    directory: str = Field(
        min_length=1,
        description="A directory such as 'web/' or 'src/gateway/', matched as the glob `<directory>/*` against an "
        "edited file's repo-relative path and against a loaded nested_memory attachment's path.",
    )
    message: str = Field(min_length=1, description="Violation message reported when this gate fails.")


class EditedPathGateSpec(BaseModel):
    """A regex check against the file paths this turn's ``Edit``/``Write``/``NotebookEdit`` calls touched.

    No git awareness: this answers "was this file edited", not "was it committed". A caller
    that sends no ``edited_paths`` is treated as having edited nothing.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["edited_path"] = "edited_path"
    name: str = Field(min_length=1)
    pattern: str = Field(min_length=1, description="Regex (re.search) matched against an edited file's path.")
    mode: Literal["must_not_edit", "must_edit"] = Field(
        default="must_not_edit",
        description=(
            "'must_not_edit' (default) fails if any edited path matches. 'must_edit' fails unless at "
            "least one edited path matches."
        ),
    )
    message: str = Field(min_length=1, description="Violation message reported when this gate fails.")


class JudgeGateSpec(BaseModel):
    """An LLM-as-judge check: does the transcript excerpt comply with free-text rules."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["llm_judge"] = "llm_judge"
    name: str = Field(min_length=1)
    judge_backend: Literal["provider", "subscription"] = Field(
        default="provider",
        description=(
            "'provider' (default) resolves judge_model through Otari's own provider config. "
            "'subscription' shells out to the locally installed `claude` CLI, using whatever session is "
            "already logged in, at zero marginal cost; it requires the gateway process to run on the same "
            "machine as that login. A policy may mix both across its gates."
        ),
    )
    judge_model: str | None = Field(
        default=None,
        min_length=1,
        description=(
            "Required when judge_backend='provider': a model selector resolved the same way a completion's "
            "is, so it may name a local provider instance. Optional when judge_backend='subscription': passed "
            "as the `claude` CLI's own --model flag; unset defaults to headless.DEFAULT_SUBSCRIPTION_MODEL."
        ),
    )
    rules: str | None = Field(
        default=None,
        min_length=1,
        description="Inline rules text. Exactly one of `rules` / `rules_file` must be set.",
    )
    rules_file: str | None = Field(
        default=None,
        min_length=1,
        description=(
            "Path to a file read once at validation time and used as `rules`. Resolved against the process "
            "working directory, so prefer an absolute path."
        ),
    )
    max_transcript_chars: int = Field(
        default=24_000,
        gt=0,
        description="Hard cap on the excerpt sent to the judge, applied server-side whatever the caller sent.",
    )
    judge_max_tokens: int = Field(default=600, gt=0, description="Cap on the judge's own output tokens.")

    @model_validator(mode="after")
    def _exactly_one_rules_source(self) -> JudgeGateSpec:
        if (self.rules is None) == (self.rules_file is None):
            raise ValueError("exactly one of `rules` or `rules_file` must be set")
        return self

    @model_validator(mode="after")
    def _judge_model_required_for_provider(self) -> JudgeGateSpec:
        if self.judge_backend == "provider" and not self.judge_model:
            raise ValueError("judge_model is required when judge_backend='provider'")
        return self

    @model_validator(mode="after")
    def _resolve_rules_file(self) -> JudgeGateSpec:
        # Read once, then cleared: this object is re-validated whenever it is embedded in a
        # freshly built spec (the policy routes rebuild one from an already-resolved gate
        # list), and the exactly-one rule above would otherwise reject the second pass.
        if self.rules_file is not None:
            path = Path(self.rules_file)
            if not path.is_file():
                raise ValueError(f"rules_file {self.rules_file!r} does not exist or is not a file")
            text = path.read_text(encoding="utf-8").strip()
            if not text:
                raise ValueError(f"rules_file {self.rules_file!r} is empty")
            self.rules = text
            self.rules_file = None
        return self


GateSpec = Annotated[
    DeterministicGateSpec | CommandGateSpec | ScopedGuidanceGateSpec | EditedPathGateSpec | JudgeGateSpec,
    Field(discriminator="type"),
]


class PolicyCheckSpec(BaseModel):
    """One named policy: an ordered list of gates, and what to report if a judge gate is unreachable."""

    model_config = ConfigDict(extra="forbid")

    gates: list[GateSpec] = Field(min_length=1)
    on_unavailable: Literal["block", "monitor"] = Field(
        default="block",
        description=(
            "What a judge gate reports when its call fails (after one retry). 'block' (default) fails "
            "closed: compliant=False. 'monitor' fails open: compliant=True, checked=False."
        ),
    )


class TrafficConfig(BaseModel):
    """What to check on inference traffic passing through the gateway (see ``observer``).

    Either a stored policy by name or inline gates; inline wins when both are set.
    Empty means the traffic observer is not registered at all.
    """

    model_config = ConfigDict(extra="forbid")

    policy: str | None = Field(default=None, description="A stored policy's name, read fresh about once a minute.")
    gates: list[GateSpec] = Field(default_factory=list, description="Inline gates, the same shape as a gates file.")

    @property
    def active(self) -> bool:
        return bool(self.policy or self.gates)


class AgentGatesConfig(BaseModel):
    """The ``plugins.agent-gates:`` block of ``config.yml``.

    Loading the plugin is the on/off switch (``plugins.disabled`` turns it off), and a
    hook-checked policy is never declared here: it comes from a repo's own
    ``.otari-gates.yml`` or a stored row. ``traffic`` names what the gateway checks on
    the wire, which has no repository to carry a file. An unknown key fails plugin load
    so a typo is caught at startup rather than ignored.
    """

    model_config = ConfigDict(extra="forbid")

    judge_timeout_seconds: int = Field(
        default=120,
        gt=0,
        description="How long one subscription-backend judge call may take before it counts as failed.",
    )
    traffic: TrafficConfig = Field(default_factory=TrafficConfig)


class Base(DeclarativeBase):
    """The plugin's own metadata; see the module docstring."""


class PolicyCheckRecord(Base):
    """One recorded ``POST /policy-checks/{policy_name}/check`` evaluation.

    Stores the verdict, never the transcript excerpt that produced it. Deployment-wide:
    no workspace or user scoping, and many rows per ``policy_name`` is the point.

    ``gates`` is the per-gate breakdown (``service.GateOutcome`` dumped to JSON); null for a
    row written before the field existed, which is a different fact than "every gate passed".
    ``turn_id`` is the transcript's most recent entry uuid at check time, so two checks in one
    session's retry loop stay individually traceable. ``repo`` and ``branch`` are what the CLI
    could tell from ``git``. The three usage columns sum every subscription-backend judge
    gate's own reported usage; null, not zero, when nothing in the run reported any.
    ``gave_up`` marks a terminal marker row the Stop hook writes when its retry cap is reached
    (``checked=True, compliant=False, gates=None``). ``dismissed_at`` is set once by an
    operator from the dashboard and never cleared; it does not change the verdict.
    """

    __tablename__ = "policy_check_records"
    __table_args__ = (
        Index("ix_policy_check_records_policy_name", "policy_name"),
        Index("ix_policy_check_records_created_at", "created_at"),
        Index("ix_policy_check_records_repo", "repo"),
        Index("ix_policy_check_records_branch", "branch"),
    )

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    policy_name: Mapped[str] = mapped_column()
    session_id: Mapped[str | None] = mapped_column(default=None)
    turn_id: Mapped[str | None] = mapped_column(default=None)
    repo: Mapped[str | None] = mapped_column(default=None)
    branch: Mapped[str | None] = mapped_column(default=None)
    checked: Mapped[bool] = mapped_column()
    compliant: Mapped[bool] = mapped_column()
    violations: Mapped[list[str]] = mapped_column(JSON)
    guidance: Mapped[str] = mapped_column(default="")
    gates: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, default=None)
    total_cost_usd: Mapped[float | None] = mapped_column(default=None)
    total_input_tokens: Mapped[int | None] = mapped_column(default=None)
    total_output_tokens: Mapped[int | None] = mapped_column(default=None)
    gave_up: Mapped[bool] = mapped_column(default=False)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class PolicyCheckPolicy(Base):
    """A named policy stored through the API or dashboard.

    The only server-side source of a named policy: a repo's own ``.otari-gates.yml`` is sent
    inline per check and never registered here. This table is for a check with no repo to
    carry a file, or an operator-managed policy meant to apply across many repos. Read fresh
    on every request (no cache), so a dashboard edit is visible immediately. ``gates`` is
    validated against ``PolicyCheckSpec`` on write and again on load, so a row written by a
    newer schema surfaces as a warning, not a crash.
    """

    __tablename__ = "policy_check_policies"
    __table_args__ = (UniqueConstraint("name", name="uq_policy_check_policies_name"),)

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column()
    gates: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    on_unavailable: Mapped[str] = mapped_column(default="block")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
