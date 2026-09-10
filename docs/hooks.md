# Hooks

Two Claude Code hooks ship under `src/otari_agent_gates/hooks/`. Both are
standard library only and thin: each reads Claude Code's JSON payload from stdin
and hands it to the `otari` CLI, which does the work. Copy them anywhere Claude
Code and `otari` are installed; they need no other file from this package.

## The Stop hook

`policy_check_hook.py` runs when a turn ends. It calls

```
otari policy check $OTARI_POLICY_NAME --claude-transcript <path> --session-id <id>
```

which extracts the current turn from the transcript (the text excerpt, the Bash
commands that ran and whether they errored, the paths edited, and every
`nested_memory` attachment in the session), discovers `.otari-gates.yml`, and posts
all of that to the gateway. Only this machine can read the transcript; the gateway
never does.

Exit codes of `otari policy check`, and what the hook does with each:

| Exit | Meaning | Hook |
| --- | --- | --- |
| 0 | compliant | exit 0, session stops normally |
| 1 | non-compliant | exit 2 with the violations and guidance on stderr; Claude Code feeds them back to the model and continues |
| 2 | could not check (unreachable gateway, unknown policy, malformed gates file, or a judge unreachable under `on_unavailable: block`) | `OTARI_POLICY_CHECK_FAIL_MODE=open` (default): exit 0. `closed`: exit 2 asking the model to retry or justify |

The hook keeps a per-session attempt count in a temp file. Once
`OTARI_POLICY_CHECK_MAX_ATTEMPTS` (default 3) blocks have happened, it lets the
session finish and records a `gave_up` marker through `otari policy give-up`, so
the session's timeline in the dashboard can tell "converged" apart from
"exhausted its retries". Claude Code's own `stop_hook_active` flag is honored too,
so a hook-triggered continuation never re-triggers the hook.

`otari policy check` reads the gateway URL and API key from the `config.yml` it
finds, normally the one `otari serve` was started with, so run both from the same
project directory. `--url` and `--api-key` override that.

## The PreToolUse hook

`pretooluse_hook.py` runs before every Bash tool call. It pipes the payload to
`otari policy pretooluse`, which:

1. discovers `.otari-gates.yml` from the current directory upward;
2. keeps every `command` gate with `mode: must_not_run` and no `paths` condition
   (a `must_run_and_succeed` gate is a whole-turn fact, and a `paths` condition
   needs the turn's edited paths, which one tool call cannot know);
3. masks the command the same way the Stop hook's command gate does;
4. on a match, prints `{"hookSpecificOutput": {"permissionDecision": "deny"},
   "systemMessage": <gate message>}` to stderr and exits 2.

The hook relays that deny verbatim. Everything else, including a missing `otari`,
a timeout, malformed stdin, or an invalid gates file, exits 0 and allows the call:
a bug in a prevention hook must never make Claude Code unusable. This path never
contacts a gateway.

Pair a `must_not_run` command gate with this hook whenever letting the command run
even once has a real consequence (a force-push, a destructive migration). The Stop
hook still checks the same gate afterward as a backstop.

## Settings

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

Claude Code registers hooks by absolute path, so the scripts live wherever you
keep them; the gates they enforce still come from the repo being worked on.

| Variable | Default | Purpose |
| --- | --- | --- |
| `OTARI_POLICY_NAME` | required (Stop hook) | Policy to check, or the label when a gates file is found |
| `OTARI_CLI_PATH` | `otari` on `PATH` | Override for a non-`PATH` `otari` install |
| `OTARI_POLICY_CHECK_MAX_ATTEMPTS` | `3` | Retry cap per session |
| `OTARI_POLICY_CHECK_FAIL_MODE` | `open` | `open` or `closed`, see above |
| `OTARI_CLAUDE_CLI_PATH` | `claude` on `PATH` | Read by the gateway for subscription judge gates, and by `otari policy generate` |
