# Repository Guidelines

## Project Structure & Module Organization

- `backend/app/` contains the FastAPI API, simulation engine, decimal ledger, strategy logic, inference adapters, persistence, worker, and CLI.
- `backend/tests/` holds accounting, timing, recovery, and API tests. `backend/migrations/` contains Alembic migrations.
- `frontend/src/` contains the React/TypeScript dashboard and styles; Vite builds into `frontend/dist/`.
- `configs/examples/` provides experiment configurations. `data/README.md` documents imports; runtime datasets live outside tracked source.
- `integrations/openclaw/` contains the optional simulation skill. `docs/prompts/001-mvp.md` defines the target specification; `README.md` records current limitations.

## Build, Test, and Development Commands

From the repository root:

```sh
cp .env.example .env
docker compose up --build
```

This starts PostgreSQL, migrations, API, worker, and dashboard at `http://localhost:8080`.

For local development, run from `backend/`:

- `uv sync` — install Python dependencies.
- `uv run uvicorn app.main:app --reload --port 8000` — start the API.
- `uv run python -m app.worker` — process experiments in a separate terminal.
- `uv run pytest -q` — run backend tests.
- `uv run python -m app.cli benchmark --output ../docs/benchmark-demo.md` — regenerate the synthetic benchmark report.

From `frontend/`, run `npm ci`, then `npm run dev`. Use `npm run build` for TypeScript checking and production compilation.

## Coding Style & Naming Conventions

Use four-space Python indentation, type annotations, `snake_case` functions/modules, and `PascalCase` classes. Use two-space indentation for new TypeScript, `PascalCase` components, and `camelCase` variables. Keep financial arithmetic in the backend ledger and validate external inputs with Pydantic. No formatter or lint script is configured; avoid unrelated formatting changes.

## Testing Guidelines

Use pytest and pytest-asyncio; name files `test_*.py` and tests `test_*`. Add deterministic regression tests for accounting, execution timing, risk checks, and recovery changes. Mock inference and avoid network-dependent tests. No coverage percentage is enforced. Frontend changes must pass the production build; document manual UI checks separately.

## Commit & Pull Request Guidelines

This checkout has no Git history, so no existing commit convention can be inferred. Use concise, imperative messages describing one logical change. PRs should explain behavior, relevant issues, tests performed, and limitations; include screenshots for UI changes. Flag migration and accounting impacts explicitly.

## Security & Simulation Constraints

Never add brokerage execution or real-money modes. Preserve simulation banners and synthetic-data labels. Keep credentials in backend configuration, never frontend code or committed files. All strategy proposals must pass shared risk validation and simulated execution; preserve point-in-time filtering and idempotent fills.
