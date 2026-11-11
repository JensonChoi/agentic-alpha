# Agentic Alpha

A self-hosted agentic trading research application. **SIMULATION ONLY — NO REAL MONEY.** Every trade runs through an internal ledger. There are no brokerage integrations, credentials, execution modes, or order routes.

## Run locally

```sh
cp .env.example .env
docker compose up --build
```

Open http://localhost:8080; API documentation is at http://localhost:8000/docs. Create a VOO, momentum, or congressional experiment and run it. The worker processes queued experiments. No model account is needed. In **Experiment History**, use **Delete** and confirm to permanently remove an experiment and its saved portfolio, trades, decisions, and results. Cancel queued, running, or waiting experiments before deleting them. Shared datasets are retained.

The bundled dataset is **synthetic**, generated with a fixed seed, with a fictional legislator. It is not authentic financial history, and its returns do not measure investment performance. Actual simulator results populate the dashboard; there are no canned performance charts.

Without Docker (Python 3.12+, Node 22+, and uv):

```sh
cd backend
uv sync
uv run uvicorn app.main:app --port 8000
# Another terminal, also in backend:
uv run python -m app.worker
# Another terminal, from the repository root:
cd frontend
npm ci
npm run dev
```

SQLite is the local development fallback. Compose uses PostgreSQL and runs Alembic before startup. Only one worker is supported; PostgreSQL enforces that with an advisory lock. Do not run multiple SQLite workers.

## Strategies and models

- `buy_and_hold`: VOO allocation at the first eligible session open, with a disclosed 100% position budget.
- `momentum`: completed-bar 20/50-day crossovers, persistent bullish state, capped equal weights, alphabetical tie-breaking, configurable rebalance frequency.
- `congressional`: disclosure availability drives execution, with equal/fixed/midpoint-proportional purchase allocation and full-position exits on sell disclosures. Proportional sizes are approximations. Unsupported securities are skipped.
- `single_agent`: bounded indicator snapshot and simulated positions produce validated JSON proposals.
- `multi_agent`: three concurrent analysts followed by a portfolio decision model. Advisory risk recommendations cannot override deterministic controls.

Install a model in Ollama separately, configure `OLLAMA_BASE_URL`, and enter its exact model identifier in the form. Models are checked before queueing. For the optional Compose Ollama service, use `docker compose --profile ollama up -d` and set `OLLAMA_BASE_URL=http://ollama:11434`; pull your chosen model in that container. OpenAI-compatible inference uses `COMPATIBLE_BASE_URL`. Cloud use requires `ENABLE_CLOUD=true` and `OPENAI_API_KEY`; local failures never fall back to cloud.

Agents receive bounded read-only snapshots, not shell access or general web retrieval. News and fundamentals are explicitly unavailable. Outputs are validated; failures record no action. Historical models can contain future knowledge in their training and are not fully point-in-time clean.

## Import research data

From `backend`:

```sh
uv run python -m app.cli import prices.csv --id research-v1 --provenance 'Source, license, retrieval date, and limitations'
```

CSV/Parquet columns: `date,ticker,open,high,low,close,volume`. Prices must be **raw**, not dividend-adjusted. Use a new dataset ID for each immutable version. Optional `--disclosures disclosures.json` and `--actions actions.json` import JSON arrays. The API also accepts `POST /api/datasets/import`; see its OpenAPI schema.

Disclosure records contain `id`, `person`, `ticker`, `action` (BUY/SELL), `transaction_date`, `disclosure_date`, optional `published_at`, `security_type` (stock/etf), `value_low`, `value_high`, and `provenance`. Date-only records are actionable at the next trading-session open. Options are never converted to shares. An `amends` identifier groups repeated disclosures; previously processed identities are not traded twice.

Corporate actions contain `date,ticker,type` and either `ratio` for a split or per-share `amount` for a dividend. Dates must correspond to the supplied raw-price accounting convention. Dividend reinvestment is optional and uses an available opening price. Do not submit adjusted prices alongside distributions.

There is no bundled authenticated historical provider. Acquire authorized data separately; provider subscriptions, licensing and redistribution rights remain the operator's responsibility. Imports do not resolve survivorship bias, symbol changes, delistings, or source errors automatically. Missing execution prices never get forward-filled; stale last observations may mark existing holdings and should be considered when interpreting results.

## Forward simulations

Create an experiment with `mode: "forward"` using the API, a suitable start/end range and current imported data. Only sessions whose official closing time has passed are evaluated. The worker persists state after each processed session, waits, and checks again every minute. No new data means no new fills.

Import an extended immutable dataset and POST `{"dataset":"research-v2"}` to `/api/experiments/{id}/advance`. The old bars must remain unchanged. This queues processing of newly available sessions with the saved ledger, pending proposals, and strategy state. External data acquisition is operator-managed; the application does not poll a commercial feed. Canceling a waiting experiment stops scheduling.

## Methodology and persistence

Signals use completed bars and fill at the following available session open with configured adverse slippage and fees. End-of-backtest pending orders are unfilled. Sells precede buys. Invalid proposals are rejected; purchases are capped by cash and total exposure at fill time. Decimal ledger arithmetic prevents negative cash and shares. A transaction publishes result tables and ledger records atomically; deterministic fill IDs prevent duplicates.

Experiments persist configurations, checkpoints, snapshots, proposals, decisions, fills, positions, metrics, and dataset checksums. Restart resumes saved daily state without calling models for already checkpointed decisions. A crash during a model call may require that call again. Configuration snapshots and exports support inspection; the export endpoint contains the complete recorded result.

Returns use simulated equity. CAGR uses actual elapsed days / 365.25; volatility uses sample daily standard deviation × √252. Sharpe assumes zero risk-free rate. Sortino uses downside RMS and 252 sessions/year. Maximum drawdown compares equity to its running peak including initial capital. Undefined ratios are null. Turnover is gross traded notional / initial capital. Realized sales use FIFO lots; holding duration averages matched lot durations. Split-adjusted FIFO P&L is not yet supported, so realized-trade statistics on datasets with splits should not be used. Inference cost estimates use configured local cost/hour and call duration; cloud price estimates are not supplied.

Compare date ranges, capital, costs, universes, information access and risk budgets before drawing conclusions. The passive benchmark's allocation budget differs from active defaults. No statistical-significance or investment-outperformance claims are made.

## Validation and reports

```sh
cd backend
uv run pytest -q
uv run python -m app.cli benchmark --output ../docs/benchmark-demo.md
cd ../frontend
npm run build
```

The benchmark report is generated from three real simulator runs on synthetic fixtures. See `docs/benchmark-demo.md`. API integration tests exercise create → queue → execute → inspect, authentication, and configuration validation.

The optional OpenClaw skill and setup instructions are in `integrations/openclaw/`. OpenClaw is not a runtime dependency.

## Security and current limitations

Compose binds published ports to loopback. Configure API_TOKEN and a TLS reverse proxy before nonlocal access. The dashboard's API client reads a token from session storage when supplied by an operator; there is no multi-user login UI. Inference endpoints are configured by the operator on the backend, never from agent output. Secrets stay on the backend.

This implementation includes the primary local research flows but is not the entire production-quality specification. Outstanding capabilities include authenticated market-data adapters, richer historical news/fundamental tools, token-budget enforcement and retries, detailed cloud pricing, configurable risk-free rates, benchmark-relative excess returns, advanced comparison date controls, and automated browser testing. PostgreSQL/Docker and real inference require separate environment verification. Treat import provenance and corporate-action consistency as operator responsibilities.
