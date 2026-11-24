# GPT-5.5 single-agent campaign

Each yearly configuration comes from the Qwen and Gemma single-agent experiments in the benchmark report. Their IDs and dataset content checksums are in `sources.json`. The runner checks both source configurations and the local datasets before starting. Smoke uses the 2026 configuration with an end date of January 20.

Use the backend environment and database containing those experiments and their registered, immutable datasets. Set `ENABLE_CLOUD=true` and supply `OPENAI_API_KEY` in the backend process environment. This campaign uses the standard OpenAI endpoint, standard service tier, pinned snapshot, and Chat Completions JSON mode. The adapter maps `thinking: false` to `reasoning_effort: none`, omits temperature and seed, and appends “Return JSON.” to the shared prompt. Server-side schema, evidence, tool and risk validation still apply. The request has no hosted tools. [Model documentation](https://developers.openai.com/api/docs/models/gpt-5.5)

## Running the campaign

Run these stages separately from `backend/` when paid execution is intended.

1. Run `PYTHONPATH=. uv run python ../scripts/gpt55_benchmarks.py smoke`. Inspect the three weekly decisions in the saved experiment and the audit in the printed directory. Check validated weeks (including holds), provider and schema errors, length stops, retries, usage and latency. Diagnose repeated failures before annual execution.
2. Review the smoke projection for all 147 measured weeks. It extrapolates priced smoke usage per scheduled week. Missing usage makes the projection partial. Verify the dated standard USD rates in the audit against the model documentation when launching the campaign.
3. Run `PYTHONPATH=. uv run python ../scripts/gpt55_benchmarks.py annual --reviewed-smoke ID` with the inspected experiment ID. The runner saves the review, then executes 2026, 2025 and 2024 sequentially. For interruptions, reissue the same command. Completed runs are audited again and interrupted runs resume from their last committed daily checkpoint.
4. Run `PYTHONPATH=. uv run python ../scripts/gpt55_benchmarks.py publish` to audit all three measured experiments and update the existing report and charts. This stage reads completed experiments and requires no API key.

Campaign files live under `reports/gpt-5-5-single-agent/<protocol hash>/`. Preserve this directory with the database and datasets. It contains exact configurations, source IDs, implementation and dataset checksums, final experiment IDs, the smoke review and per-window audits. Changing the configurations, source manifest or backend implementation selects a separate campaign directory. Earlier outcomes and checkpoints remain available. Each measured window starts with a fresh portfolio.

The API cost estimate prices provider-reported tokens, including retries. Cached tokens are a subset of input tokens. If either input or cache count is missing, the input charge for that call is unknown. Missing output counts similarly exclude the output charge. The audit lists missing counts and sums only amounts that can be priced. Requests interrupted before a checkpoint may appear on the provider invoice without a corresponding persisted trace.

## Spend limit

Smoke has a $2 standard API token budget. Each measured year has a separate $5 budget. The worker reserves enough for the full uncached request and maximum completion before each API attempt, including retries. It settles reservations using provider usage. Requests without complete usage retain their maximum reservation, including after a crash. A request that cannot fit is recorded as a rejected decision and sends no traffic. The audit reports priced usage and the total spent or reserved. Resuming the experiment reuses its budget. A separately created experiment starts a new budget.
