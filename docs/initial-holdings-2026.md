# 2026 benchmark with inferred starting holdings

**Simulation only. Publication assumed on filing date; historical availability remains unverified.**

Period: **2026-01-01 through 2026-11-01**, inclusive. All three strategies completed through the existing worker. Each starts with $100,000; fees are zero, slippage is 5 bps, and cash dividends use the existing ex-date approximation.

| Strategy | Return | Final equity | Average exposure | Maximum drawdown | Fills |
|---|---:|---:|---:|---:|---:|
| buy_and_hold | 11.0169% | $111,016.89 | 99.6538% | -8.8945% | 1 |
| momentum | -0.1290% | $99,871.00 | 63.4590% | -8.6616% | 146 |
| congressional | -0.5744% | $99,425.56 | 51.6544% | -16.0621% | 12 |

## Starting portfolio assumption

The separate immutable `house-pelosi-pre2026-v1` snapshot contains eight official 2024–2025 PTR PDFs, 22 normalized rows, 15 unsupported entries and zero quarantines. Only disclosures available under the filing-date assumption from **2024-01-01 through 2025-12-31** enter initialization. No 2026 transaction or sale selects starting holdings.

Eligible stock/ETF purchases establish candidates. Explicit `S (partial)` sales imply an unknown residual holding, even if its purchase predates the lookback. Other eligible sales remove candidates. Conflicts block initialization; amendments cannot replay processed transactions. Options, exercises, contributions, and unsupported asset types remain excluded. Partial-sale handling applies to this inference step; sales during the 2026 simulation retain the existing full-exit approximation.

The inferred candidates are **AAPL, MSFT, NVDA, and V**, targeting **20% each**, with approximately 20% cash. Equal targets ignore unknown actual share counts and disclosure amount ranges. The first January 2 open establishes these positions through the shared risk checks and ledger, with normal slippage; there are no pre-period returns or inherited cost bases. Additional candidates would use the existing alphabetical five-position cap.

| Candidate | Pre-start evidence |
|---|---|
| AAPL | Partial sale, filed January 17, 2025; document 20026590, page 1 |
| MSFT | Partial sale, filed July 30, 2024; document 20025535, page 1 |
| NVDA | 2024 purchases and partial sale filed January 17, 2025; documents 20025368, 20025535, 20026590 |
| V | Partial sale, filed July 2, 2024; document 20025368, page 1 |

This is a bounded-lookback hypothetical portfolio, not a reconstruction of the family’s actual holdings. Unobserved older holdings, omitted options, later dispositions not represented by supported records, and historical revisions remain unknown. Current archive retrieval does not establish historical publication evidence.

## Comparison and verification

Congressional return changes from **−4.0534%** in the preserved cash-start study to **−0.5744%**, a **3.4790 percentage-point** increase. Average exposure rises from 10.4757% to 51.6544%. VOO and momentum financial results are unchanged. Different exposure budgets prevent interpreting the return difference as evidence of strategy superiority.

The new immutable price snapshot `yahoo-house-2026-initial-v1` adds MSFT and V to the original union. Momentum remains restricted to VOO, QQQ, NVDA, TSLA, AAPL. It retains 51 preceding warmup sessions. Overlapping raw OHLC and volume match the prior snapshot; 229 inspection-only adjusted-close values differ by at most 0.0001220703125 and are never used for execution.

All three results reproduce exactly offline for metrics, fills, and every equity point. **93 backend tests** and the frontend production build passed, including new cutoff, partial-sale, cap, amendment, missing-price, conflict, and checkpoint-recovery tests. No schema migration or ledger arithmetic change. Existing dependency and bundle-size warnings remain.

## Reproduction and saved evidence

Suite: `e7305757-59e8-4e67-8288-3609c2ab5cf1`. Config: [pelosi-family-2026-initial-holdings.json](../configs/examples/pelosi-family-2026-initial-holdings.json). Full local report: `reports/pelosi-family-2026-initial-holdings-v1.md`. Offline verification: `reports/pelosi-family-2026-initial-verification.json`. Both snapshots and source artifacts remain immutable and outside Git. Execution provenance records input hashes and the uncommitted implementation hash.

- buy_and_hold: `65797fbc-61b8-483c-a57b-92edea180268`
- momentum: `40cb76d0-df45-4558-987c-78f70b9665fd`
- congressional: `df91104c-178b-4cef-80f3-a9e9eced161b`

[Open the updated local comparison](http://127.0.0.1:5173/compare?suite=e7305757-59e8-4e67-8288-3609c2ab5cf1&experiment=65797fbc-61b8-483c-a57b-92edea180268&experiment=40cb76d0-df45-4558-987c-78f70b9665fd&experiment=df91104c-178b-4cef-80f3-a9e9eced161b). The screenshot in the prior [cash-start validation](house-pdf-validation.md) is historical and does not show this run.

No further 2025 simulation was performed for this update. The benchmark was executed before commit; its implementation hash identifies the execution code.
