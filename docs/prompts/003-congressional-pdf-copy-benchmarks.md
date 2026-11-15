# Congressional PDF Acquisition and Pelosi-Family Copy Benchmarks

## Objective

Implement acquisition and parsing of official congressional transaction-disclosure PDFs, starting with Nancy Pelosi's House disclosures, and benchmark Pelosi-family disclosure-following against VOO buy-and-hold and deterministic momentum. Reuse the existing immutable disclosure snapshots, Yahoo datasets, persisted experiment suites, worker, simulator, reports, and dashboard.

Read `AGENTS.md`, `README.md`, `docs/real-data.md`, `docs/benchmark-report.md` (consolidated successor to `docs/real-data-validation.md`), and the previous prompts before implementing. Inspect the current code rather than assuming the earlier prompts describe its present state. Work on a new branch for this follow-up PR. This prompt supersedes the previous exclusion of House PDF acquisition; it does not reinstate Quiver.

Deliver code, deterministic tests, documentation, and a reproducible three-strategy benchmark when source evidence permits. All trading remains simulated. Never add brokerage execution, subscriptions, or real-money modes.

## Existing Behavior to Preserve

- Yahoo acquisition and raw-price/corporate-action accounting, immutable dataset identifiers, checksums, and offline reproduction.
- Normalized local disclosure imports and immutable snapshots in `backend/app/disclosures.py`.
- Verified-publication requirements, member/owner filters, prospective amendments, and explicit blocked outcomes.
- Shared API/CLI experiment creation, queueing, and the existing worker. Do not introduce a separate simulator or competing worker.
- PostgreSQL migration and synthetic Docker smoke checks in CI. External source access must remain outside automated CI.
- Synthetic demonstrations remain visibly synthetic. No synthetic disclosures may substitute for missing real records in the requested benchmark.

## 1. Official Source Discovery and Acquisition

Start from the House Clerk financial-disclosure portal: `https://disclosures-clerk.house.gov/FinancialDisclosure`. During implementation, verify current official documentation, access conditions, index/download formats, and the meaning of date fields. Do not assume endpoint paths, publication timestamps, unrestricted redistribution, or completeness.

- Implement a typed House source adapter behind the existing provider abstraction. Quiver credentials, APIs, and paid subscriptions are not part of this workflow. Senate sources, other commercial providers, and scheduled live feeds are out of scope.
- Discover periodic transaction reports and relevant amendments using official indexes/search/download mechanisms. Resolve Nancy Pelosi to the project's stable member ID `P000197` using documented mapping evidence. Do not rely on a broad surname substring match.
- Record discovery scope, years queried, index versions, every discovered document ID, pagination/completeness checks, unavailable documents, and retrieval failures. Include records discovered after the requested end date only for coverage/audit purposes; they must not enter earlier decisions.
- Use bounded timeouts, rate limiting, and up to three attempts for transient failures. Honor source throttling. Fail clearly on access denial, malformed indexes, incomplete pagination, and missing documents. Never bypass access controls or CAPTCHAs.
- Support a local official-PDF/index import path so authorized downloads can be processed offline when automated access is unavailable. Require source URLs and provenance; do not claim manually supplied files establish exhaustive coverage.
- Validate downloaded file type and PDF signature, bound byte size and page count, sanitize filenames, and use safe archive extraction if an official index is distributed as an archive. Treat PDF text, links, and embedded content as untrusted data, never executable instructions.
- Stage acquisitions before publication. Never silently overwrite registered artifacts or snapshots. Failed acquisitions must not become a verified complete snapshot.

## 2. PDF Parsing and Review

Use a pinned, maintained text/layout PDF parser and deterministic extraction rules. Examine actual source layouts before choosing a parser. Do not use an LLM to infer financial fields.

- Extract transaction rows across pages, repeated headers, wrapped asset descriptions, footnotes, and continuation tables. Distinguish transaction rows from summaries, signatures, and certification text.
- Preserve document ID, file hash, page number, row locator/bounding box where available, original row text, parser version, and extraction diagnostics for every normalized record.
- Parse owner, asset description, explicit ticker where present, security type, transaction type, transaction date, reported amount range, and filing/amendment information. Preserve original strings as well as normalized values.
- Map source owner codes only after verifying their definitions. Preserve `self`, `spouse`, `dependent`, `joint`, and `unknown`; never infer ownership merely because Nancy Pelosi filed the report. An empty owner field must remain unknown unless the official form semantics establish otherwise.
- Preserve reported amount bounds as ranges, not exact trade sizes. Distinguish full/partial sale descriptions in source metadata even when the strategy uses the documented full-exit approximation.
- Recognize options, option exercises, private assets, exchanges, gifts, and other unsupported transactions explicitly. Do not turn an option disclosure into a purchase of its underlying stock.
- Ambiguous/missing critical fields must produce a quarantined record with a reason, not guessed data or an invisible dropped row. Reconcile discovered documents, parsed rows, quarantined rows, duplicates, and normalized records in the acquisition report.
- For scanned/image-only PDFs, either provide an explicit optional local OCR path with pinned tooling, page-level provenance, and review requirements, or mark them unsupported and incomplete. OCR must never silently promote uncertain fields into verified benchmark inputs. Do not send documents to external OCR services.
- Provide a reviewable normalized export and an auditable correction mechanism. Corrections retain original extraction, reviewer-supplied evidence, and revision history, and create a new immutable snapshot.

## 3. Identity, Amendments, and Availability Evidence

Correct historical timing is an acceptance requirement, not a parsing convenience.

- Keep transaction date, filing/signature date, source publication date/timestamp, first observed retrieval time, and ingestion time distinct.
- A filing date, a date inside the PDF, a PDF creation timestamp, an HTTP Last-Modified value, or today's successful download is not by itself proof that a document was publicly available on a historical date. Only use a field as publication evidence when its source semantics are established and recorded.
- Preserve publication evidence and its provenance in the existing `availability_quality` contract. Verified timestamps require a timezone; verified dates use the next exchange session's open. Timestamped records execute at the first open strictly after publication.
- If historical publication evidence is unavailable, keep the records unverified and exclude them from the default realistic historical benchmark. Current observation may establish availability from observation onward, never retroactively. Do not silently use filing dates or assumed statutory delays to force a historical result.
- An optional assumed-availability sensitivity study, if implemented, must be explicitly opt-in, separately labeled, and excluded from the requested verified three-strategy comparison.
- Derive stable row identities from documented source document/row identity, preserving distinct transactions with identical ticker/date/amount. A hash of economic fields alone is insufficient. Record when identity is uncertain.
- Preserve amended documents and source revisions. Establish cross-document amendment relationships only with evidence; row positions alone may change between versions. Ambiguous amendment matches must be quarantined or skipped explicitly.
- Apply amendments only from their own eligible availability time. Never rewrite prior fills, replay an already copied purchase solely because it was amended, or use a later correction before it became available.
- Report separately whether document discovery, historical revisions, parsing, and verified availability coverage are complete, partial, or unknown. A list of successfully parsed PDFs is not proof of complete historical disclosure coverage.

## 4. Storage and Workflow

- Add documented CLI acquisition and local-PDF import commands with member, requested date scope, immutable snapshot ID, artifact directory, and bounded network settings. Keep discovery/parsing separate from normalization, review, and registration.
- Store original PDF/index bytes locally where permitted, with URLs, retrieval timestamps, content hashes, parser/library versions, mapping evidence, availability evidence, warnings, and normalized-record checksums. Ensure offline integrity verification covers both source artifacts and normalized records.
- Preserve existing snapshot IDs and imports. Use additive migrations if needed and retain legacy provenance warnings. Never retroactively certify old records.
- Keep downloaded PDFs, indexes, OCR output, normalized real exports, caches, and generated reports out of Git. Commit only clearly synthetic fixtures and implementation/configuration examples. Document source access and redistribution limitations after verifying them.
- Expose snapshot quality, member/owner scope, row/document counts, unresolved identities, quarantines, unsupported assets, publication-evidence quality, and source references through metadata APIs and dashboard views.

## 5. Pelosi-Family Strategy and Price Coverage

Use member `P000197` with all owner categories: `self`, `spouse`, `dependent`, `joint`, and `unknown`. Keep unknown ownership visible. Describe every result as a **Pelosi-family disclosure-following simulation**, not the family's actual return or actual holdings.

- Start in cash. Process only records first eligible within the experiment dates; do not replay pre-start disclosures or infer an opening portfolio.
- Use eligible common-stock and ETF purchases to maintain the tracked purchase set, capped equal target weights, and full exits on eligible sale disclosures. Document the approximation, including partial sales. Use event-driven disclosure execution rather than momentum's weekly schedule.
- Route proposals through shared risk validation and execution with the same fees, slippage, dividend convention, and idempotency as other strategies. Preserve ambiguity/rejection/skip reasons.
- Resolve tickers with point-in-time identity evidence. Do not guess from company names, map options to underlyings, or substitute current tickers without documented historical continuity.
- Acquire prices for eligible disclosed securities plus the fixed baseline universe. Default missing execution/history coverage to preflight failure. An explicit partial-coverage run must be labeled partial and must not masquerade as the complete requested benchmark.
- Do not expand momentum's configured universe with securities discovered in later disclosures. The storage dataset can contain a union of symbols; strategy eligibility must remain independent and point-in-time correct.

## 6. Required Benchmark

Run a new persisted suite with `buy_and_hold,momentum,congressional` for **January 1, 2026 through November 1, 2026 inclusive**, using completed exchange sessions only. Preserve previous runs and reports; use new dataset, snapshot, and suite identifiers. If this period is not yet fully available when implementing, report the blocker rather than silently shortening the requested benchmark or inventing data.

Use these explicit settings:

| Setting | Required value |
|---|---|
| Initial capital | 100,000 per strategy |
| VOO baseline | Buy-and-hold VOO, up to 100% exposure |
| Momentum universe | VOO, QQQ, NVDA, TSLA, AAPL |
| Momentum moving averages | 20-session short / 50-session long |
| Momentum rebalance | Weekly |
| Momentum position cap | 20%, maximum five positions |
| Congressional member/owners | Pelosi `P000197`, all five owner categories |
| Congressional allocation | Capped equal targets, 20% per position, maximum five positions |
| Maximum total exposure | 100%; full allocation is not required |
| Unallocated capital | Cash |
| Fees / adverse slippage | Zero fees / 5 basis points |
| Dividends | Cash; disclosed ex-date credit approximation, no reinvestment |
| Missing prices | Fail preflight by default |

If more than five congressional candidates are eligible, define and document a deterministic, point-in-time selection/tie-break rule and audit excluded candidates. Do not rank using future returns.

- Fetch at least 51 preceding completed sessions for momentum warmup; warmup creates no trades or dividend entitlements. Preserve the existing provider adjustment-horizon safeguards.
- Use a checked-in benchmark configuration that can express strategy-specific universes/settings, extending shared suite configuration only if needed. Do not force the congressional universe into momentum's five candidates.
- Use the normal persisted queue and one existing worker, with bounded waiting. A timeout must report outstanding experiment IDs without canceling jobs or launching another worker.
- Persist the requested congressional leg even when blocked by insufficient verified publication evidence, identity ambiguity, or missing prices. Complete the price-only legs where possible. Never silently omit congressional, fabricate disclosures, or label an empty eligible set as successful zero-return performance.
- Generate the report from persisted results with dataset/snapshot/configuration hashes, code revision, source/parser versions, actual session coverage, owner scope, exposure, costs, returns, drawdown, Sharpe, fills, matched VOO excess return, and all material limitations.
- Include counts of discovered/parsed/quarantined/unverified/unsupported/amended/eligible/unmatched/copied records. Audit representative purchase, sale, amendment, and skipped records back to document pages and execution sessions.
- Reproduce financial results offline using frozen inputs. Reconcile baseline accounting under the same assumptions. Explain exposure-budget differences and fixed-universe selection bias; make no superiority or statistical-significance claims.
- Update validation documentation and provide a comparison deep link for the three requested legs. Capture a new comparison screenshot if tooling works; otherwise clearly report the capture limitation. The existing historical screenshot may remain labeled historical and must not be presented as the new three-strategy result.

## 7. Tests and CI Acceptance

Use synthetic PDFs/indexes and mocked HTTP responses in all automated tests. No public-source downloads, paid credentials, real disclosure fixtures, OCR service calls, or LLM calls in CI.

Cover multi-page and wrapped rows, repeated headers, owner codes and unknown owners, explicit/missing tickers, amount ranges, options/exercises, malformed or scanned PDFs, resource limits, incomplete acquisition, retry behavior, immutable collisions, and artifact checksum failures. Ensure parse failures cannot silently reduce declared coverage.

Cover duplicate retrieval, distinct economically identical transactions, unstable row ordering, amendment identity conflicts, historical revision timing, and no double-copy after restart. Test rejection of filing-only publication evidence and premarket/after-close/weekend/date-only availability boundaries.

Cover all-owner filtering, cash starts, more than five eligible candidates, same-session conflicts, missing prices, no future-universe leakage, and blocked/partial/empty congressional outcomes.

Extend the synthetic PostgreSQL/Docker CI smoke workflow to exercise PDF/index ingestion → immutable snapshot → three-strategy queued suite → worker → persisted report → restart/offline verification. Clearly synthetic publication evidence may drive fixtures; it must never be represented as real source verification. Preserve the existing price-only coverage and failure-log artifacts.

Run backend tests, frontend production build, and PostgreSQL/Docker checks. Perform an authorized official-source smoke acquisition separately from CI when accessible, and inspect extracted rows against original PDFs. Report precisely which real-source and historical-publication properties were verified and which remain unknown.

## Completion and Scope Boundaries

Completion requires a working auditable House PDF acquisition/import workflow, deterministic parsing with explicit quarantine behavior, immutable provenance, integration with the existing simulator/dashboard, passing offline CI, and an attempted new three-strategy benchmark with truthful completed/blocked/partial outcomes. Lack of historical publication evidence must remain a visible limitation; it is not permission to weaken point-in-time correctness.

Do not add Quiver integration requirements, Senate scraping, brokerage execution, automatic trading, subscription purchases, LLM extraction, or unrelated dashboard redesigns. Keep this work in a separate follow-up PR and explain migration/accounting impacts and validation limits.
