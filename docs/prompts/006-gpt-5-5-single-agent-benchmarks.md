# Benchmark GPT-5.5 as a price-only single agent

Start a feature branch from current main. Run the pinned OpenAI API snapshot `gpt-5.5-2026-04-23` as one portfolio decision-maker. The research question is whether it improves on Qwen and Gemma single-agent under the same trading rules, and at what API cost. Deliver three measured runs and update the existing [benchmark report](../benchmark-report.md) in place.

We chose GPT-5.5 because its documented knowledge cutoff is December 1, 2025. Every market outcome in the 2026 window falls after that cutoff. At each decision, the simulator supplies only the price history and portfolio state available by that date. [OpenAI model documentation](https://developers.openai.com/api/docs/models/gpt-5.5)

## Match the local benchmark

- Derive each configuration from the corresponding ten-ticker single-agent experiment identified in the report. Use its dataset version, warm-up, decision dates, screening, prompt, evidence, and tool and retry budgets. Retain price-only inputs and simulator-provided tools. Disable web search and external market data.
- Start each measured window with a fresh $100,000 cash portfolio. Preserve weekly decisions, ten positions, the 20% position cap, 100% exposure cap, costs, dividends, cash interest, point-in-time marks, shared risk validation and next-open simulated fills.
- Use backend-only cloud credentials and the exact snapshot. Check the existing OpenAI adapter against the [model documentation](https://developers.openai.com/api/docs/models/gpt-5.5). Make the minimum changes needed for supported token limits, response format and usage reporting. Start with reasoning effort `none` to match the local benchmarks’ disabled thinking setting. Record the effective settings and any provider differences, including unsupported sampling or seed controls. Keep server-side validation authoritative and run backend tests with mocked inference before paid runs.

## Execute in order

| Stage | Historical window | Dataset | Completion check |
|---|---|---|---|
| 1. Smoke | January 1–20, 2026 | `yahoo-house-2026-initial-v1` | Inspect the three scheduled decisions, API usage, latency and estimated cost. Require at least one validated decision. A hold qualifies. |
| 2. 2026 | January 1–November 1 configuration bounds, last session October 30 | Same as smoke | Audit all 43 scheduled decisions. |
| 3. 2025 | January 1–December 31 | `yahoo-llm-2024-2025-10-tickers-v1` | Audit all 52 scheduled decisions. |
| 4. 2024 | January 1–December 31 | Same as 2025 | Audit all 52 scheduled decisions. |

Run one experiment at a time. Diagnose repeated provider, schema or truncation failures during smoke before starting the annual runs. Use smoke token counts and current published API prices to estimate campaign cost. Freeze the protocol after smoke. If a change affects decisions, repeat affected measured windows. Resume from persisted checkpoints after interruption. Preserve completed-with-warnings outcomes and all rejected or skipped weeks in the denominator.

## Verify and publish

- Save reproducible configurations, snapshot ID and final experiment IDs. Reuse the existing benchmark audit to reconcile ending equity, return and maximum drawdown from daily equity and check cash and exposure after each fill. Verify rejected decisions produced no orders. Record validated weeks, skips, errors, calls including retries, reported token usage, latency and estimated API spend. Identify pricing assumptions and missing usage explicitly.
- Add one **GPT-5.5 single-agent** row directly to each existing yearly table and regenerate each chart from daily equity. Update the report and chart generators to retain all nine series with matching legends. Keep smoke out of the performance tables and preserve the existing local single- versus multi-agent comparisons.
- Compare GPT-5.5 with both local single agents on return, drawdown and decision reliability. Report API cost for each year. Discuss the December 1, 2025 documented knowledge cutoff and the April 23, 2026 snapshot date. The 2024 and most of the 2025 decisions fall within the knowledge window. The 2026 data follows the cutoff, but the January–April decisions before snapshot release are retrospective. Limit conclusions to these simulated runs on the fixed universe.
