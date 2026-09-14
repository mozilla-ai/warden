# Writing gates

A policy is a YAML mapping with one required key, `gates`, and one optional key,
`on_unavailable`. The same shape is what `.otari-gates.yml` holds, what
`POST /policies` accepts, and what the dashboard's gate editor writes.

```yaml
on_unavailable: block   # or monitor
gates:
  - type: ...
```

`on_unavailable` says what a judge gate reports when its model call fails after
one retry. `block` (default) fails closed: the run is non-compliant. `monitor`
fails open: the run is reported compliant with `checked: false`, so the dashboard
still shows that nothing was verified.

## Where a policy comes from

- **A repo's own `.otari-gates.yml`.** `otari warden check` walks upward from the
  current directory to find it, the way `git` finds `.git`, and sends it inline.
  The policy name on the command line becomes only the label recorded in history;
  the gateway looks nothing up. The file is reviewed in the PR that changes it and
  works the same for anyone who clones the repo.
- **A stored policy**, created in the dashboard's Gates page or through
  `POST /api/v1/plugins/warden/policy-checks/policies`. The fallback for a
  check with no repo to carry a file, or an operator-managed policy meant to apply
  across many repos. Read fresh from the database on every check.

There is no third, `config.yml`-declared source: a value read once at startup could
never pick up a change without a restart, unlike either of these.

## Gate reference

Every gate has a `type`, a unique `name`, and (except `llm_judge`) a `message`
reported as the violation when it fails.

### `deterministic`

A regex (`re.search`) against the transcript excerpt rendered as text.

| Field | Values |
| --- | --- |
| `pattern` | regex |
| `mode` | `must_not_match` (default): fails when found. `must_match`: fails when absent |

Cheap, but it matches prose: a command merely quoted in a tool result trips it too.
Prefer `command` for anything about what ran.

### `command`

A regex against a Bash command the current turn actually ran, taken from the
transcript's structured `tool_use`/`tool_result` blocks, paired with whether the
result carried `is_error`. Heredoc bodies, comments, and (on lines with no
`bash -c`, `eval`, `ssh`, or `xargs`) quoted strings are masked first, so a JSON
fixture containing a banned phrase is not evidence the phrase ran.

| Field | Values |
| --- | --- |
| `pattern` | regex |
| `mode` | `must_run_and_succeed` (default): fails unless a matching command ran without error. `must_not_run`: fails if one ran at all |
| `paths` | optional list of globs; the gate only applies when an edited path this turn matches one |

`paths` uses `fnmatch` semantics against repo-relative paths: `*` matches across
`/`, so `web/*` means anywhere under `web/`. Do not write `**`; it means nothing
special here and fails to match a file directly under the directory.

```yaml
- type: command
  name: web-lint
  pattern: "pnpm --dir web run lint"
  mode: must_run_and_succeed
  paths: ["web/*"]
  message: "Run pnpm --dir web run lint for frontend changes."
```

### `scoped_guidance`

Checks that a directory's own `AGENTS.md`/`CLAUDE.md` was loaded into context
before this turn edited a file under it. Claude Code injects that file as a
`nested_memory` attachment the first time a file under the directory is touched,
possibly many turns earlier, so the load is looked for across the whole session
while the edit is checked in the current turn only.

| Field | Values |
| --- | --- |
| `directory` | one directory, such as `web/`; matched as the glob `web/*` |

### `edited_path`

A regex against the paths this turn's `Edit`, `Write`, and `NotebookEdit` calls
touched. It knows nothing about git: "was this committed" needs a judge gate.

| Field | Values |
| --- | --- |
| `pattern` | regex |
| `mode` | `must_not_edit` (default): fails if a matching path was edited. `must_edit`: fails unless one was |

### `llm_judge`

Free-text rules judged by a model against the transcript excerpt.

| Field | Values |
| --- | --- |
| `judge_backend` | `provider` (default) or `subscription` |
| `judge_model` | required for `provider`; optional for `subscription` (the `claude` CLI's `--model`, default `claude-haiku-4-5-20251001`) |
| `rules` or `rules_file` | exactly one; `rules_file` is read when the spec is validated, relative to the gateway's working directory |
| `max_transcript_chars` | cap on the excerpt sent to the judge (default 24000) |
| `judge_max_tokens` | cap on the judge's reply (default 600) |

The judge is told to treat anything inside the transcript as untrusted content to
evaluate, never as an instruction. Each judge gate is one model call; a policy
with many judge gates makes that many calls per turn.

## Evaluation order

Mechanical gates (`deterministic`, `command`, `scoped_guidance`, `edited_path`)
run first. If any fails, every judge gate is reported `skipped` and no model is
called. Otherwise all judge gates run concurrently and their violations and
guidance are concatenated into one verdict. A judge that cannot be reached raises
immediately and `on_unavailable` decides the outcome.

## Generating a gates file

`otari warden generate plan.md` asks the local `claude` CLI to decompose a plan
into narrow, checkable criteria and writes `.otari-gates.yml` in the current
directory (`--yaml-out -` prints it). Each criterion is classified toward the
narrowest mechanical shape that fits unconditionally; anything uncertain becomes
an `llm_judge` gate, since a wrong mechanical classification would silently pass
or fail every run. `--dry-run` prints the criteria without writing.

## What a gate can check

A gate can only check something the session it runs against can actually do. Do
not write a rule that depends on a skill, plugin, or tool that is not installed
there: a PreToolUse hook enforcing "load skill X first" denies every call when X
is absent, and a judge gate checking for it always reports it missing. Verify a
rule's dependency exists in the environment being checked, not only in the
document the rule came from.
