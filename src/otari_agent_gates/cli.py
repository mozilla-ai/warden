"""The ``otari policy`` command group.

``check`` and ``give-up`` are HTTP clients against a running ``otari serve``:
extraction happens here, on the machine that holds the transcript, and every
gate is evaluated inside the gateway. ``pretooluse`` and ``generate`` never
touch a gateway at all.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import click
import yaml
from gateway.core.config import load_config
from pydantic import ValidationError

from otari_agent_gates.models import GATES_FILENAME, CommandGateSpec, PolicyCheckSpec

API_PREFIX = "/api/v1/plugins/agent-gates/policy-checks"

_GATES_FILE_SEARCH_DEPTH = 20


@click.group()
def policy() -> None:
    """Check and author Agent Gates policies."""


class GatesFileError(ValueError):
    """A gates file that could not be read, parsed, or validated."""


def _git_toplevel(start: Path) -> Path | None:
    """The git repo ``start`` is inside, or ``None`` outside one or without ``git`` on PATH."""
    git_binary = shutil.which("git")
    if git_binary is None:
        return None
    try:
        completed = subprocess.run(  # noqa: S603 argv list, never shell=True
            [git_binary, "-C", str(start), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    toplevel = completed.stdout.strip()
    return Path(toplevel) if toplevel else None


def _working_tree_changes(repo_toplevel: Path | None) -> list[str]:
    """Paths changed in the working tree, relative to the repo, or none outside a repo.

    A turn that writes a file through a shell command (``cat >``, ``sed -i``,
    ``tee``) leaves no ``Edit`` or ``Write`` call in the transcript, so this is
    what keeps a ``paths`` condition or an ``edited_path`` gate from missing it.
    Covers everything uncommitted at check time, so it can reach back before the
    current turn; that errs toward evaluating a gate rather than skipping it.
    """
    git_binary = shutil.which("git")
    if repo_toplevel is None or git_binary is None:
        return []
    try:
        completed = subprocess.run(  # noqa: S603 argv list, never shell=True
            [git_binary, "-C", str(repo_toplevel), "status", "--porcelain", "--untracked-files=all"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0:
        return []
    paths: list[str] = []
    for line in completed.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        # A rename is reported as "old -> new"; the new path is the one edited.
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.append(path.strip('"'))
    return paths


def _current_repo_label(start: Path) -> str | None:
    """The basename of the git repo ``start`` is inside, for grouping runs by repo."""
    toplevel = _git_toplevel(start)
    return toplevel.name if toplevel is not None else None


def _relativize_paths(paths: list[str], repo_toplevel: Path | None) -> list[str]:
    """Strip the repo toplevel from each path, so gate globs match like a CI paths filter.

    A path outside the repo, or any path when the toplevel is unknown, passes through
    unchanged: a gate's glob simply will not match it.
    """
    if repo_toplevel is None:
        return paths
    resolved_toplevel = repo_toplevel.resolve()
    relativized: list[str] = []
    for path in paths:
        try:
            relativized.append(str(Path(path).resolve().relative_to(resolved_toplevel)))
        except ValueError:
            relativized.append(path)
    return relativized


def _current_branch_label(start: Path) -> str | None:
    """The current git branch at ``start``; ``None`` outside a repo or on a detached HEAD."""
    git_binary = shutil.which("git")
    if git_binary is None:
        return None
    try:
        completed = subprocess.run(  # noqa: S603 argv list, never shell=True
            [git_binary, "-C", str(start), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    branch = completed.stdout.strip()
    return branch if branch and branch != "HEAD" else None


def find_gates_file(start: Path, filename: str = GATES_FILENAME) -> Path | None:
    """Walk upward from ``start`` looking for a gates file, the way ``git`` finds ``.git``.

    Depth-capped as a bound against a symlink loop.
    """
    current = start.resolve()
    for _ in range(_GATES_FILE_SEARCH_DEPTH):
        candidate = current / filename
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            return None
        current = parent
    return None


def load_gates_spec(path: Path) -> PolicyCheckSpec:
    """Parse and validate a gates file against the same model the gateway validates against.

    Raises ``GatesFileError`` so a malformed file fails locally, before any network call.
    """
    try:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise GatesFileError(f"could not read {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise GatesFileError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise GatesFileError(f"{path} must be a YAML mapping with 'gates' (and optionally 'on_unavailable')")
    try:
        return PolicyCheckSpec.model_validate(parsed)
    except ValidationError as exc:
        raise GatesFileError(f"{path} failed validation: {exc}") from exc


def _load_gates_file(path: Path) -> PolicyCheckSpec:
    try:
        return load_gates_spec(path)
    except GatesFileError as exc:
        click.echo(json.dumps({"error": str(exc)}))
        raise SystemExit(2) from exc


def _base_url_and_key(config: str | None, url: str | None, api_key: str | None) -> tuple[str, str]:
    cfg = load_config(config)
    host = cfg.host if cfg.host and cfg.host != "0.0.0.0" else "127.0.0.1"
    base_url = url or f"http://{host}:{cfg.port}"
    return base_url, api_key or cfg.master_key or ""


@policy.command(name="check")
@click.argument("policy_name")
@click.option(
    "--claude-transcript",
    "claude_transcript_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to a Claude Code session transcript (.jsonl). Only the current turn is sent onward.",
)
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, dir_okay=False),
    help="Path to config YAML file",
    default=None,
)
@click.option("--url", default=None, help="Gateway base URL. Default: derived from --config's host/port.")
@click.option("--api-key", default=None, help="Otari API key. Default: --config's master_key.")
@click.option("--max-chars", type=int, default=20_000, help="Transcript excerpt cap, before the gateway's own cap.")
@click.option(
    "--session-id",
    default=None,
    help="Opaque correlation id (e.g. Claude Code's session_id), recorded on the history row.",
)
@click.option(
    "--gates-file",
    "gates_file_path",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help=f"Path to a repo-scoped gates file. Default: auto-discover {GATES_FILENAME} by walking upward from "
    "the current directory. When found, its gates are sent inline and POLICY_NAME becomes only the label "
    "recorded in history; no stored policy is looked up.",
)
def policy_check(
    policy_name: str,
    claude_transcript_path: str,
    config: str | None,
    url: str | None,
    api_key: str | None,
    max_chars: int,
    session_id: str | None,
    gates_file_path: str | None,
) -> None:
    """Check POLICY_NAME against a Claude Code transcript, via a running `otari serve`.

    Connection details default from the same config.yml the server loads, so `otari serve`
    then `otari policy check` against one config file needs no extra flags.

    Exit codes: 0 compliant; 1 non-compliant; 2 could not check at all (unreachable
    gateway, unknown policy, a malformed gates file, or on_unavailable=block on an
    unreachable judge). The Stop hook applies its fail-open or fail-closed choice to 2 only.
    """
    import urllib.error
    import urllib.parse
    import urllib.request

    from otari_agent_gates.transcript import (
        extract_edited_paths,
        extract_excerpt,
        extract_executed_commands,
        extract_loaded_context_paths,
        latest_turn_id,
    )

    base_url, key = _base_url_and_key(config, url, api_key)

    excerpt = extract_excerpt(claude_transcript_path, max_chars)
    if not excerpt:
        click.echo(json.dumps({"error": "transcript had nothing to check"}))
        raise SystemExit(2)
    turn_id = latest_turn_id(claude_transcript_path)
    repo_toplevel = _git_toplevel(Path.cwd())
    repo = repo_toplevel.name if repo_toplevel is not None else None
    branch = _current_branch_label(Path.cwd())
    executed_commands = extract_executed_commands(claude_transcript_path)
    edited_paths = sorted(
        set(_relativize_paths(extract_edited_paths(claude_transcript_path), repo_toplevel))
        | set(_working_tree_changes(repo_toplevel))
    )
    loaded_context_paths = _relativize_paths(extract_loaded_context_paths(claude_transcript_path), repo_toplevel)

    gates_file = Path(gates_file_path) if gates_file_path else find_gates_file(Path.cwd())
    inline_spec = _load_gates_file(gates_file).model_dump(mode="json") if gates_file is not None else None

    endpoint = base_url.rstrip("/") + f"{API_PREFIX}/{urllib.parse.quote(policy_name, safe='')}/check"
    request_body: dict[str, Any] = {
        "transcript": excerpt,
        "session_id": session_id,
        "turn_id": turn_id,
        "repo": repo,
        "branch": branch,
        "executed_commands": executed_commands,
        "edited_paths": edited_paths,
        "loaded_context_paths": loaded_context_paths,
    }
    if inline_spec is not None:
        request_body["spec"] = inline_spec
    body = json.dumps(request_body).encode()
    request = urllib.request.Request(endpoint, data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "application/json")
    request.add_header("Otari-Key", key)

    try:
        # A subscription-backend judge gate shells out to a real `claude` call server-side.
        with urllib.request.urlopen(request, timeout=180) as response:
            status_code, raw = response.status, response.read()
    except urllib.error.HTTPError as error:
        status_code, raw = error.code, error.read()
    except (urllib.error.URLError, OSError) as exc:
        click.echo(json.dumps({"error": f"could not reach {base_url}: {exc}"}))
        raise SystemExit(2) from exc

    try:
        result = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        result = None

    if status_code == 404:
        click.echo(json.dumps({"error": f"policy {policy_name!r} is not configured on the gateway"}))
        raise SystemExit(2)
    # Anything other than exactly 200 is "could not check", never "compliant": a 4xx has a
    # JSON dict body just as often as a real verdict does.
    if status_code != 200 or not isinstance(result, dict):
        click.echo(json.dumps({"error": f"unexpected response (HTTP {status_code})"}))
        raise SystemExit(2)

    click.echo(json.dumps(result))
    if not result.get("compliant", True):
        raise SystemExit(1)


@policy.command(name="give-up")
@click.argument("policy_name")
@click.option(
    "--session-id",
    required=True,
    help="Which session's retry loop is giving up. Required, since the marker only means something on one "
    "session's timeline.",
)
@click.option("--config", "-c", type=click.Path(exists=True, dir_okay=False), help="Path to config YAML file")
@click.option("--url", default=None, help="Gateway base URL. Default: derived from --config's host/port.")
@click.option("--api-key", default=None, help="Otari API key. Default: --config's master_key.")
def policy_give_up(policy_name: str, session_id: str, config: str | None, url: str | None, api_key: str | None) -> None:
    """Record that POLICY_NAME's check for SESSION_ID ended without ever reaching compliant.

    Called by the Stop hook when its retry-attempt cap is hit, so a session's timeline can
    tell "converged" apart from "exhausted its retries". Repo and branch are detected from
    the current directory exactly as `policy check` does.
    """
    import urllib.error
    import urllib.parse
    import urllib.request

    base_url, key = _base_url_and_key(config, url, api_key)

    repo_toplevel = _git_toplevel(Path.cwd())
    repo = repo_toplevel.name if repo_toplevel is not None else None
    branch = _current_branch_label(Path.cwd())

    endpoint = base_url.rstrip("/") + f"{API_PREFIX}/{urllib.parse.quote(policy_name, safe='')}/give-up"
    body = json.dumps({"session_id": session_id, "repo": repo, "branch": branch}).encode()
    request = urllib.request.Request(endpoint, data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "application/json")
    request.add_header("Otari-Key", key)

    try:
        with urllib.request.urlopen(request, timeout=10):
            pass
    except urllib.error.HTTPError as error:
        click.echo(json.dumps({"error": f"unexpected response (HTTP {error.code})"}))
        raise SystemExit(2) from error
    except (urllib.error.URLError, OSError) as exc:
        click.echo(json.dumps({"error": f"could not reach {base_url}: {exc}"}))
        raise SystemExit(2) from exc


# --------------------------------------------------------------------------- #
# PreToolUse: deny a banned command before it runs
# --------------------------------------------------------------------------- #


def preventable_gates(spec: PolicyCheckSpec) -> list[CommandGateSpec]:
    """The gates a PreToolUse hook can enforce from one Bash call in isolation.

    Only ``must_not_run`` command gates without a ``paths`` condition: a
    ``must_run_and_succeed`` gate is a whole-turn fact, and a ``paths`` condition needs
    this turn's edited paths, which one tool call cannot know.
    """
    return [
        gate
        for gate in spec.gates
        if isinstance(gate, CommandGateSpec) and gate.mode == "must_not_run" and gate.paths is None
    ]


def first_violated_gate(command: str, gates: list[CommandGateSpec]) -> CommandGateSpec | None:
    """The first gate whose pattern matches ``command`` after the same masking the Stop hook applies."""
    from otari_agent_gates.transcript import strip_inert_shell_regions

    masked = strip_inert_shell_regions(command)
    for gate in gates:
        if re.search(gate.pattern, masked):
            return gate
    return None


def evaluate_pretooluse(payload: Any, gates_file: Path | None) -> CommandGateSpec | None:
    """The gate a PreToolUse payload violates, or ``None`` to allow the call.

    Fails open on anything unexpected (a non-Bash tool, a missing or invalid gates file,
    a malformed payload): a rule that cannot be evaluated must never make Claude Code
    itself unusable.
    """
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return None
    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or gates_file is None:
        return None
    try:
        spec = load_gates_spec(gates_file)
    except GatesFileError:
        return None
    gates = preventable_gates(spec)
    if not gates:
        return None
    return first_violated_gate(command, gates)


@policy.command(name="pretooluse")
@click.option(
    "--gates-file",
    "gates_file_path",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help=f"Path to a gates file. Default: auto-discover {GATES_FILENAME} by walking upward from the current directory.",
)
def policy_pretooluse(gates_file_path: str | None) -> None:
    """Deny a Bash call that matches a must_not_run command gate, before it runs.

    Reads a Claude Code PreToolUse payload from stdin. On a match, prints the hook's deny
    JSON to stderr and exits 2; otherwise exits 0. Never talks to a gateway, and fails open
    on anything it cannot evaluate. Wire it through hooks/pretooluse_hook.py.
    """
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        raise SystemExit(0) from None
    gates_file = Path(gates_file_path) if gates_file_path else find_gates_file(Path.cwd())
    violated = evaluate_pretooluse(payload, gates_file)
    if violated is None:
        raise SystemExit(0)
    click.echo(
        json.dumps({"hookSpecificOutput": {"permissionDecision": "deny"}, "systemMessage": violated.message}),
        err=True,
    )
    raise SystemExit(2)


# --------------------------------------------------------------------------- #
# generate: decompose a plan into gates
# --------------------------------------------------------------------------- #

GateTypeName = Literal["llm_judge", "command", "scoped_guidance", "edited_path"]


@dataclass(frozen=True)
class Criterion:
    """One acceptance criterion, the single representation ``render_policy_yaml`` serializes from.

    ``gate_type`` defaults to ``llm_judge``; the three mechanical shapes carry the extra
    fields that gate type needs. ``_normalize_criteria`` falls back to ``llm_judge`` when a
    mechanical classification is missing its required fields, since a broken mechanical
    gate would silently pass or fail every run.
    """

    name: str
    description: str
    gate_type: GateTypeName = "llm_judge"
    pattern: str | None = None
    mode: str | None = None
    directory: str | None = None
    paths: list[str] | None = None


_MAX_PLAN_CHARS = 40_000
_DEFAULT_MAX_CRITERIA = 6
_DECOMPOSITION_PROMPT_TEMPLATE = (
    "You are helping turn an engineering plan into a checklist an automated auditor can use "
    "to grade whether an AI coding agent actually followed it.\n\n"
    "Read the plan below and produce a JSON array of narrow, objectively-checkable acceptance "
    "criteria. Each one must be a single concrete fact a reviewer could verify as true or false "
    "by reading the agent's transcript and the resulting diff, with no room for subjective "
    'judgment, for example "the demo judge_model in config.example.yml must reference a '
    'keyless/local provider, not a paid one," never "code should be good" or "tests should '
    'pass" without saying which tests or what passing means here.\n\n'
    "Do not invent criteria the plan does not support. Skip anything already effectively "
    "enforced by the codebase's own tests or CI unless the plan explicitly calls out a change "
    "to it. Produce at most {max_criteria} criteria; prefer fewer, sharper criteria over many "
    "vague ones.\n\n"
    "For each criterion, also classify which of four gate shapes checks it, and prefer the "
    "narrowest mechanical shape that fits *unconditionally*, one of these free, model-free "
    "checks over an LLM judging free text, wherever the criterion holds regardless of what else "
    "changed:\n"
    '- "command": the criterion is really "a specific shell command must have run and succeeded, '
    'or must never have run" (e.g. "make lint was run", "git push --force was never run"). Also '
    "set `pattern` (a substring/regex matching the command text) and `mode` "
    "(`must_run_and_succeed` or `must_not_run`). The one condition this shape can express: if "
    'the requirement only applies when specific paths changed (e.g. "web/ changes must run pnpm '
    '--dir web run lint separately"), also set `paths` to a JSON array of fnmatch-style glob '
    "patterns matched against paths relative to the repo root, the same idea as a GitHub Actions "
    "workflow's own `paths:` filter, but plain shell-glob syntax, not GitHub Actions' own: use "
    'a single `*` for "anything, including across a `/`" (e.g. `["web/*"]` already means anywhere '
    'under web/, not just one level down) and never `**`. A double star does not mean "any depth" '
    "here the way it does in a real .gitignore or a GHA workflow, and a pattern built assuming it "
    "does (e.g. `web/**/*.ts`) silently fails to match a file directly under web/ itself, with no "
    "error to reveal the mistake. Leave `paths` null/omitted when the command is required "
    "unconditionally, every turn.\n"
    '- "edited_path": the criterion is really "a file matching a path pattern must, or must not, '
    'have been edited", full stop (e.g. "CHANGELOG.md must not be hand-edited"). Also set '
    "`pattern` (a regex matching the file path) and `mode` (`must_not_edit` or `must_edit`).\n"
    '- "scoped_guidance": the criterion is really "before editing files under one specific '
    "directory, that directory's own AGENTS.md/CLAUDE.md must have been loaded into context\". "
    'Also set `directory` (e.g. "web/"), exactly one directory, unlike command\'s `paths`, since '
    "it also names which directory's own guidance file is being checked for.\n"
    '- "llm_judge" (default, use this whenever unsure): the criterion is conditional on '
    "something other than which paths changed, about file *content* rather than which files "
    "were touched or which commands ran, about whether something was *committed* (git "
    "add/commit) rather than merely edited or run, or needs any subjective/semantic judgment at "
    "all. A wrong mechanical classification silently passes or fails every run with no "
    "visibility, so misclassifying toward llm_judge is always the safer mistake.\n\n"
    "## Plan\n{plan_text}\n\n"
    "Reply with ONLY a JSON array on one line, no markdown fences and no other text. Each "
    "element must have exactly this shape (omit `pattern`/`mode`/`directory`/`paths` entirely, "
    'or set them null, when `gate_type` is "llm_judge" or does not need that field):\n'
    '{{"name": "short-kebab-case-slug", "description": "one or two sentence acceptance '
    "criterion, self-contained, no reference to 'the plan' or 'above'\", \"gate_type\": "
    '"llm_judge", "pattern": null, "mode": null, "directory": null, "paths": null}}'
)


def decompose_plan(plan_text: str, *, max_criteria: int, claude_binary: str | None = None) -> list[Criterion]:
    """Ask the local ``claude`` CLI to decompose ``plan_text`` into acceptance criteria."""
    from otari_agent_gates import headless

    prompt = _DECOMPOSITION_PROMPT_TEMPLATE.format(max_criteria=max_criteria, plan_text=plan_text)
    last_error: str | None = None
    for attempt in range(1, headless._MAX_JUDGE_ATTEMPTS + 1):
        try:
            result = headless.run_claude_headless(prompt, binary=claude_binary)
        except (headless.ClaudeCliNotFoundError, headless.ClaudeCliCallError) as exc:
            last_error = str(exc)
            click.echo(f"policy generate: claude CLI call failed (attempt {attempt}): {exc}", err=True)
            continue
        parsed = headless.extract_json(result.text)
        criteria = _normalize_criteria(parsed, max_criteria=max_criteria)
        if criteria:
            return criteria
        last_error = "reply was not a usable JSON array of {name, description} objects"
        click.echo(f"policy generate: {last_error} (attempt {attempt})", err=True)
    raise SystemExit(f"error: decomposition failed after {headless._MAX_JUDGE_ATTEMPTS} attempts: {last_error}")


_MECHANICAL_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "command": ("pattern", "mode"),
    "edited_path": ("pattern", "mode"),
    "scoped_guidance": ("directory",),
}


def _normalize_criteria(parsed: Any, *, max_criteria: int) -> list[Criterion]:
    if not isinstance(parsed, list):
        return []
    seen_names: dict[str, int] = {}
    criteria: list[Criterion] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        description = str(item.get("description", "")).strip()
        if not name or not description:
            continue
        slug = _slugify(name)
        if slug in seen_names:
            seen_names[slug] += 1
            slug = f"{slug}-{seen_names[slug]}"
        else:
            seen_names[slug] = 1

        raw_gate_type = item.get("gate_type")
        gate_type_candidate = raw_gate_type if isinstance(raw_gate_type, str) else ""
        pattern = item.get("pattern") if isinstance(item.get("pattern"), str) else None
        mode = item.get("mode") if isinstance(item.get("mode"), str) else None
        directory = item.get("directory") if isinstance(item.get("directory"), str) else None
        raw_paths = item.get("paths")
        paths = [p for p in raw_paths if isinstance(p, str)] or None if isinstance(raw_paths, list) else None
        required = _MECHANICAL_REQUIRED_FIELDS.get(gate_type_candidate, ())
        values = {"pattern": pattern, "mode": mode, "directory": directory}
        gate_type: GateTypeName = "llm_judge"
        if gate_type_candidate in _MECHANICAL_REQUIRED_FIELDS and all(values[field] for field in required):
            gate_type = cast("GateTypeName", gate_type_candidate)
        else:
            # Missing mechanical fields, or an unknown gate_type: fall back to the always-valid
            # llm_judge shape rather than emit a gate that would mis-evaluate every run.
            pattern, mode, directory, paths = None, None, None, None

        criteria.append(
            Criterion(
                name=slug,
                description=description,
                gate_type=gate_type,
                pattern=pattern,
                mode=mode,
                directory=directory,
                paths=paths,
            )
        )
        if len(criteria) >= max_criteria:
            break
    return criteria


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")
    return slug or "criterion"


def render_policy_yaml(
    criteria: list[Criterion],
    *,
    judge_backend: str = "subscription",
    judge_model: str | None = None,
    on_unavailable: str = "block",
) -> str:
    """A ``.otari-gates.yml`` document, one gate per criterion.

    A subscription judge gate omits ``judge_model`` entirely; a provider one requires it.
    Neither applies to a mechanical gate.
    """

    def _gate(criterion: Criterion) -> dict[str, Any]:
        if criterion.gate_type == "command":
            command_gate: dict[str, Any] = {
                "type": "command",
                "name": criterion.name,
                "pattern": criterion.pattern,
                "mode": criterion.mode,
                "message": criterion.description,
            }
            if criterion.paths is not None:
                command_gate["paths"] = criterion.paths
            return command_gate
        if criterion.gate_type == "edited_path":
            return {
                "type": "edited_path",
                "name": criterion.name,
                "pattern": criterion.pattern,
                "mode": criterion.mode,
                "message": criterion.description,
            }
        if criterion.gate_type == "scoped_guidance":
            return {
                "type": "scoped_guidance",
                "name": criterion.name,
                "directory": criterion.directory,
                "message": criterion.description,
            }
        gate: dict[str, Any] = {
            "type": "llm_judge",
            "name": criterion.name,
            "judge_backend": judge_backend,
            "rules": criterion.description,
        }
        if judge_backend == "provider":
            gate["judge_model"] = judge_model
        return gate

    spec = {
        "on_unavailable": on_unavailable,
        "gates": [_gate(criterion) for criterion in criteria],
    }
    return yaml.safe_dump(spec, sort_keys=False, default_flow_style=False)


@policy.command(name="generate")
@click.argument("plan_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--judge-backend", type=click.Choice(["provider", "subscription"]), default="subscription")
@click.option("--judge-model", default=None, help="Required (and only meaningful) with --judge-backend provider.")
@click.option("--on-unavailable", type=click.Choice(["block", "monitor"]), default="block")
@click.option("--yaml-out", default=None, help=f"Default: {GATES_FILENAME} in the current directory. '-' for stdout.")
@click.option("--max-criteria", type=int, default=_DEFAULT_MAX_CRITERIA)
@click.option("--claude-binary", default=None, help="Override for a non-PATH claude install.")
@click.option("--dry-run", is_flag=True, help="Print criteria, write nothing.")
def policy_generate(
    plan_path: str,
    judge_backend: str,
    judge_model: str | None,
    on_unavailable: str,
    yaml_out: str | None,
    max_criteria: int,
    claude_binary: str | None,
    dry_run: bool,
) -> None:
    """Decompose PLAN_PATH into acceptance-criteria gates, via the local `claude` CLI.

    Local-only: writes a repo's own .otari-gates.yml, meant to be committed at the repo
    root and discovered by `otari policy check`. Each criterion is classified toward the
    narrowest gate shape that fits it unconditionally; most still render as llm_judge.
    """
    if judge_backend == "provider" and not judge_model:
        raise click.BadParameter("--judge-model is required with --judge-backend provider")

    plan_text = Path(plan_path).read_text(encoding="utf-8")
    if len(plan_text) > _MAX_PLAN_CHARS:
        click.echo(f"policy generate: plan is {len(plan_text)} chars, truncating to {_MAX_PLAN_CHARS}", err=True)
        plan_text = plan_text[:_MAX_PLAN_CHARS]

    criteria = decompose_plan(plan_text, max_criteria=max_criteria, claude_binary=claude_binary)

    if dry_run:
        for criterion in criteria:
            click.echo(f"- [{criterion.gate_type}] {criterion.name}: {criterion.description}")
        return

    resolved_yaml_out = yaml_out or GATES_FILENAME

    yaml_text = render_policy_yaml(
        criteria,
        judge_backend=judge_backend,
        judge_model=judge_model,
        on_unavailable=on_unavailable,
    )

    if resolved_yaml_out == "-":
        click.echo(yaml_text)
    else:
        Path(resolved_yaml_out).write_text(yaml_text, encoding="utf-8")
        click.echo(f"policy generate: wrote {len(criteria)} criteria to {resolved_yaml_out}", err=True)
