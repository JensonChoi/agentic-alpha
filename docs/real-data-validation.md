# Validation record — November 14, 2026

All results are simulations. No provider data or credentials are checked into Git.

- Backend: 53 deterministic tests passed, covering acquisition normalization, identity and evidence validation, timing, split FIFO/accounting restart, dividend entitlement and independent reinvestment reconciliation, migration from the original schema, three-strategy persistence, blocked legs, and offline repeatability.
- Frontend: production TypeScript/Vite build passed. Vite reports its existing large-chunk advisory; dependency deprecation warnings remain in Python tests.
- Browser: verified the 2026 comparison chart, dataset labels, and metrics in native Chrome; the revised screenshot could not be captured because macOS ScreenCaptureKit failed (errors -3811/-3812). The image below is retained from the earlier two-symbol run and does not depict these revised results. Comparison URLs now support repeated `experiment` parameters for reproducible selections.
- Quiver: no `QUIVER_API_KEY` in the process. Auth/pagination/schema behavior was tested with HTTP mocks, and normalized imports exercised all three strategies with synthetic fixtures. No real Quiver end-to-end or real congressional performance claim is made.
- PostgreSQL 16/Docker smoke passed locally: fresh migration, legacy revision `001` → `002` upgrade and repeat with metadata preserved, frontend/API proxy readiness, API-created queued experiment, CLI two-strategy suite completed by the real worker, persisted report, and unchanged results after API/worker restart. All smoke inputs are synthetic. The same checks run in the `Docker smoke` GitHub Actions workflow; logs and report are uploaded as artifacts.

## 2026 benchmark: January 1 through November 1

Requested range: **2026-01-01 through 2026-11-01 inclusive**. Actual exchange sessions: January 2 through October 30 (holiday/weekend boundaries). Dataset `yahoo-2026-expanded-v1` contains VOO, QQQ, NVDA, TSLA, and AAPL, with 51 preceding warmup sessions starting October 20, 2025. Normalized content hash: `33955d34a00c8a508d87fd79a3719623620f7bd0843a9aafed9a641c452a707c`.

```sh
uv run python -m app.cli download --id yahoo-2026-expanded-v1 --symbols VOO,QQQ,NVDA,TSLA,AAPL \
  --start 2026-01-01 --end 2026-11-01 --long-window 50
uv run python -m app.cli benchmark --dataset yahoo-2026-expanded-v1 --universe VOO,QQQ,NVDA,TSLA,AAPL \
  --start 2026-01-01 --end 2026-11-01 \
  --strategies buy_and_hold,momentum --short-window 20 --long-window 50 \
  --rebalance weekly --max-position-weight 0.2 --max-positions 5 --wait 30 \
  --output ../reports/2026-expanded-benchmark.md
```

Suite `15c581b6-626e-4bd8-b95b-d79e76baa2bb` was processed through the existing worker:

| Strategy | Status | Total return | Average exposure | Fills |
|---|---|---:|---:|---:|
| VOO buy-and-hold | Completed | 11.0169% | 99.6538% | 1 |
| Momentum | Completed | -0.1290% | 63.4590% | 146 |

Congressional benchmark execution is **deferred to a later PR**. This revised suite requested only the two price-only baselines, and both completed. No Quiver key or registered disclosure snapshots were available. No synthetic disclosures were substituted. A credential alone is insufficient without verified publication evidence and stable transaction identities; an authorized normalized local export can supply these.

Experiment IDs: VOO `70848ba6-b82b-4902-891d-cfb89e227753`; momentum `fb9611d1-5908-497a-9532-028ce7036e54`. Initial capital 100,000; zero fees; adverse slippage 5 bps; cash dividends using the ex-date approximation; 20/50 momentum windows; weekly rebalance; 20% active position cap versus 100% passive VOO. Momentum can hold up to five positions, with maximum total exposure of 100%; full allocation is not required, and unallocated capital stays in cash. Different exposure budgets and a selected fixed universe prevent interpreting this as a controlled claim of superiority.

The full persisted report is in ignored `reports/2026-expanded-benchmark.md`. Earlier 2024 validation suites remain in the local database but are superseded by this date-range run. The earlier 2024 offline-repeat check is historical validation, not a claim that the 2026 suite was rerun.

Acquisition exposed a calendar-boundary bug when the warmup search began on a weekend. The calendar initialization now includes an extra ten-day buffer before that search boundary.

## Comparison screenshot

The comparison link selects the two completed experiments; congressional remains deferred and has no performance curve:

`/compare?experiment=70848ba6-b82b-4902-891d-cfb89e227753&experiment=fb9611d1-5908-497a-9532-028ce7036e54`

![Earlier two-symbol comparison — superseded](images/comparison-2026.png)

**Historical screenshot only:** this image shows the earlier VOO/NVDA run with a 10% cap. The historical image is retained by agreement; it does not represent the revised five-symbol results. Green: VOO; blue: momentum. Congressional is deferred and therefore has no plotted return. Dataset labels include warmup coverage; portfolio returns start in January 2026.
