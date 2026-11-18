# Bounded LLM strategies

Both strategies are simulation only. The initial configurable universe is VOO,
QQQ, NVDA, TSLA, AAPL. The implementation extends the previous snapshot-only
adapter with deterministic screening, structured read-only tool loops, separate
analyst/final schemas, bounded orchestration, and versioned audits. The existing
Decimal ledger and next-session risk/execution path remain authoritative.

## Local examples

Four files in `configs/examples/` cover `single_agent` and `multi_agent` with
`qwen3.5:9b` and `gemma4:12b`. They use identical evidence, rules and resource
settings. Each multi-agent example uses one model throughout. These are practical
local configurations, not compute-matched experiments. Confidence is self-reported.

The examples reference a separate synthetic fixture containing all five symbols.
When ready to use them, create it with `uv run python -m app.cli llm-demo` from
`backend/`. This registers data only. Create an experiment using
`uv run python -m app.cli experiment --config ../configs/examples/single_agent-qwen3.5-9b.json`.
Add `--queue` to request worker execution. These commands were not run as part of
implementation. Benchmark integration remains separate and restricted to the
existing deterministic strategies.

Select the dataset and model in the dashboard or submit the same configuration to
the existing experiment API. Models must already be installed. No downloads or
Ollama global settings changes occur. Use concurrency one on a 24GB Mac and run
model families sequentially. An 8192-token context does not guarantee a given
model fits RAM; download size is not runtime memory consumption.

## Contracts and policy

`TradeSignal` aliases `Signal`. Trusted code stamps strategy IDs. BUY requires a
positive target weight and entry eligibility; SELL requires a held position and
zero target weight, meaning full exit. HOLD never executes a rebalance. Duplicate
or unauthorized symbols reject the whole model decision. Deterministic risk limits
still independently validate execution at the next eligible open.

The screener requires a fresh completed bar, long-window-plus-one warmup, short
moving average above long moving average, and positive long-window return.
Candidates rank by descending return, then ticker, with ten maximum by default.
All holdings remain available for exit review; overflow fails visibly. Price tools
return up to 100 close-price rows from the immutable decision snapshot. Prices are USD closes adjusted for splits through the cutoff. Indicators are backend
computed; split adjustments include only actions known through that session.

Technical, fundamental/news, and advisory-risk roles run independently under a
semaphore. The final role runs only after all three validate. Missing evidence is
explicit; it does not itself make a role fail. Invalid/missing role output does:
no partial-analysis trading is supported. Recorded recommendation differences are
separate from the final agent's interpretation. Risk input describes current
portfolio exposure, drawdown and candidate weight limits, not future proposals.
Sectors are unavailable. Analyst advice cannot override deterministic controls.

Defaults: 12 actual invocations, two tool rounds per role, eight tool requests per
decision, one retry per invocation, 90 seconds per call, 600 seconds per
decision, and one concurrent analyst. Retries and follow-ups consume the shared
budget; one invocation is reserved for final synthesis. No automatic schema repair.
Worker cancellation is polled every half second while asynchronous inference runs.
Provider-side compute may continue after an HTTP request is canceled.

## Evidence imports

`POST /api/datasets/import` accepts optional `agent_evidence` alongside bars and
actions. Imports are immutable and included in the manifest checksum. Each record
has `id`, integer `revision`, `ticker`, `kind` (`news` or `fundamentals`),
`published_at`, `available_at`, and `provenance`. Both timestamps require a timezone;
availability cannot precede publication. News uses bounded `text`. Fundamentals
require `metric`, finite `value`, and `unit`. Supported metrics: `revenue`,
`net_income`, `eps`, `debt_to_equity`, `pe_ratio`. Use a stable ID per item/metric
observation and increase its revision for amendments.

Tools select the latest available revision of each item at the exchange close,
then enforce freshness (news seven days, fundamentals 180 days by default).
Future records never enter tool output. Missing, stale and rejected results are
explicit. No news service, web retrieval, sector source, or fundamental data
subscription is bundled. Evidence text is untrusted data, never instructions.
The tool dispatcher accepts no paths, URLs, SQL or executable code.

## Providers and telemetry

All providers use the explicitly selected `structured_envelope_v1` JSON request
protocol, not native tool calling. Ollama receives a JSON schema, temperature,
seed, output/context limits, and optional `thinking` control. Compatible/cloud
adapters request JSON-object output, temperature, seed, and output limit; context
is server-managed and seed support is explicitly unverified. Unsupported thinking
controls are rejected. Model/template support is not inferred from a model listing.
A server rejecting schema/settings fails closed; there is no silent fallback.
Qwen and Gemma share mocked adapter tests; neither has been verified live here.
No Qwen-specific reasoning field or template is assumed for Gemma.

`OLLAMA_BASE_URL`, `COMPATIBLE_BASE_URL`, `OPENAI_BASE_URL` and corresponding API
keys stay backend-only. Cloud requires `ENABLE_CLOUD=true`. Optional final model
and provider overrides use the same validation. Nonzero temperature and seed zero
are supported; no seed or temperature setting promises deterministic output.

Audits retain requested rules, effective settings on completed calls, returned model
name, concise outputs, tool evidence, sanitized errors, usage and timings. A model
digest is not currently supplied by the chat adapters. Hidden thinking fields,
raw provider bodies and validation input text are not persisted. Input size uses
a conservative character bound, not an exact provider tokenizer. Tool results
are capped at 16KB and provider responses at 256KB after receipt.

Elapsed decision seconds differ from summed concurrent call seconds. Local cost
uses elapsed time and the configured USD/hour estimate. Optional input/output
USD-per-million-token rates take precedence; missing usage yields unavailable cost.
Failed attempts are counted and usage is unknown when a response cannot be parsed.

JSON audits use version 1 within existing JSON tables; no database migration is
required. Old experiments remain readable. Saved decisions resume without model
re-evaluation; a crash before checkpointing an external response can cause another
invocation. Decision IDs link to subsequent simulated orders/fills. Checkpoints
retain audits even before final persistence into normalized audit tables.

Historical point-in-time retrieval cannot remove training-data contamination from
a model. These examples and offline tests establish software behavior, not trading
performance or empirical superiority.

## Decision error codes

New failures include `error_code` and `error_stage` in the decision audit and
associated call trace. Existing saved decisions are unchanged and may only have
an exception name. Codes contain trusted application constants, never model text,
provider error bodies, credentials, or validation inputs.

| Stage | Codes |
|---|---|
| Request | `input_context_limit` |
| Provider | `provider_unavailable`, `call_timeout`, `provider_http_error`, `unsupported_capability_or_model`, `provider_response_size_limit`, `invalid_provider_json`, `invalid_provider_response` |
| Schema validation | `invalid_model_json`, `output_schema_invalid` |
| Protocol validation | `mixed_tools_and_output`, `expected_portfolio_output`, `expected_analyst_output` |
| Semantic validation | `unknown_evidence_reference`, `unauthorized_signal_symbol`, `duplicate_signal_symbol`, `ineligible_buy_symbol`, `nonpositive_buy_weight`, `invalid_exit`, `unknown_analyst_candidate`, `unauthorized_finding_symbol`, `unknown_finding_evidence` |
| Budget | `model_budget_exhausted`, `tool_budget_exhausted`, `tool_rounds_exhausted` |
| Orchestration | `required_analyst_failed`, `decision_deadline_exceeded`, `canceled`, `internal_error` |

For a required analyst failure, inspect that role's call trace for its specific
cause. HTTP failures additionally include the numeric `http_status`.
`status: completed` on a call denotes a parsed response; `validation_status`
separately reports `validated`, `tool_request_validated`, or `failed`. Successful
parsing followed by a protocol/semantic rejection records `validation_status: failed`
and the precise error code. Unknown errors use `internal_error` without exposing
exception messages. Provider stop reasons and reported token counts are retained
when model JSON parsing or schema validation fails.

Malformed JSON can be retried once per tool round when the configured retry and
model call budgets permit it. The retry uses the same response schema unless
the remaining tool budget requires a final response. If the provider reports a
length stop, the output token limit doubles up to the configured context limit
and the supported output ceiling of 8192 tokens. Each attempt has its own audit
entry. A repeated parse failure rejects the decision.

Older audits use `invalid_entry` for both buy checks. New audits use
`ineligible_buy_symbol` for an allowed symbol outside the entry shortlist and
`nonpositive_buy_weight` for an eligible buy with zero weight.
