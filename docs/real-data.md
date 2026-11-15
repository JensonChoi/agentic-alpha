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

CLI overrides take precedence over `strategy_settings[STRATEGY]`, then shared JSON settings, then `Config` defaults. The passive VOO policy always retains its 100% position/exposure budget. Without settings, the demo dataset and April–December 2024 range remain the defaults; real studies should specify their range. Strategies default to `buy_and_hold,momentum`. `benchmark --help` lists allocation, execution, date, universe, owner, window, and dividend overrides. `--no-reinvest-dividends` overrides a true JSON setting. Wait defaults to zero; incomplete/blocked/partial suites exit 2, completed suites exit 0. A timeout leaves jobs intact and prints outstanding IDs. The command never launches a worker. An explicitly requested but unavailable congressional leg remains blocked in the suite and report.

Download dates are inclusive. Acquisition retrieves 51 preceding sessions for a 50-session long window. User boundaries may be holidays/weekends; preflight checks actual sessions. Incomplete sessions are excluded. Interior gaps remain explicit in per-symbol coverage; strict preflight rejects missing required bars. `--missing-price-policy skip` is an explicit partial-coverage research policy. Execution prices are never forward-filled; existing holdings may be marked at their last price. Warmup makes no trades or dividend credits.

The universe is a fixed research selection, with survivorship and selection bias, not historical index membership. Storage may contain additional disclosed stocks, but momentum candidates remain the independently configured universe. Passive VOO targets 100% versus active position caps: these are different risk budgets.

## Yahoo conventions and limitations

The pinned adapter is `yfinance==0.2.66`, an unofficial client. Consult [yfinance](https://github.com/ranaroussi/yfinance), its [history API](https://ranaroussi.github.io/yfinance/reference/yfinance.price_history.html), [price repair notes](https://ranaroussi.github.io/yfinance/advanced/price_repair.html), and [Yahoo adjusted-close explanation](https://help.yahoo.com/kb/SLN28256.html). Source access and redistribution are governed by provider terms; this repository's license grants no market-data rights. No availability guarantee or subscription purchase is implied.

Acquisition requests `auto_adjust=False`, `back_adjust=False`, `repair=False`, `actions=True`, `rounding=False`, `keepna=True`, daily frequency and a 15-second request timeout. The client itself still performs documented parsing/merging; disabling repairs is not a guarantee that Yahoo upstream data are error-free. Only USD US exchange stocks/ETFs with America/New_York sessions are accepted. Capital-gains distributions fail closed.

Yahoo OHLC and distributions are split-adjusted even with automatic dividend adjustment disabled. For each daily row we multiply OHLC and dividends by the product of subsequent split ratios and divide volume by that product. Same-day units are post-split. The full adjustment horizon extends through retrieval day, including splits after benchmark end. The source response hashes and all adjustment events are retained in the manifest. Incomplete horizon coverage, invalid schemas, and conspicuous unadjusted split discontinuities are rejected; no undocumented repair is attempted. Adjusted close is retained solely for inspection, never execution.

New versioned manifests checksum bars, actions, disclosures and metadata. Publication stages a file and atomically links it without replacement, then commits its registration; failed commits remove the new file. A process crash between linking and commit can leave an unregistered file; acquisition refuses that ID and a fresh identifier is required. Legacy datasets remain readable with explicit unverified-convention warnings. Imported prices are labeled operator-supplied/unverified; imports must use raw units with explicit actions. Reacquisition always requires a new ID.

Splits adjust shares, prior marks and exact FIFO lots. Indicators rescale historical closes only for splits effective by that decision. Dividends use pre-opening holdings after same-day splits. Payment dates are unavailable: cash is credited on ex-date as an approximation. Optional reinvestment uses available opening prices with configured fees, slippage, cash/exposure/position checks. Realized P&L uses split-aware FIFO including fees. Exact accounting and applied action IDs persist in checkpoints. Legacy checkpoints without exact FIFO state require a new experiment; existing saved results remain readable.

VOO returns are ledger returns. Adjusted-close returns can differ due to opening entry, fees, slippage, cash dividends, and reinvestment timing; they are not required to match different conventions.

## House PDF acquisition and review

House PTR acquisition is available for the evidenced Nancy Pelosi / `P000197` mapping. Quiver, OCR, Senate sources, LLM extraction, and brokerage execution are outside this workflow. [House source semantics and validation](house-pdf-validation.md) document the inspected official formats and remaining limitations.

```sh
uv run python -m app.cli download-house --id house-pelosi-2026-v2 \
  --member-id P000197 --start 2026-01-01 --end 2026-11-01 \
  --artifact-dir ../house-artifacts --provenance 'Official House; local noncommercial research'
uv run python -m app.cli download --id yahoo-house-2026-v1 \
  --symbols VOO,QQQ,NVDA,TSLA,AAPL,AMZN,BE,DIS,INTC,PYPL \
  --start 2026-01-01 --end 2026-11-01 --long-window 50
uv run python -m app.cli benchmark --config ../configs/examples/pelosi-family-2026.json \
  --wait 30 --output ../reports/pelosi-family-2026-v2.md
```

Use fresh IDs on subsequent acquisitions. The example records the validated IDs, not a promise those IDs exist on a new installation. The price union above includes explicitly parsed stock purchases/sales, even when availability remains unverified. Quarantined securities are unresolved; therefore this is not a claim of exhaustive required price coverage. Momentum stays restricted to VOO, QQQ, NVDA, TSLA, AAPL. Congressional selection is event-driven: active purchase candidates are sorted alphabetically, the first five receive capped equal targets, and excluded candidates are audited on each event. Eligible sales fully exit, including source partial sales. Cash remains unallocated when caps prevent full investment.

Acquisition reads every current member PTR in each requested calendar-year index, including post-end filings for audit. Date scope does not filter on transaction or filing dates as a substitute for publication dates. Index observations cannot prove historical completeness, prior revisions, or availability. All extracted records start unverified. Unrecognized layouts, scanned pages, uncertain fields and amendment links are quarantined. Strict congressional preflight blocks unresolved House quarantines/publication evidence; explicit `--missing-price-policy skip` allows only a labeled partial run when at least one usable event exists. No usable events always block.

The parser uses header geometry, wrapped descriptions, separate note rows and recognized note continuations after repeated headers. It preserves original text, column strings, page/table/row/bounding-box locators, PDF hash and parser version. Source tickers are used only when explicit; no company-name inference or modern-symbol substitutions occur. Options, exercises, gifts/contributions, exchanges, mergers and private assets cannot become ordinary stock trades. A malformed amount remains quarantined even for an unsupported exchange. General handwritten forms and fragmented transaction rows require review.

Bounds: 20 MiB per source, ten index years, 500 PDFs, 100 pages per PDF, three transient-request attempts, 1–60 second request timeout, 0.1–10 second inter-request interval (defaults 20/1), bounded `Retry-After`, 45 seconds per parser subprocess and 30 CPU seconds. Linux subprocesses also limit address space to 2 GiB; macOS does not support that limit reliably. ZIP contents are read in memory with path/duplicate/expansion checks; XML entity expansion is disabled. Redirects, access denial and CAPTCHAs are not bypassed.

An acquisition reserves a new artifact directory before staging. Missing indexes/documents, network errors or identifier collisions never register a snapshot. Failed directories and discovery journals remain for inspection; choose a new ID to retry. Source URLs, retrieval observations, index rows, PDFs, extraction JSON and the review export are preserved. Parser quarantines can register only with explicit partial/unknown quality. Version-2 manifests hash every registered artifact and the normalized records; `load_snapshot` checks both offline. Keep the database and artifacts together at their recorded absolute paths (or restore the same mount in a container). Legacy snapshots remain readable without retroactive certification. No database migration or ledger-accounting change is needed.

### Offline official-PDF import

`import-house bundle.json` takes the same ID, member, dates, artifact-directory and provenance flags. The bundle lists local source paths (resolved from the command's working directory), official source URLs and index years:

```json
{
  "indexes": [{"path": "/local/2026FD.zip", "year": 2026,
    "source_url": "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/2026FD.zip"}],
  "documents": [{"path": "/local/20033725.pdf", "year": 2026, "document_id": "20033725",
    "source_url": "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2026/20033725.pdf"}]
}
```

The example is illustrative: supply **every** selected member PTR in the provided index, not just the first PDF. Local imports still label discovery partial; operator-supplied files do not establish exhaustive historical coverage. Byte identity changes for an already observed document quarantine its rows instead of trusting reordered row positions. Repeated identical source documents preserve identities, while economically identical rows in different source locations remain distinct.

### Evidence-backed corrections

Inspect `house-artifacts/SNAPSHOT/review.json` and each extraction JSON against the original PDF. Run `correct-disclosures corrections.json --source OLD --id NEW --provenance 'Review scope and limitations'`. The corrections file is an array:

```json
[{
  "source_id": "house:DOCUMENT:p1:t1:r1",
  "reviewer": "Named reviewer",
  "evidence": "Source URL, page, field and reason for correction",
  "changes": {"owner": "spouse"}
}]
```

Corrections cannot replace the source locator or original extraction. A corrected quarantine needs a complete valid normalized record in `changes`; unknown document/page-level quarantines require a new import, not guessed rows. Every corrected record embeds its previous version, parent snapshot, reviewer and evidence. Amendments additionally require `amends` naming a known root transaction and `amendment_evidence`; ambiguous mappings remain excluded. The existing simulator applies amendments prospectively without replaying copied identities.

Availability corrections require `publication_basis: "documented_publication"`, source semantics/evidence in `publication_evidence`, and either timezone-aware `published_at` or `published_date`. This is an auditable reviewer assertion, not automatic certification. Filing, signature, notification, PDF metadata, HTTP Last-Modified and present retrieval do not establish historical publication. `synthetic_fixture` is reserved for visibly synthetic automated tests; it is never used for the real benchmark.

### Normalized local imports

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

Run `bash scripts/docker-smoke.sh` from the repository root with Docker Compose 2.24 or newer. It builds the backend and frontend, starts PostgreSQL 16 and the normal migration/API/worker services in a unique disposable project, and publishes no host ports. It verifies fresh and legacy migrations, API queueing, synthetic PDF/index ingestion and evidence review, worker-completed VOO/momentum/congressional benchmarks, persisted reports, artifact integrity and offline financial reproduction after restarting the API and worker. Provider and inference credentials are disabled; only image/dependency installation needs external network access.

The `Docker smoke` GitHub Actions workflow runs this command on pushes, pull requests, and manual dispatch with a 15-minute job timeout. Logs and the benchmark report are retained as workflow artifacts and locally under ignored `reports/docker-smoke/`. The script removes its own containers and volumes on exit, leaving existing stacks untouched. This is CI validation, not deployment or a real-data performance benchmark.
