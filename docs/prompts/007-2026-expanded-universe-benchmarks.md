# Benchmark the expanded 30-ticker universe in 2026

**Does giving trading agents a larger ticker universe improve simulated trading performance in 2026?**

Test that question by rerunning the price-only Qwen single-agent simulation with 30 tickers. Measure return, maximum drawdown, and average exposure. Use the [original benchmark](../benchmark-report.md#2026) for context and account for the changes in allocation rules when interpreting the results. Run the other models only with separate user authorization.

## Universe

- Keep VOO, QQQ, NVDA, TSLA, AAPL, V, DIS, BE, AMZN, and MSFT.
- Add IBIT (bitcoin), ETHA (ether), IAUM (gold), SLV (silver), CRWV (CoreWeave), NBIS (Nebius), AMD, and BRK.B (Berkshire Hathaway Class B). Use Yahoo Finance’s `BRK-B` symbol consistently for Berkshire prices, actions, and configuration.
- Add JNJ (healthcare), XOM (oil and gas), PG (consumer staples), NEE (utilities), PLD (industrial real estate), LIN (industrial gases and materials), and CAT (heavy machinery).
- Add GOOGL (Alphabet Class A) and TSM (Taiwan Semiconductor’s U.S.-listed ADR).
- Add RKLB (Rocket Lab), PLTR (Palantir), and COIN (Coinbase).

## Runs

| Model | Strategy | Reference configuration |
| --- | --- | --- |
| Qwen 3.5 9B (`qwen3.5:9b`) | Single agent | [30-ticker Qwen single agent](../../configs/benchmarks/2026-expanded-universe-30-tickers/qwen-single.json) |
| Qwen 3.5 9B (`qwen3.5:9b`) | Multi-agent | [2026 Qwen multi-agent](../../configs/benchmarks/price-only-multi-agent/2026-qwen3.5-9b.json) |
| Gemma 4 12B (`gemma4:12b`) | Multi-agent | [2026 Gemma multi-agent](../../configs/benchmarks/price-only-multi-agent/2026-gemma4-12b.json) |
| GPT-5.5 (`gpt-5.5-2026-04-23`) | Single agent | [2026 GPT-5.5 single agent](../../configs/benchmarks/gpt-5-5-single-agent/2026.json) |

Use the same `2026-01-01` to `2026-11-01` configuration bounds as the existing runs, with October 30 as the last trading session. Earlier bars serve only as indicator warm-up. Use `yahoo-expanded-2026-30-v1` as the immutable 30-symbol dataset.

## Allocation policy

- Apply a maximum position weight of **20% of portfolio equity each for VOO and QQQ** because each ETF already spreads its exposure across many underlying companies. Cap all other tickers at **5% each**, including IBIT, ETHA, IAUM, and SLV. Apply these limits from the first decision in every measured run and smoke test.
- Use `max_positions: 20` and keep total exposure capped at 100%. Screen all 30 tickers and keep `max_candidates: 10` for the ranked entry shortlist.
- Add optional per-ticker position-weight overrides to the simulator and use the same effective caps in agent context, proposal validation, and next-open simulated execution. Reject targets above the effective cap and allow reductions or exits when market moves push an existing holding above its cap. Audit market-driven drift separately from purchases. Preserve the existing uniform-cap behavior for configurations without overrides.
- Add deterministic regression tests for the VOO and QQQ overrides, the 5% default, and enforcement at proposal validation and execution. Verify that a holding above its cap can still be reduced or exited.

## Data and execution

- Use the repository’s historical import and preflight checks. Verify that every symbol has all required trading sessions and the 51 preceding sessions for warm-up. Record source, coverage, and corporate actions. Follow the simulator’s raw-price accounting convention and check split normalization against the provider’s adjustment history, including later splits that can affect its historical bars.
- Derive each new configuration from its reference. Keep the existing weekly schedule, initial capital, costs, provider settings, and decision budgets. Use only point-in-time price history, indicators, and portfolio state. Keep shared risk validation and next-open simulated execution.
- Run Qwen single-agent first. If authorized, run Qwen multi-agent and Gemma multi-agent in that order before GPT-5.5. Smoke-test each authorized configuration before its measured run. Check symbol coverage, candidate screening, and context usage, and confirm that each configuration can validate a portfolio decision. Document any protocol changes that affect comparability.
- Run GPT-5.5 single-agent last, including its smoke test. Cap total GPT-5.5 API spend at **$5 USD** across the smoke test, measured run, and all retries. Use the worker’s enforced `api_budget_usd` for each experiment. Before starting another GPT-5.5 experiment, subtract all prior GPT-5.5 API spend and outstanding reservations for this benchmark from the $5 total, and set its cap to at most the remaining balance. Stop paid requests when the remaining budget cannot cover the next request. Report spend, reservations, and any measured weeks left incomplete because of the cap.

## Deliverables

- Save the reproducible 30-ticker Qwen single-agent configuration and record the dataset version, model settings, and experiment IDs.
- Publish only 30-ticker results in [the benchmark report](../benchmark-report-2026-expanded-universe.md). Link to the original report for historical Qwen and VOO buy-and-hold benchmarks.
- Report return, final equity, maximum drawdown, fills, validated decisions out of scheduled decisions, skips, and errors. Include average exposure, peak holdings, orders blocked by the allocation limits, runtime, and reported inference usage. Reconcile performance against daily equity and show whether RKLB, PLTR, and COIN were traded.
