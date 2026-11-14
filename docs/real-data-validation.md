# Validation record — November 13, 2026

All results are simulations. No provider data or credentials are checked into Git.

- Backend: 52 deterministic tests passed, covering acquisition normalization, identity and evidence validation, timing, split FIFO/accounting restart, dividend entitlement and independent reinvestment reconciliation, migration from the original schema, three-strategy persistence, blocked legs, and offline repeatability.
- Frontend: production TypeScript/Vite build passed. Vite reports its existing large-chunk advisory; dependency deprecation warnings remain in Python tests.
- Browser: native Chrome showed the local Comparison page, persisted suite count, and both completed baseline selections. Further UI interaction stopped when the user changed Chrome focus. Full form submission, expanded provenance and screenshot review were not completed. Browser connector host was unavailable; API integration and production build were verified separately.
- Quiver: no `QUIVER_API_KEY` in the process. Auth/pagination/schema behavior was tested with HTTP mocks, and normalized imports exercised all three strategies with synthetic fixtures. No real Quiver end-to-end or real congressional performance claim is made.
- PostgreSQL/Docker were not run; additive Alembic migration compatibility was exercised against an old-schema SQLite database. Existing legacy dataset metadata was preserved.

## Live Yahoo smoke and offline repetition

Dataset `yahoo-split-smoke-v1` acquired VOO and NVDA, benchmark April 1–30, 2024, with coverage January 17–April 30 and 51 preceding sessions per symbol. No missing sessions were reported. yfinance 0.2.66 retrieved the full adjustment horizon through November 13, 2026. NVDA's June 10, 2024 split (10:1, after the benchmark end) was retained as adjustment evidence and reversed from historical units. First normalized NVDA close: approximately 560.530014, volume 47,439,400. The normalized content hash is `a85a43bee672d903e21c5bc4a276fb1d9f8cfac0508f712f7542e7e02bb237c6`.

Run:

```sh
uv run python -m app.cli benchmark --dataset yahoo-split-smoke-v1 \
  --universe VOO,NVDA --start 2024-04-01 --end 2024-04-30 \
  --wait 20 --output ../reports/yahoo-split-smoke.md
```

Suite `221c6b4c-21d1-4e75-aa3f-533e03fcc5ee` completed through the existing worker:

| Strategy | Experiment | Total return | Fills |
|---|---|---:|---:|
| VOO | dee8a64f-3b9f-4db3-bae2-063941269a4b | -4.204181% | 1 |
| Momentum | 62e9df15-ef74-4ca0-a627-c173eedd8778 | -0.315607% | 8 |

Initial capital 100,000; fee zero; adverse slippage 5 bps; dividends paid in cash; 20/50 windows; weekly momentum rebalance; 10% active position cap versus 100% passive VOO. These are different exposure budgets, not evidence of strategy superiority. No dividends fell within this short benchmark range; deterministic tests separately reconcile cash dividends and reinvestment.

An independent VOO calculation (`capital / first_open_with_slippage * last_close`) matched persisted final equity 95,795.81892666304 to below 1e-8. The offline repeat suite `74787359-e67e-4002-976c-49b287bcebc1` produced identical financial metric dictionaries without reacquisition. Reports are locally available in ignored `reports/yahoo-split-smoke.md` and `reports/yahoo-split-repeat.md`.

Earlier VOO/AAPL acquisition `yahoo-smoke-v1` and suite `483fb8df-3ffe-4082-b9e3-fbdefd204b06` also completed. Use the final VOO/NVDA suite above as the validation reference. Dataset manifests and exports record input/configuration hashes, base Git revision and execution implementation hashes so uncommitted development code is distinguishable from the base revision.
