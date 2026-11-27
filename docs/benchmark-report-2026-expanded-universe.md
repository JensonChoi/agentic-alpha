# 2026 expanded-universe benchmark

**Does giving trading agents a larger ticker universe improve simulated trading performance in 2026?**

This report presents the 30-ticker runs. Return and maximum drawdown measure performance. Average exposure shows the mean percentage of portfolio equity invested at each trading-session close. Comparisons with the original benchmark reflect changes in both the universe and allocation rules. [Original benchmark report](benchmark-report.md#2026)

## Method

Price-only simulations started with $100,000 on January 1, 2026, and ran through the October 30 trading session. Agents made weekly decisions using completed bars and traded at the next eligible open. Each decision screened all 30 tickers and shortlisted up to 10 entries.

VOO and QQQ could each reach 20% of portfolio equity because each ETF already spreads exposure across many underlying companies. All other tickers were capped at 5% each. Portfolios could hold up to 20 positions with 100% maximum total exposure.

The Yahoo Finance dataset `yahoo-expanded-2026-30-v1` has 51 warm-up sessions per symbol and no missing market sessions. The universe includes Rocket Lab (RKLB), Palantir (PLTR), and Coinbase (COIN). The universe was selected retrospectively, and agents received real ticker symbols and dates.

ETHA underwent a one-for-three reverse split on October 6. The simulator applies the split to share quantities at the open and carries fractional shares under its usual accounting convention. [Nasdaq corporate action notice](https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-713)

## Performance

The passive baseline reuses the original 2026 VOO buy-and-hold experiment. [Original benchmark report](benchmark-report.md#2026)

Rows marked as means give the arithmetic average across completed runs for each metric, including each run’s maximum drawdown and validated week count. The Qwen single-agent group uses 16,384 context tokens and a 180-second call timeout. Each multi-agent mean includes its original 8,192-token, 90-second run and completed repeats at the new settings. The Gemma single-agent mean includes its 16,384-token, 90-second reference run and completed repeats at 180 seconds.

| Strategy | Return | Final equity | Max drawdown | Avg. exposure | Fills | Validated weeks | Experiment |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| VOO buy and hold | +11.04% | $111,038.44 | 8.89% | 99.7% | 1 | — | `157861d6-8a27-4459-bd03-66013269e233` |
| Momentum (20/50 sessions) | +4.86% | $104,859.98 | 13.01% | 82.1% | 775 | — | `7aa388dd-8994-4312-8aaf-57d508f68258` |
| Qwen 3.5 9B single-agent (mean of 3 runs) | +6.00% | $106,003.34 | 11.40% | 71.0% | 220.0 | 37.7/43 | 3 experiments |
| Qwen 3.5 9B multi-agent (mean of 4 runs) | +6.77% | $106,767.63 | 10.32% | 58.6% | 265.2 | 42.5/43 | 4 experiments |
| Gemma 4 12B single-agent (mean of 4 runs) | +10.03% | $110,034.40 | 15.08% | 76.1% | 100.0 | 42.2/43 | 4 experiments |
| Gemma 4 12B multi-agent (mean of 4 runs) | +7.73% | $107,725.35 | 8.83% | 44.1% | 233.5 | 43.0/43 | 4 experiments |
| GPT-5.5 single-agent | +10.76% | $110,764.36 | 15.70% | 87.9% | 50 | 43/43 | `d471d2fd-5b91-4831-810c-a7ef04713984` |
| GPT-5.5 multi-agent | +21.41% | $121,410.10 | 10.20% | 88.7% | 61 | 43/43 | `fee3c8d2-ecfc-46a8-ae2a-345ab3598bf5` |

## Discussion

The comparison pairs the same strategies over the 2026 window ending October 30. The 30-ticker column uses the overall means from the performance table where repeats are available. Return changes are in percentage points and use the percentages shown in the table. [Original 10-ticker results](benchmark-report.md#2026)

| Strategy | 10-ticker return | 30-ticker return | Return change (pp) | 10-ticker max drawdown | 30-ticker max drawdown |
| --- | ---: | ---: | ---: | ---: | ---: |
| Momentum (20/50 sessions) | -6.30% | +4.86% | +11.16 | 11.74% | 13.01% |
| Qwen 3.5 9B single-agent | +26.52% | +6.00% | -20.52 | 15.51% | 11.40% |
| Qwen 3.5 9B multi-agent | +1.81% | +6.77% | +4.96 | 11.26% | 10.32% |
| Gemma 4 12B single-agent | +11.13% | +10.03% | -1.10 | 11.46% | 15.08% |
| Gemma 4 12B multi-agent | +12.33% | +7.73% | -4.60 | 16.67% | 8.83% |
| GPT-5.5 single-agent | -4.56% | +10.76% | +15.32 | 14.51% | 15.70% |
| GPT-5.5 multi-agent | +8.17% | +21.41% | +13.24 | 18.26% | 10.20% |

Returns improved for 3 of 6 LLM strategies in the 30-ticker configuration. The shared VOO buy-and-hold baseline returned +11.04%.

GPT-5.5 multi-agent went from +8.17% to +21.41% in return and from 18.26% to 10.20% in maximum drawdown. It validated 43 of 43 decisions in the expanded run and averaged 88.7% exposure.

### Local repeatability

The local repeats use 16,384 context tokens and 180 seconds per call, with seed 42 and temperature 0.0. Return ranges summarize variation across runs on the same market data.

| Strategy | Runs | Mean return | Return range | Mean max drawdown | Mean exposure | Validated weeks | Runs above VOO |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen 3.5 9B single-agent | 3 | +6.00% | -1.18% to +10.69% | 11.40% | 71.0% | 113/129 | 0/3 |
| Qwen 3.5 9B multi-agent | 3 | +6.72% | +1.34% to +14.47% | 10.61% | 59.9% | 128/129 | 1/3 |
| Gemma 4 12B single-agent | 3 | +10.22% | +8.31% to +11.72% | 15.10% | 74.9% | 128/129 | 1/3 |
| Gemma 4 12B multi-agent | 3 | +8.26% | +6.87% to +9.11% | 8.66% | 42.9% | 129/129 | 0/3 |

Gemma 4 12B multi-agent had the narrowest return range at 2.24 percentage points. Qwen 3.5 9B multi-agent had the widest at 13.12 points. Most weekly decisions validated across the local repeats, even where returns varied widely.

The 10-ticker portfolios could hold up to 10 positions at 20% per ticker. The 30-ticker portfolios could hold up to 20, with 20% caps for VOO and QQQ and 5% caps elsewhere. Some agents also ran with different context budgets and call timeouts. The results measure the combined configuration changes over one retrospectively selected window.

## Conclusion

GPT-5.5 multi-agent led the reported 30-ticker LLM strategies and finished +10.37 percentage points relative to VOO buy and hold. Its maximum drawdown was 10.20%, versus 8.89% for VOO.

4 of 4 local strategies averaged below VOO in the matched-settings repeats. The repeated local runs measure sensitivity to rerunning the models on one market window.

GPT-5.5 multi-agent was measured once in the expanded universe.

This benchmark leaves the effect of universe size on its own unresolved. A follow-up would vary the ticker universe while holding allocation and inference settings fixed and repeat the comparison on a held-out period.

## Appendix: Portfolio and inference audit

### Momentum (20/50 sessions)

Peak holdings were 20. There were 208 closes with holdings above their weight caps. Allocation-related order rejections were none. Tickers traded among RKLB, PLTR, and COIN were RKLB, PLTR, COIN.

Momentum used weekly 20/50-session moving-average signals and capped equal-weight targets.

### Qwen 3.5 9B single-agent

The averages include 3 completed experiments. Individual results are recorded in the experiment audits for `6fb4647c-734e-40fc-b9a6-3f825ff02410`, `72492740-d875-4fae-b140-8a52b515739e`, `452c51aa-3bc3-49d5-8ce9-09a872d60f60`.

### Qwen 3.5 9B multi-agent

The averages include 4 completed experiments. Individual results are recorded in the experiment audits for `5efa9521-545b-4e6c-b160-c88756591508`, `2be927d0-69e5-4f8e-928c-c20799531f52`, `5d5e002e-e485-40f9-bf4f-b5ec32b34e7c`, `389ba1a3-dfc4-4940-840a-d0696b4b2e85`.

Across 3 runs at 16,384 context tokens and 180 seconds per call, mean return was +6.72%, mean maximum drawdown was 10.61%, mean exposure was 59.9%, and the mean validated week count was 42.7 of 43.

### Gemma 4 12B single-agent

The averages include 4 completed experiments. Individual results are recorded in the experiment audits for `9d34bbba-6703-4efa-95a6-c36741dd7d0d`, `0aeea2d8-eae7-449c-bfbe-f1809dd501a0`, `dc810124-537e-4c39-a860-a4c0bdec04d0`, `81543aa8-a2eb-4189-8d13-80098cb87fed`.

Across 3 runs at 16,384 context tokens and 180 seconds per call, mean return was +10.22%, mean maximum drawdown was 15.10%, mean exposure was 74.9%, and the mean validated week count was 42.7 of 43.

### Gemma 4 12B multi-agent

The averages include 4 completed experiments. Individual results are recorded in the experiment audits for `dd0d5097-e169-4f1e-b16c-787ee05fed11`, `5ce8bb0d-3728-4157-a6f7-b4172ef0cabc`, `f85574ee-3879-4eff-9aaa-26717753fd0b`, `59544ce6-ac63-4776-8a5e-087327aa2fce`.

Across 3 runs at 16,384 context tokens and 180 seconds per call, mean return was +8.26%, mean maximum drawdown was 8.66%, mean exposure was 42.9%, and the mean validated week count was 43.0 of 43.

### GPT-5.5 single-agent

Peak holdings were 20. There were 208 closes with holdings above their weight caps. Allocation-related order rejections were Maximum positions (24). Tickers traded among RKLB, PLTR, and COIN were RKLB, PLTR.

The run recorded 43 model calls, 0 skipped weeks, and 6.4 seconds per scheduled decision on average. Recorded inference errors were none. Reported token usage was 278,660 input tokens, 19,815 output tokens, 2,816 cached input tokens.

GPT-5.5 priced usage was $2.0651 across smoke and measured runs. Spend plus unsettled reservations was $2.0651 of the $5.00 campaign cap. The cap limited 0 measured weeks. [API pricing](https://developers.openai.com/api/docs/models/gpt-5.5)

### GPT-5.5 multi-agent

Peak holdings were 20. There were 208 closes with holdings above their weight caps. Allocation-related order rejections were Maximum positions (20). Tickers traded among RKLB, PLTR, and COIN were RKLB, PLTR.

The run recorded 172 model calls, 0 skipped weeks, and 22.9 seconds per scheduled decision on average. Recorded inference errors were none. Reported token usage was 781,329 input tokens, 84,052 output tokens, 3,584 cached input tokens.

GPT-5.5 priced usage was $6.7523 across smoke and measured runs. Spend plus unsettled reservations was $6.7523 of the $10.00 campaign cap. The cap limited 0 measured weeks. [API pricing](https://developers.openai.com/api/docs/models/gpt-5.5)
