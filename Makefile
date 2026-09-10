.PHONY: lint format test ui ui-lint

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

format:
	uv run ruff check --fix src tests
	uv run ruff format src tests

test:
	uv run pytest tests -q

ui-lint:
	pnpm --dir web install --frozen-lockfile
	pnpm --dir web run lint

ui:
	pnpm --dir web install --frozen-lockfile
	pnpm --dir web run build
