# Warden

An [Otari](https://github.com/mozilla-ai/otari) plugin that reviews what your coding
agent actually did, so you do not have to check its work yourself. A repo states its
rules once as a **policy**, an ordered list of **gates**, and every Claude Code turn
is checked against them. A failing verdict blocks the session and feeds the
violations back to the model as instructions, so Claude Code fixes them and tries
again, with no human relaying anything. Four gate types are mechanical (free,
deterministic, run first); the fifth asks a model, either through Otari's own
providers or through the `claude` CLI login you already have, at no marginal cost.

It has two halves. Hooks on your machine give prevention (a `PreToolUse` hook denies
a banned command before it runs) and the block-and-retry loop (a `Stop` hook sends
the turn's transcript to the gateway and blocks on a failing verdict). The gateway
itself grades every agent's traffic that flows through Otari, with nothing installed
on the client.

![Warden inside the Otari dashboard: the Marketplace card and its settings, the Warden page with its runs, and an Activity row where a forced push was refused on the wire](docs/demo.gif)

Above: Warden installed from the Marketplace with its settings editable in
place, its page under Build > Tools listing reviewed runs, and the Activity
log showing a turn where the gateway refused a `git push --force` before the
agent could run it.

## Quick start

1. **Install the plugin into Otari.** Open Marketplace in the Otari dashboard and
   install Warden, or run

   ```
   otari plugins install njbrake/warden
   ```

   then restart `otari serve`. `otari plugins list` shows it as `loaded`.

2. **Put a `.otari-gates.yml` at the root of a repo.**

   ```yaml
   # .otari-gates.yml
   on_unavailable: block
   gates:
     - type: command
       name: no-force-push
       pattern: "git\\s+push\\b.*?(?:--force(?!-)\\b|(?<!\\S)-f\\b)"
       mode: must_not_run
       message: "Never force-push."
     - type: command
       name: tests-ran
       pattern: "pytest"
       mode: must_run_and_succeed
       paths: ["src/*", "tests/*"]
       message: "Run pytest after changing source or tests."
     - type: llm_judge
       name: agents-md-compliance
       judge_backend: subscription
       rules_file: AGENTS.md
   ```

3. **Wire the hooks.** Copy the two scripts from `src/otari_warden/hooks/` to
   your machine (standard library only) and paste this into `~/.claude/settings.json`:

   ```json
   {
     "hooks": {
       "Stop": [
         {
           "hooks": [
             {"type": "command", "command": "python3 /path/to/policy_check_hook.py"}
           ]
         }
       ],
       "PreToolUse": [
         {
           "matcher": "Bash",
           "hooks": [
             {"type": "command", "command": "python3 /path/to/pretooluse_hook.py"}
           ]
         }
       ]
     }
   }
   ```

4. **Point the hooks at the gateway.** In the shell Claude Code runs from:

   ```sh
   export OTARI_URL=https://otari.example.com   # your gateway
   export OTARI_API_KEY=sk-...                  # an ordinary Otari API key, created in the dashboard
   export OTARI_POLICY_NAME=team-rules          # the label runs are recorded under
   export OTARI_CLI_PATH=/path/to/otari         # only when otari is not on PATH
   ```

5. **Run a Claude Code session**, then open Warden in the Otari dashboard
   sidebar, under Build > Tools, to watch the runs come in.

## How it works

```
Claude Code turn ends
  -> Stop hook (hooks/policy_check_hook.py, standard library only)
  -> otari warden check <name> --claude-transcript <path>
       reads the transcript, extracts the current turn, discovers .otari-gates.yml
  -> POST /api/v1/plugins/warden/policy-checks/<name>/check
       mechanical gates first; judge gates only if they all pass
  -> verdict recorded in history; non-compliant => hook exits 2 with the violations
  -> Claude Code keeps the session going with those violations as instructions
```

### Checking traffic instead of transcripts

An agent that talks to its model through Otari puts every tool call and every
result on the wire, so the gateway can judge the same gates with nothing
installed on the client and for every agent at once. Name what to check under
the plugin's config block:

```yaml
plugins:
  warden:
    traffic:
      policy: team-rules        # a stored policy, or:
      gates:                    # inline gates, the same shape as .otari-gates.yml
        - type: command
          name: no-force-push
          pattern: "git\\s+push\\b.*--force"
          mode: must_not_run
          message: "Never force-push."
```

On every inference request the plugin evaluates the `command` and
`edited_path` gates against the previous turn (the tool calls the agent made
and the results it got back) and, for each tool call in the model's answer,
the `must_not_run` gates against the command about to run. A call a gate
refuses never reaches the agent: Otari removes it from the response (holding
it back in a stream until it is whole) and puts the gate's message in its
place, so the model sees why and tries something else. What fired, and what
was refused, is recorded on the request's usage row under
`plugin_annotations.warden` and shown on the dashboard's Activity page.

The other gate types stay with the hook: `scoped_guidance` needs the loaded
context, `deterministic` the rendered transcript, and `llm_judge` a model call
that should not be paid per request. So do the repo's own `.otari-gates.yml`,
the git working-tree view, and the block-and-retry loop, which only a client
can drive.

## Install

Warden needs an Otari deployment with the plugin seam (`gateway.plugins`,
plugin API 1). It runs in standalone mode; a hybrid gateway lists it as
disabled, since a `provider`-backend judge has nothing local to resolve
against there. Then any of:

- **Dashboard.** Open Marketplace in the Otari dashboard, find Warden, and
  install it. Restart the gateway when the banner says so. This needs
  `plugins.allow_install: true` in the gateway's `config.yml`.
- **CLI.** `otari plugins install njbrake/warden`, then restart
  `otari serve`. This writes into the gateway's plugins directory.
- **Package.** Into the same environment Otari runs in:
  `pip install otari-warden` or `uv pip install otari-warden`. Otari
  discovers it through the `otari.plugins` entry point on the next start.

On startup (with `auto_migrate`, the default) or on `otari migrate`, the plugin
creates its two tables through its own Alembic chain, stamped in
`alembic_version_warden`, separate from Otari's own. `otari plugins list`
and `GET /api/v1/plugins` show it as `loaded`.

## Configuration

Loading the plugin is the switch; there is no `enabled` flag. Everything else is
optional:

```yaml
# config.yml
plugins:
  disabled: []                  # add "warden" to turn it off without uninstalling
  warden:
    judge_timeout_seconds: 120  # cap on one subscription-backend judge call
```

`judge_timeout_seconds` is declared in the manifest, so the Marketplace's
Installed list shows it on the plugin's card, where an operator can change it
without a restart; a value set there wins over `config.yml`. An unknown key
under `plugins.warden` fails the plugin load (it is listed as `failed`
with the reason, and the gateway boots without it).

A policy is never declared in `config.yml`. It comes from a repo's own
`.otari-gates.yml` or from a policy stored through the dashboard; both are read
fresh on every check. `otari warden generate plan.md` can draft a gates file from
an engineering plan. With a gates file present, `OTARI_POLICY_NAME` is only the
label runs are recorded under.

## Hooks

Both scripts under `src/otari_warden/hooks/` are standard library only, so
they can be copied to any machine that has Claude Code and the `otari` CLI on
`PATH`. Each is a thin dispatcher: the Stop hook calls `otari warden check`, the
PreToolUse hook calls `otari warden pretooluse`. The settings JSON is the one in
the Quick start; it also works in a project's `.claude/settings.local.json`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `OTARI_POLICY_NAME` | required (Stop hook) | Policy to check, or the label when a gates file is found |
| `OTARI_URL` | derived from `config.yml` | Gateway base URL, read by `otari warden check` and `give-up` |
| `OTARI_API_KEY` | `config.yml`'s `master_key` | An ordinary Otari API key for that gateway |
| `OTARI_CLI_PATH` | `otari` on `PATH` | Override for a non-`PATH` `otari` install |
| `OTARI_POLICY_CHECK_MAX_ATTEMPTS` | `3` | Retry cap per session, a retry after a block is checked again |
| `OTARI_POLICY_CHECK_FAIL_MODE` | `open` | `open` never blocks a session over a check that could not run; `closed` does |

`OTARI_URL` and `OTARI_API_KEY` are what make the hooks work from a machine that
is not the gateway's. Without them, `otari warden check` derives the URL and the
master key from the `config.yml` it finds, normally the one `otari serve` was
started with, so on the gateway's own machine nothing needs exporting. `--url`
and `--api-key` on the command itself override both.

The Stop hook is a retrospective reviewer. The PreToolUse hook is prevention: it
reads every `must_not_run` command gate from the discovered `.otari-gates.yml`
(skipping any with a `paths` condition, which needs the whole turn) and denies a
matching Bash call with that gate's own message, so one declaration serves both.
It never contacts a gateway and fails open on anything it cannot evaluate. Details
in [docs/hooks.md](docs/hooks.md).

## Gate types

| Type | Checks | Evidence |
| --- | --- | --- |
| `deterministic` | A regex against the transcript's rendered text | Transcript excerpt |
| `command` | A regex against a Bash command that actually ran, and whether it errored; optional `paths` condition | Structured `tool_use`/`tool_result` blocks |
| `scoped_guidance` | A directory's `AGENTS.md`/`CLAUDE.md` was loaded before a file under it was edited | `nested_memory` attachments plus `Edit`/`Write`/`NotebookEdit` calls |
| `edited_path` | A regex against which files this turn edited | `Edit`/`Write`/`NotebookEdit` calls |
| `llm_judge` | Free-text rules, judged by a model | Transcript excerpt |

The first four run first; any failure skips every judge gate that turn. Judge gates
run concurrently and aggregate. Field reference in [docs/gates.md](docs/gates.md).

## Judge backends

- **`provider`** (default) resolves `judge_model` through Otari's own provider
  configuration, a paid API or a free local model as you prefer.
- **`subscription`** shells out to the locally installed `claude` CLI under
  `--safe-mode`, using whatever session is already logged in, at zero marginal
  cost. `otari serve` must run on the same machine as that login. The CLI's own
  envelope reports what the tokens would have cost through the API; the dashboard
  shows that figure as an equivalent, not a bill.

## API

Mounted under `/api/v1/plugins/warden/policy-checks`:

| Method and path | Auth | Purpose |
| --- | --- | --- |
| `POST /{policy_name}/check` | API key or master key | Evaluate a transcript excerpt (inline `spec` wins over a stored policy) |
| `POST /{policy_name}/give-up` | API key or master key | Record that a session's retry loop hit its cap |
| `GET/POST /policies`, `GET/PUT/DELETE /policies/{name}` | operator | Stored policies |
| `GET /history`, `/history/count`, `/history/{id}`, `POST /history/{id}/dismiss`, `DELETE /history?older_than_days=N` | operator | Run history |
| `GET /repos`, `/branches`, `/sessions` | operator | Grouped summaries with run counts and cost totals |

Operator routes take the dashboard session cookie or the master key, like Otari's
own management routes. The dashboard page is served at `/plugins/warden/ui/`.

## Development

```
git clone https://github.com/njbrake/warden
cd otari-warden
uv sync          # installs gateway from mozilla-ai/otari main, per [tool.uv.sources]
make lint        # ruff check + format check
make test        # pytest, SQLite only, no Docker
make ui          # pnpm install + build; commits land in src/otari_warden/static/
```

Until the plugin seam ships on Otari's `main`, `uv sync` resolves a gateway that
has no `gateway.plugins` module and the tests cannot import. Run them against a
local checkout of the seam branch instead: install this repo editable into that
checkout's environment and use its interpreter.

```
uv pip install --python /path/to/otari/.venv/bin/python -e .
/path/to/otari/.venv/bin/python -m pytest tests -q
```

The route tests run over SQLite through the plugin's own migration chain, so
nothing here needs PostgreSQL. `web/` is a small Vite + React app on HeroUI v3 and
Tailwind v4 with hash routing (it lives in an iframe under a static mount); see
[web/README.md](web/README.md). The built bundle is committed so an install from
the marketplace or GitHub archive ships a working page.

More: [docs/gates.md](docs/gates.md), [docs/hooks.md](docs/hooks.md),
[docs/dashboard.md](docs/dashboard.md).

## License

Apache-2.0. Copyright Mozilla.ai.
