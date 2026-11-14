# Real-Data Baseline and Congressional Copy Benchmarks

## Objective

Extend Agentic Alpha so a user can acquire real historical daily market data from Yahoo Finance, save a reproducible local dataset, and benchmark VOO buy-and-hold, deterministic momentum, and a Pelosi-family disclosure-following strategy through the existing simulator and dashboard.

Implement working code, tests, and documentation. Preserve the existing synthetic demonstration and CSV/Parquet imports. All execution must remain simulation-only; never add brokerage connections or real-money modes.

Read `AGENTS.md`, `README.md`, and the relevant requirements in `docs/prompts/001-mvp.md` before implementation.

## Current Implementation

- `backend/app/data.py` validates and registers immutable Parquet datasets, stores manifests, and generates synthetic demo data. Its manifest currently labels all imported prices as raw without establishing their actual adjustment basis.
- `backend/app/engine.py` handles strategies, corporate actions, next-session fills, checkpoints, and metrics. Inspect its existing split/dividend handling before trusting real-data results.
- `backend/app/cli.py` supports imports and a benchmark command, but the benchmark hardcodes default dates/universe, runs congressional copying regardless of available disclosures, and includes synthetic-only report language.
- The dashboard selects registered datasets and displays persisted experiments. CLI benchmark results currently bypass experiment persistence.

Reuse these components; avoid a second execution engine or unrelated architectural rewrites.

## Scope

Implement Yahoo ingestion through `yfinance` as the initial provider, behind a small typed provider interface. Keep provider acquisition separate from validation, normalization, persistence, and execution so another authorized provider can be added later.

Include VOO buy-and-hold, momentum, and a narrowly scoped congressional extension using one structured source. Use Quiver as the initial congressional API target, subject to verification of its current schema, historical coverage, credentials, and permitted use; also support an authorized local export of the same normalized records. Direct House/Senate PDF scraping, OCR, additional congressional providers, LLM enhancements, intraday trading, and automated forward feeds are out of scope.

### 1. Data Acquisition

- Add a CLI download command accepting provider, immutable dataset ID, symbols, and inclusive benchmark start/end dates. Translate provider-specific exclusive end dates explicitly.
- Retrieve daily OHLCV, dividends, and splits. Specify adjustment and repair options explicitly; pin the dependency through the existing package/lock workflow.
- Fetch at least `long_window + 1` completed trading sessions before the benchmark start for momentum warmup. Record the requested benchmark range separately from acquired coverage. Warmup must not create trades, equity returns, or dividend entitlements before the experiment starts.
- Bound network timeouts and retries; report invalid symbols, empty responses, rate limits, partial downloads, and insufficient coverage clearly. Do not silently drop requested symbols, fabricate bars, substitute synthetic data, or overwrite an existing dataset.
- Normalize daily dates using the exchange session timezone. Exclude incomplete sessions and validate duplicate rows, OHLC ranges, finite positive prices, volume, and corporate actions.
- Record per-symbol coverage and missing sessions. Fail acquisition for unusable symbols; preserve explicit gaps in otherwise usable histories and never forward-fill execution prices.
- Make publication of the dataset atomic enough that failed downloads or registrations leave no usable partial dataset.

### 2. Price Basis and Corporate Actions — Correctness First

Do not assume `auto_adjust=False` means historically unadjusted prices. Verify the installed provider's treatment of OHLCV, dividends, splits, and adjusted close using current primary documentation and captured examples. Yahoo data can already incorporate split adjustments.

- Normalize to the existing ledger's raw-price plus explicit-corporate-action convention. If reconstructing raw prices, retrieve all adjustment events needed for the provider's adjustment horizon, including splits after the benchmark end. Document and test the transformations for prices, share units, dividends, and volume. Reject unsupported or ambiguous conventions rather than labeling them raw.
- Keep adjusted close as optional validation data, never as an execution price combined with separate dividend credits.
- Test a held position across splits and reverse splits: quantity changes, market value stays economically consistent, and fees/cash/cost basis remain correct. Apply each action once, including after restart.
- Use split-consistent indicator history available at each decision timestamp so mechanical split price changes do not generate false momentum crossovers. Do not use future events to alter historical signals.
- Define dividend entitlement using holdings before the ex-date opening trades. Do not pay dividends on shares first bought on the ex-date.
- When payment dates are unavailable, use an explicitly labeled ex-date cash-credit approximation. Reinvestment must follow a documented executable-price convention, credit each distribution once, and respect the configured fee/slippage treatment. Never imply exact real-world payment timing.
- Fix split-aware cost basis and realized P&L, or return unavailable metrics with explicit reasons rather than inaccurate values.
- Verify VOO total returns against an independent calculation under the same accounting and reinvestment assumptions. Explain differences from provider adjusted-close returns due to timing, costs, and reinvestment conventions; do not demand equality between different conventions.

### 3. Reproducible Storage and Provenance

Extend dataset manifests with provider, retrieval timestamp, provider/library version, requested symbols/range, actual coverage, warmup coverage, original and normalized adjustment conventions, action timing assumptions, and quality warnings.

Hash normalized bars, corporate-action metadata, and versioned disclosure records, including their publication and amendment metadata. Store any supporting downloaded artifacts locally when permitted. Freeze dataset versions so reruns do not re-download or mutate prior results. A fresh acquisition requires a new identifier.

Keep downloaded market data, disclosure records, caches, credentials, and generated reports out of Git by default. Commit code, configuration examples, and small clearly synthetic test fixtures. Public availability and the project's MIT license do not grant redistribution rights to provider data. Document Yahoo/yfinance's unofficial status and applicable usage terms without promising unrestricted or guaranteed access.

### 4. Congressional Disclosure Acquisition

Implement one typed structured-source adapter and a CLI acquisition command. Verify the source's current official documentation before coding; do not assume free historical API access or that every field is suitable for point-in-time research. Preserve source identifiers, source-document links when supplied, retrieval time, and the original record alongside normalized data where permitted.

- Acquire records for a configurable tracked member, initially Nancy Pelosi, including disclosed spouse/family activity. Use stable member identifiers rather than substring name matching. Preserve owner classification (self, spouse, dependent, joint, unknown); do not attribute all transactions personally to Nancy Pelosi. Unknown ownership must remain visibly unknown.
- Add tracked-member and owner filtering to experiment configuration and apply it before signal generation. Make the dashboard and reports display the selected member and owner scope.
- Normalize transaction date, filing date, source publication timestamp/date, ingestion timestamp, effective availability, purchase/sale direction, asset identifier/ticker, security type, original value range, and amendment relationships. Do not collapse these distinct timestamps into one disclosure date.
- Define an availability-quality field distinguishing verified publication timestamps, verified publication dates, and unverified availability. A filing date is not proof of public availability. Date-only verified publication uses the next exchange session's open. Timestamped publication uses the first eligible open strictly after publication, including premarket publications. Adapt event ordering if necessary; a close-only evaluator must not introduce an unexplained extra session of delay.
- Exclude records with unverified availability from the default realistic benchmark and record why. Do not invent a publication timestamp or silently treat filing/transaction dates as publication. If the chosen API lacks sufficient availability evidence, accept a source-verified local export; otherwise report the congressional benchmark as blocked while completing the price-only benchmarks. Any separately supported assumed-delay experiment must be explicitly non-comparable and opt-in.
- Bound timeouts, retries, and pagination. Fail clearly on missing credentials, denied historical access, incomplete pagination, or invalid schemas. Never substitute synthetic disclosures for an unavailable real source.
- Store immutable disclosure snapshots with coverage, source terms/limitations, member/owner filters, and checksums. Disclose when historical coverage is not established by the provider.
- Deduplicate by stable source transaction identity and revision, not simply ticker/date/value. Preserve legitimate multiple transactions. Retain amendment history and introduce revisions only when they become publicly available; never rewrite historical decisions using today's corrected record. Previously copied transactions must not execute again solely because an amendment arrives. Record corrections and any resulting skips explicitly. If historical revisions cannot be established, flag the limitation rather than claiming a revision-complete dataset.

### 5. Congressional Strategy and Market-Data Alignment

Use stock and ETF disclosures only. Explicitly skip options, exercises that cannot be unambiguously represented, private assets, unsupported transaction types, and unresolved tickers; never convert an option into a stock trade. Preserve skip reasons and source references in results.

Default to capped equal target weights across currently tracked eligible purchases, with unused allocation in simulated cash. Maintain the eligible set through time, close a tracked position on a corresponding sell disclosure, and disclose that this is a deterministic full-exit approximation. Resolve same-event conflicts by recorded source ordering when available; otherwise skip conflicting ticker proposals with an ambiguity warning. Preserve existing fixed/proportional configurations without expanding their scope in this task.

- Start with cash and process disclosures first available within the experiment range. Do not replay all pre-start disclosures as new purchases or infer the family's starting portfolio.
- Feed proposals through the same risk checks, fees, slippage, and ledger as other strategies. Record rejected proposals and missing execution prices.
- Acquire matching market histories for eligible disclosed securities plus VOO. Preserve ticker mapping evidence and identify unavailable/delisted coverage; no invented prices or silent symbol substitutions. Required missing histories should fail preflight by default; an explicit skip-incomplete policy may run a clearly labeled partial-coverage experiment.
- Do not silently expand momentum's candidate universe using trades disclosed later in the experiment. Keep its fixed universe independently configured. A storage dataset may contain the union of required symbols, but each strategy sees only its configured candidates and point-in-time eligible disclosures.
- Report eligible, skipped, ambiguous, amended, and unmatched records and the number of filled trades. An empty eligible set must be identified as no usable disclosures, not represented as evidence that copying trades earned a zero return.
- Describe results as a Pelosi-family disclosure-following simulation, never Pelosi's actual investment performance. Publication delays, approximate position sizing, omitted options, and unknown starting holdings prevent reconstructing her family's actual portfolio.

### 6. Benchmark Workflow

Extend the CLI with configurable dataset, strategy selection, start/end dates, universe, initial capital, momentum windows, rebalance frequency, allocation limits, fees, slippage, dividend policy, disclosure snapshot ID, tracked member/owner scope, and report output. A checked-in configuration file may supply these settings; document precedence if both file and CLI overrides are supported.

- Default the real-data suite to `buy_and_hold,momentum`; require VOO in the acquired dataset. Provide an explicit three-strategy configuration using `buy_and_hold,momentum,congressional` when a verified disclosure snapshot is supplied. Do not run congressional copying without usable disclosures; report that leg as blocked rather than silently removing it.
- Use the same persisted experiment/job workflow as the API so runs appear in Experiment History and Comparison. Avoid duplicated simulation logic and do not start a competing worker implicitly.
- Provide a bounded wait/report workflow with explicit queued/running/failed/partial outcomes. An unsuccessful suite must not appear as a completed benchmark.
- Align dates, initial capital, dataset version, transaction assumptions, and dividend policy across strategies. Show the passive 100% VOO profile versus active strategy allocation limits, universe, and cash exposure as differences; do not call these identical risk budgets.
- Make report text derive from actual configuration and provenance. Include experiment IDs, dataset hashes, performance/risk metrics, fees, exposure, excess total return versus matched VOO, and warnings or failures. Label missing metrics explicitly.
- Record code revision when available and version execution assumptions. Repeating a deterministic run against the same frozen inputs must produce the same financial results.

Suggested user workflow (implement these commands or document equivalent final syntax):

```sh
cd backend
uv run python -m app.cli download --provider yahoo --id yahoo-baselines-v1 \
  --symbols VOO,AAPL,MSFT,NVDA --start 2020-01-02 --end 2024-12-31 \
  --long-window 50
uv run python -m app.cli benchmark --dataset yahoo-baselines-v1 \
  --strategies buy_and_hold,momentum --start 2020-01-02 --end 2024-12-31 \
  --universe VOO,AAPL,MSFT,NVDA --output ../reports/real-baselines.md
```

This example is a fixed-universe study, not an unbiased historical stock-selection benchmark. Explicitly disclose survivorship and selection bias; do not claim delisted-symbol or point-in-time index-membership coverage.

### 7. Dashboard and Documentation

- Add a documented congressional acquisition → price acquisition → three-strategy benchmark example using the selected source and normalized export fallback. Explain credentials, historical-access limits, member/owner selection, availability quality, and skip counts.
- Display imported real datasets distinctly from synthetic demo datasets, including provider, coverage, adjustment convention, and warnings.
- Allow existing experiment creation/comparison flows to use the downloaded dataset; show benchmark runs persisted by the CLI.
- Validate date ranges and symbol coverage before execution, accounting for non-trading boundary dates and warmup requirements.
- Update the README, data documentation, and example configs with acquisition, benchmark, offline rerun, provider limitations, and Docker-volume commands.
- Preserve simulation labels. Do not introduce claims of profitability or statistical significance.

## Tests and Acceptance Criteria

Use mocked provider responses and deterministic fixtures for automated tests; no network access, subscription, or LLM should be required.

Cover:

1. Single/multiple symbols, response column shapes, timezone conversion, inclusive date handling, and warmup history.
2. Empty/partial responses, rate limiting, bounded retries, invalid OHLCV, missing sessions, and immutable-ID collisions.
3. Split-adjusted source normalization, post-range splits, reverse splits, dividends, entitlement timing, and no double-counting.
4. Split-consistent crossover signals, no same-bar fills, no future-data access, and no trades during warmup.
5. Portfolio identity, cost basis, independent VOO return reconciliation, and restart/action idempotency.
6. Persistent benchmark experiments, correct strategy selection, aligned assumptions, truthful reports, failure reporting, and repeatable results.
7. Tracked-member/owner filtering, preservation of unknown ownership, publication versus filing dates, premarket/after-close/weekend publication timing, and exclusion of unverified availability.
8. Disclosure pagination/authentication failures, repeat acquisition, distinct same-day transactions, amendment timing, unsupported assets, ambiguous orders, missing prices, and empty eligible sets.
9. Three-strategy persistence and reports, separate candidate universes without future-disclosure leakage, reproducible disclosure hashes, and visible partial/blocked congressional outcomes.
10. API/UI dataset selection and provenance display; run the frontend production build and document browser checks separately.

Run the backend suite and relevant integration checks. If network access and provider terms permit, perform a small real-data smoke acquisition and two baseline runs; additionally run the congressional leg when an authorized source with verified availability is accessible. Inspect the resulting trades and comparison, and report the exact dataset/configuration used. If external access is unavailable, report that limitation explicitly while completing offline implementation and tests. Do not present mocked results as validated Yahoo or congressional-source results. Missing external access is a verification limitation, not permission to claim the congressional integration was validated end to end.

Completion means a user can acquire authorized real data, run both deterministic baselines and the disclosure-following strategy when verified records are supplied, inspect persisted results in the dashboard, generate an accurate report, and reproduce the results offline without introducing accounting errors or real-money execution.

Useful references to verify during implementation:

- https://github.com/ranaroussi/yfinance
- https://ranaroussi.github.io/yfinance/reference/yfinance.price_history.html
- https://help.yahoo.com/kb/SLN28256.html
- https://www.quiverquant.com/api-setup/
- https://api.quiverquant.com/
- https://disclosures-clerk.house.gov/FinancialDisclosure
- https://www.senate.gov/legislative/Public_Disclosure/financial-disclosure.htm
