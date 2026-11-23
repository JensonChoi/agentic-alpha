# Implement and benchmark price-only multi-agent trading

Start a feature branch from current main. Build on the multi-agent strategy delivered by [prompt 004](004-llm-strategies.md). The research question is whether analyst review and portfolio synthesis improve on the same model trading as a single agent. Deliver the protocol fix, run both local models on the three historical windows, and publish the measured results in [the benchmark report](../benchmark-report.md).

## Reproduce the failure

The January 1–20, 2026 Qwen smoke experiment (`b1a7d2cc-daeb-4ca6-9824-9a90796a4fcd`) made 15 model calls across three weekly decisions. Each week the technical analyst requested tools and submitted a recommendation in the same response (`mixed_tools_and_output`). On January 16 the risk analyst also returned the wrong output type. Portfolio synthesis never ran. All $182.34 of portfolio growth came from cash interest. Use this run as a protocol regression case.

## Implement the role contracts

- Start in `backend/app/inference.py`. The price-only generation schema and allowed-reference instructions currently apply only to the single agent. Extend the working constraints to multi-agent inference and keep server-side validation authoritative.
- Give each role two mutually exclusive responses when tools are available. An analyst may request a permitted tool or submit its own typed recommendation. The portfolio agent may request a permitted tool or submit final signals. Once the available tool budget is spent, expose only the completion response. Keep total calls, retries and tool rounds bounded and reserve a call for synthesis.
- Give the technical and risk analysts the price and portfolio evidence their roles need. On these datasets the fundamental/news analyst must be able to report missing coverage and abstain on the first call. Only expose evidence IDs available to the role. Pass validated recommendations, disagreements and their supporting evidence to the portfolio agent in a form that fits the configured context.
- Reuse the single-agent action rules for synthesis. A buy needs an eligible candidate and positive weight within the cap. A sell selects a held ticker and omits weight in the model response. Enforce one action per ticker. Preserve valid holds, the shared risk checks, point-in-time filtering and next-open simulated execution.
- Keep role-level errors visible alongside the weekly outcome. Include deterministic tests in `backend/tests/test_llm.py` for the observed protocol errors, missing coverage, tool follow-ups, evidence transfer, budget exhaustion, and a complete three-analyst decision through portfolio validation. Include a failure case proving that a rejected required analyst produces no orders. Run the backend suite with mocked inference.

## Run the experiments

1. Run the January 2026 smoke window first with `qwen3.5:9b`, then with `gemma4:12b`. Use one model family across all four roles, `analyst_concurrency=1`, and one experiment at a time on the laptop. Check the persisted trace for each model. Require at least one week with three validated analyst responses and a validated portfolio decision. A valid hold qualifies. Diagnose recurrent errors before spending time on the annual runs.
2. Run six multi-agent benchmarks sequentially, both models for 2026, then 2025, then 2024. Match the corresponding ten-ticker single-agent runs in the report, including dataset version, historical date bounds and warm-up. The last 2026 session is October 30. Start each run with a fresh $100,000 cash portfolio and use weekly decisions on VOO, QQQ, NVDA, TSLA, AAPL, V, DIS, BE, AMZN and MSFT.
3. Copy the historical single-agent settings for costs, dividends, interest, candidate selection, model sampling and context. Keep the ten-position maximum, 20% per-position cap and 100% total exposure limit. Save reproducible configurations and record any multi-agent budget differences. Use the same protocol across measured windows. If a protocol fix changes behavior mid-campaign, rerun affected comparisons and identify the final experiment IDs.
4. Verify each run from its persisted decision traces, fills and equity series. Reconcile ending equity and return, count accepted weekly decisions against all scheduled decisions, and audit cash and total exposure after each fill. Surface failures by model, role and error code. Preserve completed-with-warnings results and include the rejected weeks in the denominator.

## Update the report

Edit `docs/benchmark-report.md` in place. Add a multi-agent row for each model to each existing yearly table, label the single-agent rows explicitly, and regenerate each yearly return chart from daily equity with matching legend labels. Keep the existing columns, including experiment ID, and retain one table and one chart per year. Keep smoke and debugging runs out of the performance tables.

Briefly update the methodology with the role sequence, price-only abstention and sequential execution. In the discussion, compare each model with its own single-agent baseline on return, drawdown and decision reliability. Use observed call counts and latency to explain the cost of analyst review. State which approach the results favor and where the trade-off differs by year.
