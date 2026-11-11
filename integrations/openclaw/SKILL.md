---
name: agentic-alpha
description: Run and inspect Agentic Alpha simulated trading experiments through its local API. Use for simulation comparisons, portfolio inspection, and recorded trade explanations; never for real-money trading.
---

Use the configured Agentic Alpha base URL (default `http://localhost:8000`). Read `/openapi.json` for request schemas. If API_TOKEN is configured, send it only in the Authorization Bearer header; never include it in output.

- List strategies: GET `/api/strategies`.
- List datasets and provenance: GET `/api/datasets`.
- List experiments: GET `/api/experiments`.
- Create a requested simulation: POST `/api/experiments` with the user's dates, strategy, universe and simulated capital. Then POST `/api/experiments/{id}/run` with `{}`.
- Poll GET `/api/experiments/{id}` until completed, partial, failed, canceled, or waiting. Stop polling after 60 seconds and report the ID for later inspection.
- Inspect results using `/metrics`, `/equity`, `/trades`, `/orders`, `/decisions`, or `/export` below the experiment URL.
- Retrieve simulated holdings through GET `/api/portfolios/{experiment_id}`.
- Compare metrics only after identifying differences in dates, datasets, capital, risk limits and costs.
- Explain a decision using its stored rationale, snapshot, analyst recommendations, risk result and fill. Never invent hidden reasoning or missing evidence.

Always label balances simulated. Conspicuously identify synthetic demo data and incomplete experiments. Self-reported confidence is not a success probability. This backend contains no brokerage execution APIs; do not suggest otherwise or redirect simulation requests to a brokerage.
