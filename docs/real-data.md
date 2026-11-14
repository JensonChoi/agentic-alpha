# Real historical research (simulation only)

## Acquisition and baseline workflow

Run from `backend/`, after `uv sync`. Local SQLite is initialized by the CLI. PostgreSQL users must first run `uv run alembic upgrade head` (additive revision 002 adds snapshots and suites, without rewriting existing datasets).

```sh
uv run python -m app.cli download --provider yahoo --id yahoo-baselines-v1 \
  --symbols VOO,AAPL,MSFT,NVDA --start 2020-01-02 --end 2024-12-31 --long-window 50
# Keep the existing worker running in a separate terminal:
uv run python -m app.worker
# Queue jobs, wait at most 120 seconds, and report saved results:
uv run python -m app.cli benchmark --config ../configs/examples/real-baselines.json \
  --wait 120 --output ../reports/real-baselines.md
# If the wait expired, use the printed suite ID (no duplicate experiments):
uv run python -m app.cli benchmark --suite SUITE_ID --wait 120 --output ../reports/real-baselines.md
```

Overrides take precedence over JSON settings, then `Config` defaults. Without settings, the demo dataset and April–December 2024 range remain the defaults; real studies should specify their range. Strategies default to `buy_and_hold,momentum`. `benchmark --help` lists allocation, execution, date, universe, owner, window, and dividend overrides. `--no-reinvest-dividends` overrides a true JSON setting. Wait defaults to zero; incomplete/blocked/partial suites exit 2, completed suites exit 0. A timeout leaves jobs intact and prints outstanding IDs. The command never launches a worker. An explicitly requested but unavailable congressional leg remains blocked in the suite and report.

Download dates are inclusive. Acquisition retrieves 51 preceding sessions for a 50-session long window. User boundaries may be holidays/weekends; preflight checks actual sessions. Incomplete sessions are excluded. Interior gaps remain explicit in per-symbol coverage; strict preflight rejects missing required bars. `--missing-price-policy skip` is an explicit partial-coverage research policy. Execution prices are never forward-filled; existing holdings may be marked at their last price. Warmup makes no trades or dividend credits.

The universe is a fixed research selection, with survivorship and selection bias, not historical index membership. Storage may contain additional disclosed stocks, but momentum candidates remain the independently configured universe. Passive VOO targets 100% versus active position caps: these are different risk budgets.

## Yahoo conventions and limitations

The pinned adapter is `yfinance==0.2.66`, an unofficial client. Consult [yfinance](https://github.com/ranaroussi/yfinance), its [history API](https://ranaroussi.github.io/yfinance/reference/yfinance.price_history.html), [price repair notes](https://ranaroussi.github.io/yfinance/advanced/price_repair.html), and [Yahoo adjusted-close explanation](https://help.yahoo.com/kb/SLN28256.html). Source access and redistribution are governed by provider terms; this repository's license grants no market-data rights. No availability guarantee or subscription purchase is implied.

Acquisition requests `auto_adjust=False`, `back_adjust=False`, `repair=False`, `actions=True`, `rounding=False`, `keepna=True`, daily frequency and a 15-second request timeout. The client itself still performs documented parsing/merging; disabling repairs is not a guarantee that Yahoo upstream data are error-free. Only USD US exchange stocks/ETFs with America/New_York sessions are accepted. Capital-gains distributions fail closed.

Yahoo OHLC and distributions are split-adjusted even with automatic dividend adjustment disabled. For each daily row we multiply OHLC and dividends by the product of subsequent split ratios and divide volume by that product. Same-day units are post-split. The full adjustment horizon extends through retrieval day, including splits after benchmark end. The source response hashes and all adjustment events are retained in the manifest. Incomplete horizon coverage, invalid schemas, and conspicuous unadjusted split discontinuities are rejected; no undocumented repair is attempted. Adjusted close is retained solely for inspection, never execution.

New versioned manifests checksum bars, actions, disclosures and metadata. Publication stages a file and atomically links it without replacement, then commits its registration; failed commits remove the new file. A process crash between linking and commit can leave an unregistered file; acquisition refuses that ID and a fresh identifier is required. Legacy datasets remain readable with explicit unverified-convention warnings. Imported prices are labeled operator-supplied/unverified; imports must use raw units with explicit actions. Reacquisition always requires a new ID.

Splits adjust shares, prior marks and exact FIFO lots. Indicators rescale historical closes only for splits effective by that decision. Dividends use pre-opening holdings after same-day splits. Payment dates are unavailable: cash is credited on ex-date as an approximation. Optional reinvestment uses available opening prices with configured fees, slippage, cash/exposure/position checks. Realized P&L uses split-aware FIFO including fees. Exact accounting and applied action IDs persist in checkpoints. Legacy checkpoints without exact FIFO state require a new experiment; existing saved results remain readable.

VOO returns are ledger returns. Adjusted-close returns can differ due to opening entry, fees, slippage, cash dividends, and reinvestment timing; they are not required to match different conventions.

## Congressional benchmarking — deferred

Quiver is no longer part of the research workflow. No Quiver account, subscription, or API key is required. Congressional acquisition and benchmark validation are deferred to a later PR; the current validated workflow uses Yahoo prices for VOO buy-and-hold and momentum. See [the 2026 validation record](real-data-validation.md) for results and the comparison screenshot.

The existing disclosure import and simulation interfaces remain available, but they do not establish a validated real congressional dataset. The Quiver adapter remains in the code for now; it is not used by this workflow. The three-strategy example configuration is prospective, not a completed validation example.

### Requirements for a future local disclosure import

A future congressional benchmark can use an authorized, source-verified normalized local export. It must retain stable transaction identities, member/owner scope, amendment history, and evidence of public availability. Filing dates alone do not establish publication timing. Automated PDF extraction and verification are not implemented.

Once suitable records are available, the existing import interface accepts:

```sh
uv run python -m app.cli import-disclosures ../disclosure-imports/verified.json \
  --id pelosi-verified-v1 --provenance 'Authorized export; publication evidence and historical coverage description'
```

Snapshot metadata is available through `GET /api/disclosure-snapshots`. Any future price acquisition must include every eligible disclosed stock/ETF plus VOO, independently of momentum's configured universe. Strict preflight rejects missing histories by default. Delisted or unresolved securities must not be silently mapped to alternatives.

The export is an array, or `{"metadata":{"warnings":["coverage/revision limitations"]},"records":[...]}`. Each record includes:

- `source_id`: stable transaction identity from source, `revision` (default `1`), optional `amends` pointing to the original transaction. Preserve distinct transactions even with identical dates/amounts.
- `member_id`: stable member ID (`P000197` for Nancy Pelosi); `owner`: `self`, `spouse`, `dependent`, `joint`, or `unknown`. Family examples include all five categories. Never label spouse trades as personally executed by the member.
- `ticker`, `security_type` (`stock`/`etf` eligible), `action` (`BUY`/`SELL`/`UNSUPPORTED`), `transaction_date`, optional `filing_date`, `ingested_at`, `source_url`, original raw record in `original`.
- `availability_quality`: `verified_timestamp` plus timezone-aware `published_at`, or `verified_date` plus `published_date`, and a nonempty `publication_evidence` explaining the source evidence. Otherwise use `unverified`; filing dates alone never qualify. Verification is the importer's assertion with retained evidence, not automated source certification.
- `value_low`, `value_high`, `original_value_range` preserve reported ranges when supplied. Unknown ranges remain zero and cannot drive meaningful proportional allocations. Optional `source_order` establishes ordering of same-open conflicting records.

Only publications within the experiment range drive orders; starting holdings are cash. Timestamped events execute at the first open strictly after publication; date-only events execute at the next session open. Same-open opposing records without source ordering are skipped as ambiguous. Revisions arrive prospectively; a processed transaction never executes again merely because it was amended. Source amendments should reference the original identity, not an intermediate revision. Unsupported assets and unverified availability are explicitly audited. Eligible purchases maintain a set with capped equal targets; sells fully exit that ticker. Fixed/proportional options remain approximations.

Results describe a **Pelosi-family disclosure-following simulation**, never actual family investment performance. Publication delays, approximate sizing, omitted options and unknown starting holdings prevent reconstructing that portfolio. No usable disclosures produces a blocked or partial outcome, not evidence of a zero-return strategy.

## Docker and offline reproduction

```sh
# Existing compose stack runs migrations and one worker; do not start another.
docker compose exec api python -m app.cli download --id yahoo-baselines-v1 \
  --symbols VOO,AAPL,MSFT,NVDA --start 2020-01-02 --end 2024-12-31
# CLI output and data use the shared datasets volume.
docker compose exec api python -m app.cli benchmark --dataset yahoo-baselines-v1 \
  --start 2020-01-02 --end 2024-12-31 --universe VOO,AAPL,MSFT,NVDA \
  --wait 120 --output /data/reports/baselines.md
```

No disclosure-provider credentials are needed for the baseline workflow. Do not commit credentials or downloaded exports. Local `datasets/`, `disclosure-imports/`, caches and `reports/` are ignored. Preserve the database and dataset volume together: snapshots are stored transactionally in the database; bars are stored in the dataset directory. Repeating `benchmark` with frozen IDs/configuration uses no network and produces matching deterministic financial results. `--suite` regenerates a report from existing results without simulation. Reports include configuration/input hashes, code revision, exposure, fees/slippage, return versus a same-suite VOO run, disclosure counts and limitations. A Git revision identifies the base commit; during development uncommitted edits must also be preserved.

Dashboard creation, history, details and comparison expose provider/coverage/price basis/warnings and member/owner scope. Comparison includes suite membership and blocked legs. Detailed exports retain disclosure audits and exact configuration.

## Synthetic Docker CI smoke test

Run `bash scripts/docker-smoke.sh` from the repository root with Docker Compose 2.24 or newer. It builds the backend and frontend, starts PostgreSQL 16 and the normal migration/API/worker services in a unique disposable project, and publishes no host ports. It verifies fresh and legacy migrations, API queueing, worker-completed synthetic VOO/momentum benchmarks, persisted reports, and unchanged results after restarting the API and worker. Provider and inference credentials are disabled; only image/dependency installation needs external network access.

The `Docker smoke` GitHub Actions workflow runs this command on pushes, pull requests, and manual dispatch with a 15-minute job timeout. Logs and the benchmark report are retained as workflow artifacts and locally under ignored `reports/docker-smoke/`. The script removes its own containers and volumes on exit, leaving existing stacks untouched. This is CI validation, not deployment or a real-data performance benchmark.
