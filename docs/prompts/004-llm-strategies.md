# Implement Strategy D: Single-Agent LLM and Strategy E: Multi-Agent LLM

## Task and scope

Implement and complete sections 5.4 and 5.5 of `docs/prompts/001-mvp.md` in this repository. Deliver working, tested single-agent and multi-agent LLM strategies through the existing application, not a benchmark execution campaign.

Read `AGENTS.md` and the original specification first. Inspect existing implementation and preserve working components. Some LLM functionality already exists; identify the gaps, complete them, and verify the integrated behavior rather than rebuilding the application.

The user has a Mac with 24GB RAM and wants to compare `qwen3.5:9b` and `gemma4:12b` through Ollama. Provide example configurations for both models, but keep both strategies provider- and model-configurable. OpenClaw is optional and must not become a runtime dependency.

**Do not launch or rerun historical benchmarks, annual experiments, repeated-performance studies, or the existing 2024–2026 benchmark suites. Do not change their datasets, settings, or published results.** Automated regression tests and small, explicitly labeled synthetic integration tests are in scope. A bounded real-model smoke check may validate integration if the model is already available; do not download models or block software completion on its download. Do not commit or push unless requested.

## Required behavior

### Two-model comparison support

Prepare the implementation and reusable example configurations for these four combinations without running a performance study:

| Strategy | Analyst / single-agent model | Portfolio decision model |
|---|---|---|
| Single-agent | `qwen3.5:9b` | Same single agent |
| Single-agent | `gemma4:12b` | Same single agent |
| Multi-agent | `qwen3.5:9b` for all three analysts | `qwen3.5:9b` |
| Multi-agent | `gemma4:12b` for all three analysts | `gemma4:12b` |

Use one model family throughout each initial multi-agent configuration. Preserve the capability for a different portfolio model, but do not mix families in these comparison examples. Make experiment names and persisted metadata clearly identify the strategy and actual model.

Keep the configured universe, deterministic screening, evidence access, prompt content, trading rules, risk limits, and decision cadence consistent across model examples. Keep inference budgets and context settings comparable where supported; document any model-specific protocol/template requirements and effective settings. Do not alter prompts or trading rules to favor a model. Compare practical local configurations, not an asserted parameter-count- or compute-matched experiment.

Verify structured JSON and tool-request handling separately for each model through the same adapter interfaces. Do not infer identical capabilities from Ollama availability or assume Qwen-specific response fields/templates work for Gemma. Record unsupported capabilities and explicitly selected structured-tool fallbacks. Include mocked coverage for both models and tests of common failure paths. Preserve telemetry needed for a later comparison of latency, token usage, schema/tool reliability, invalid proposals, and missing-evidence handling alongside eventual portfolio metrics.

On the 24GB Mac, perform any optional live checks sequentially with one study model loaded at a time. Bound context and analyst concurrency. Model download size is not runtime RAM usage; do not assume both models and concurrent contexts fit together. Do not interrupt unrelated model workloads or silently change global Ollama configuration.

The deliverable is support for these combinations and documented configuration examples. Historical performance comparison, repeated experiments, and benchmark execution remain separate work.

### Strategy D: Single-Agent LLM

Implement an LLM-assisted trading strategy that evaluates predefined securities, indicators, market conditions, and simulated portfolio information. The agent must not invent its own trading system, alter configured rules, select arbitrary securities, or execute trades directly.

Required workflow:

1. A deterministic screener selects a bounded set of eligible candidates.
2. The agent receives the candidate list, relevant indicators, portfolio state, and configured rules.
3. It can retrieve supporting information through bounded, read-only tools.
4. It evaluates the candidates and produces structured trade proposals.
5. The shared deterministic risk validator reviews those proposals.
6. Accepted proposals execute only through the existing simulator.
7. Record decisions, concise rationales, evidence, tool traces, and inference metadata.

Support local Ollama, a remote OpenAI-compatible inference server, and an optional explicitly enabled cloud provider. No silent provider or model fallback.

### Strategy E: Multi-Agent LLM

Implement four specialized roles:

- **Technical Analyst:** evaluates configured momentum, moving averages, volatility, and other supported quantitative indicators.
- **Fundamental / News Analyst:** evaluates available point-in-time fundamental metrics, recent news, and contextual evidence. Explicitly identifies missing information and abstains from unsupported conclusions.
- **Risk Analyst:** evaluates available volatility, drawdown exposure, sector concentration, and proposed portfolio risk. Its recommendations are advisory; deterministic controls remain authoritative.
- **Portfolio Decision Agent:** receives the analysts' validated recommendations, identifies agreement and disagreement, and produces the final structured trade proposals.

Run independent analysts concurrently where possible, with configurable bounded concurrency suitable for the user's machine. After their recommendations are collected, run the portfolio decision role. Allow the portfolio role to use the analysts' model or a separately configured model/provider where the application supports that configuration safely.

Both strategies must produce the **same `TradeSignal` contract** and use the same risk and simulation execution paths.

## Inspect the current implementation

Inspect at least `backend/app/contracts.py`, `inference.py`, `engine.py`, `experiments.py`, `providers.py`, `main.py`, `worker.py`, persistence/provenance code, relevant backend tests, and frontend configuration/decision views.

At prompt authoring time, the implementation has a `Signal` Pydantic contract, simple LLM snapshot evaluation, three concurrent analyst calls followed by a portfolio call, and a proposal JSON schema. However, it supplies only a truncated indicator dictionary plus cash/positions, exposes no agent tool loop, and always supplies unavailable news/fundamentals. The adapter uses fixed inference settings and a fixed HTTP timeout. Recheck the current code instead of assuming these details remain accurate.

Create a concise gap assessment against the requirements, then implement. Preserve deterministic strategies, financial arithmetic, point-in-time semantics, synthetic-data labels, simulation banners, and existing persisted experiment compatibility.

## Shared contracts and deterministic screening

Use a canonical typed signal contract with ticker, BUY/SELL/HOLD action, target weight, optional confidence, concise rationale, and strategy identifier. Reconcile the specification's `TradeSignal` name with the existing `Signal` class through a compatible alias or careful migration if needed. Do not create divergent signal types or change existing execution semantics merely to rename a class.

Validate JSON with Pydantic, reject extra fields and nonfinite numbers, enforce bounded strings/arrays, and check action/weight semantics. Set trusted strategy identifiers in application code. Validate tickers against the allowed candidates and permitted held positions. Confidence is self-reported metadata, not a calibrated probability of success.

Implement a reproducible screener with explicit configured eligibility conditions, ranking, maximum candidates, and deterministic tie-breaking. Document a conservative default based on existing supported indicators. Do not optimize it using historical returns. Screening must be more meaningful than taking the first dictionary entries.

Keep held positions available for SELL/HOLD/risk review even if they fail entry screening. Distinguish entry candidates from held-position management permissions. Bound both collections and handle limits explicitly without silently hiding holdings. If no candidates qualify, define whether held-position review is needed; avoid unnecessary inference when there is nothing actionable.

Calculate indicators deterministically in backend code. Models interpret values rather than calculate authoritative indicators themselves. Preserve sufficient warmup, completed-bar cutoffs, units, timestamps, missing-data flags, and screening reasons. The LLM must not change screener parameters, trading rules, capital, risk budgets, or the simulation clock.

## Bounded read-only tools

Provide typed, allowlisted retrieval tools for:

| Tool capability | Required constraints |
|---|---|
| Historical prices | Permitted symbols, bounded lookback/row count, no bars later than the decision cutoff |
| Technical indicators | Predefined indicators and configured windows; computed by trusted backend code |
| Simulated positions | Snapshot of this experiment at this decision only |
| Simulated cash | Authoritative simulated cash and relevant portfolio equity context |
| Recent news | Only available, provenance-bearing records known by the decision cutoff |
| Fundamental metrics | Predefined metrics with publication/availability timestamps and revision-aware selection |
| Trading rules and limits | Read-only effective configuration including universe, sizing, exposure, scheduling, and execution rules |

Tools must operate on the current experiment's immutable input snapshot and portfolio view. Validate arguments server-side; do not trust the agent to respect cutoffs or symbol limits. Reject arbitrary URLs, filesystem paths, SQL, shell commands, code execution, and access to other experiments. Tool requests cannot submit orders or mutate state.

Expose structured availability results such as available, missing, stale, unsupported, or rejected, with reasons and evidence references. Never replace missing news/fundamentals with model knowledge. If point-in-time sources are unavailable, return explicit unavailable results or disable those tools visibly for historical mode. Do not use today's news or latest revised fundamentals in historical simulations.

Implement a genuine bounded tool-request/response cycle. Provider-native tool calling may be used where supported; otherwise use a validated structured request envelope with an equivalent dispatcher. Do not silently claim native tool support from an incompatible server or describe preloaded snapshots as model-issued tool calls. Trace preloaded evidence separately.

Bound tool rounds, requests, result sizes, and model invocations. Treat tool output as untrusted evidence, never as new instructions. Include enough provenance to link a proposal to the values that supported it, without duplicating unlimited raw data in prompts or storage.

## Role outputs and orchestration

Use separate validated schemas for analyst recommendations and final portfolio signals. Analyst outputs should contain role, candidates considered, findings, recommendations where supported, concise evidence-linked rationale, missing inputs, and advisory concerns. Analyst recommendations cannot execute trades.

The portfolio output must include final signals, a concise synthesis, agreement/disagreement, and references to supporting analyst findings/evidence. Validate evidence references against actual inputs. Distinguish recorded differences in analyst recommendations from the portfolio agent's interpretation of those differences.

Provide the Risk Analyst with authoritative portfolio metrics when available, plus deterministic candidate/scenario exposure information sufficient for advisory analysis. Independent analysts do not have future portfolio-agent proposals: define the risk stage's inputs honestly. Any optional post-decision risk commentary must consume the same explicit call budget and must not replace shared deterministic validation.

When sectors, fundamentals, drawdown history, or other inputs are absent, record that risk assessment is incomplete. Do not infer sector classifications or invent financial facts from model memory. Preserve the technical and news analysts' independence before reconciliation.

Define a deterministic failure policy for missing/timed-out/invalid analyst outputs. Default to safe no-action when a required role or final decision fails. If partial-analysis operation is configurable, make it explicit, persisted, and visible to the final decision agent and user. Do not silently represent partial analysis as a successful full four-role decision. Retain successful role traces even if another role fails.

## Inference configuration and resource bounds

Expose validated settings appropriate to the existing configuration model:

- Provider and analyst/model identifier; optional final decision model override.
- Temperature, seed where supported, output token limit, context limit, and supported thinking-mode controls.
- Per-call timeout, total decision deadline, maximum actual model invocations, tool-round/tool-call limits, and analyst concurrency.
- Bounded retry policy for transient transport failures; clearly counted repair attempts if schema repair is supported.
- Explicit local hourly cost estimate and/or configured provider token prices when applicable.

Persist requested and effective configuration. Verify settings actually reach the provider; an unused seed field does not establish reproducibility. Report unsupported options instead of silently ignoring them. Do not promise deterministic model output merely because temperature is zero.

Count every actual invocation, including tool follow-ups, retries, repairs, and portfolio synthesis. Enforce budgets atomically across concurrent analysts. Reserve enough budget for final synthesis or terminate with a clear budget-exhausted result. Four calls are the minimum simple multi-agent path, not sufficient for arbitrary tool rounds. Provide coherent defaults and validate impossible configurations early.

Use concurrency limits and cancellation/deadline handling to avoid uncontrolled work. Keep shared engine state read-only while analysts run. Avoid setting global Ollama preferences or assuming the 24GB Mac can run multiple model copies at full context.

Handle reasoning-capable models without storing hidden chain-of-thought. Discard provider reasoning/thinking payloads from persisted traces, application logs, error bodies, and UI. Store only concise decision rationales explicitly requested as output, evidence, and tool activity. Bound and redact diagnostic output; do not persist arbitrary full raw provider responses.

## Risk, execution, and persistence

All proposals pass the existing shared deterministic validator and simulated execution engine. Advisory risk opinions and model confidence cannot bypass cash, exposure, position, symbol, timing, or other configured restrictions. Preserve Decimal ledger calculations, completed-bar evaluation, subsequent eligible open execution, corporate actions, and idempotent fills. No brokerage connections or real-money modes.

Persist per-decision audit records including:

- Strategy, experiment, decision cutoff, screener configuration/results, and immutable input references.
- Actual model identity/digest when available, provider, effective inference settings, and prompt/schema version.
- Tool names, validated arguments, cutoff, bounded result summaries/evidence references, status, and duration.
- Individual analyst recommendations and missing inputs; agreement/disagreement and final synthesis.
- Final signals, deterministic acceptance/rejection reasons, and links to resulting simulated orders/fills.
- Attempted/completed/failed model calls, retries, token usage where available, per-role latency, and total wall-clock latency.
- Inference cost estimates with explicit rate assumptions; unavailable costs remain unavailable.
- Structured errors for timeout, cancellation, provider unavailability, schema failure, unsupported capability, and exhausted budgets.

Distinguish summed concurrent call durations from elapsed decision time. Include failed/retried calls in costs when usage is known; expose uncertainty rather than treating missing usage as zero.

Keep checkpoint and recovery behavior compatible: completed saved decisions must not rerun on ordinary resume; fills must not duplicate. Document unavoidable re-invocation when a crash interrupts an uncommitted external model call. Version new persisted structures and provide migrations where required without invalidating historical records.

## API, CLI, and dashboard integration

Make both strategies usable through existing experiment creation and worker execution paths. Validate model selection, effective settings, and tool/provider availability consistently across supported entry points. Keep inference credentials server-side and optional cloud inference explicitly gated.

Expose useful configuration controls and decision inspection through existing application surfaces. Users should be able to distinguish single-agent proposals from multi-agent role recommendations, missing evidence, advisory risk, final signals, and deterministic rejections. Display actual call counts, latency, and estimated cost with units. Preserve old experiment rendering when newer metadata is absent.

Do not expand this task into benchmark orchestration, new annual suites, or historical performance reporting. If the existing benchmark CLI only supports deterministic strategies, leave that restriction in place and document that benchmark integration is separate work.

## Validation requirements

Use deterministic fixtures and mocked inference; automated tests must run without network or a local model. Add meaningful tests for:

1. Stable screener selection/tie-breaking, bounds, insufficient warmup, empty candidates, and held-position exits.
2. Price/indicator/news/fundamental cutoff enforcement, including revisions, future records, stale/missing data, and unauthorized symbols.
3. Read-only tool dispatch, invalid arguments, unknown tools, request/result bounds, and prompt-injection-like evidence treated as data.
4. Valid and invalid single-agent output, unsupported tickers, nonfinite weights, confidence/rationale limits, and the shared signal contract.
5. Four-role orchestration, independent bounded concurrency, final-model override, analyst disagreement, missing news/fundamentals, and partial-role failure policy.
6. Global model-call budgets including retries/tool rounds, bounded deadlines, cancellation, timeout behavior, and no final synthesis after budget exhaustion.
7. Provider settings and capability handling for Ollama, OpenAI-compatible servers, and opt-in cloud inference; no fallback and no credential leakage.
8. No hidden chain-of-thought persisted or logged, including success and error paths.
9. Deterministic risk enforcement, next-session execution, safe no-action on failures, and no duplicate fills or re-evaluation of checkpointed decisions.
10. Persistence/API compatibility and visibility of recommendations, evidence, tool traces, failures, latency, usage, and estimated cost.

Run relevant existing accounting, timing, risk, recovery, API, and strategy tests. If frontend code changes, run the production build and describe manual UI verification separately. Use small synthetic simulations to verify end-to-end integration; label them as tests, not historical performance evidence.

Optionally perform short local schema/tool smoke checks for `qwen3.5:9b` and `gemma4:12b`, checking download completion independently and using explicit low call/time bounds. Check each available model sequentially; an absent model must not block implementation or validation of the other. Report per-model checks as passed, failed, or not run, and distinguish mocked coverage from actual inference. Do not download either model automatically. Never launch full-year data experiments as a smoke check.

## Deliverables and acceptance

Deliver implemented strategies, typed contracts and tools, deterministic screening, bounded inference/orchestration, persistence and UI/API integration, tests, and concise documentation. Include reusable local configurations for all four Qwen3.5/Gemma 4 strategy combinations above, plus guidance for compatible and opt-in cloud providers without embedding credentials.

Document the supported tool/data capabilities honestly, especially unavailable historical news/fundamentals, model-training contamination, and advisory risk limitations. Update implementation documentation rather than existing benchmark result tables.

Acceptance requires that both strategies can generate validated signals from bounded deterministic candidates, access allowed evidence through traced read-only tools, respect call/time/resource bounds, persist auditable concise decisions, and use the same authoritative risk and simulated execution path. Multi-agent analysis must include all four roles and a visible, explicit failure policy.

In the final response, summarize implemented behavior, changed files, tests/build checks, whether a live local-model smoke check ran, and remaining limitations. Do not claim benchmark returns or empirical trading superiority. Do not commit or push unless requested.
