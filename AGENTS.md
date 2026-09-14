# AGENTS.md

Guidance for agentic coding tools working in this repository.

## What this is

An Otari plugin. It runs inside the `otari` process and imports the `gateway`
package (Otari's internal import name) for auth dependencies, config, logging,
provider resolution, and the plugin migration helper. It ships nothing Otari
already has: `pyproject.toml` declares no runtime dependencies on purpose.

## Layout

- `src/otari_warden/otari-plugin.toml`: the manifest Otari reads before importing anything.
- `src/otari_warden/__init__.py`: `register(ctx)`, the only thing Otari calls.
- `models.py`: gate and policy schemas, the `plugins.warden` config model, and the two tables on the plugin's own `Base`.
- `service.py`, `routes.py`, `cli.py`, `transcript.py`, `headless.py`: evaluation, the API, `otari warden`, transcript extraction, the `claude` CLI wrapper.
- `migrations/`: the plugin's Alembic chain, stamped in `alembic_version_warden`. Never edit a shipped revision; add a new one.
- `hooks/`: the two Claude Code hook scripts. Standard library only, and thin: they shell out to `otari warden ...`.
- `static/`: the built dashboard page, committed. Do not hand-edit; run `make ui`.
- `web/`: the page's source (Vite, React 19, HeroUI v3, Tailwind v4, hash routing).
- `tests/`: pytest, SQLite only.

## Commands

- `make lint` (ruff check and format check), `make test`, `make ui`.
- Tests need a `gateway` with the plugin seam. Until that ships on Otari's `main`,
  install this repo editable into a local seam checkout's venv and run pytest with
  that interpreter (see README, Development).
- `pnpm --dir web run lint` type-checks the UI; `make ui` rebuilds `static/`.

## Conventions

- Match Otari's house style: async SQLAlchemy 2.0, pydantic models with `extra="forbid"`, line length 120.
- Never log or echo secrets. The route layer surfaces `public_detail` from a `PolicyCheckUnavailableError`, never the provider error.
- Route paths are relative to the mount Otari supplies (`/api/v1/plugins/warden`); the routers own only `/policy-checks`.
- Comments explain a non-obvious constraint, not what the code does or how it got here. Keep them short.
- Prose in US English, with no em dashes and no double hyphens as separators.
- The two hook scripts stay standard library only.
