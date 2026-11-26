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

| Strategy | Return | Final equity | Max drawdown | Avg. exposure | Fills | Validated weeks | Experiment |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| VOO buy and hold | +11.04% | $111,038.44 | 8.89% | 99.7% | 1 | — | `157861d6-8a27-4459-bd03-66013269e233` |
| Momentum (20/50 sessions) | +4.86% | $104,859.98 | 13.01% | 82.1% | 775 | — | `7aa388dd-8994-4312-8aaf-57d508f68258` |
| Qwen 3.5 9B single-agent (16,384 context tokens, 180s call timeout) | +10.69% | $110,685.14 | 11.01% | 70.1% | 212 | 40/43 | `6fb4647c-734e-40fc-b9a6-3f825ff02410` |
| Qwen 3.5 9B multi-agent | +6.90% | $106,898.70 | 9.47% | 54.6% | 233 | 42/43 | `5efa9521-545b-4e6c-b160-c88756591508` |
| Gemma 4 12B single-agent (16,384 context tokens) | +9.49% | $109,488.49 | 15.01% | 80.0% | 108 | 41/43 | `9d34bbba-6703-4efa-95a6-c36741dd7d0d` |
| Gemma 4 12B multi-agent | +6.12% | $106,119.37 | 9.31% | 47.5% | 242 | 43/43 | `dd0d5097-e169-4f1e-b16c-787ee05fed11` |
| GPT-5.5 single-agent | +10.76% | $110,764.36 | 15.70% | 87.9% | 50 | 43/43 | `d471d2fd-5b91-4831-810c-a7ef04713984` |
| GPT-5.5 multi-agent | +21.41% | $121,410.10 | 10.20% | 88.7% | 61 | 43/43 | `fee3c8d2-ecfc-46a8-ae2a-345ab3598bf5` |

## Discussion

The comparison pairs the same strategies over the 2026 window ending October 30. Return changes are in percentage points and use the percentages shown in the table. [Original 10-ticker results](benchmark-report.md#2026)

| Strategy | 10-ticker return | 30-ticker return | Return change (pp) | 10-ticker max drawdown | 30-ticker max drawdown |
| --- | ---: | ---: | ---: | ---: | ---: |
| Momentum (20/50 sessions) | -6.30% | +4.86% | +11.16 | 11.74% | 13.01% |
| Qwen 3.5 9B single-agent | +26.52% | +10.69% | -15.83 | 15.51% | 11.01% |
| Qwen 3.5 9B multi-agent | +1.81% | +6.90% | +5.09 | 11.26% | 9.47% |
| Gemma 4 12B single-agent | +11.13% | +9.49% | -1.64 | 11.46% | 15.01% |
| Gemma 4 12B multi-agent | +12.33% | +6.12% | -6.21 | 16.67% | 9.31% |
| GPT-5.5 single-agent | -4.56% | +10.76% | +15.32 | 14.51% | 15.70% |
| GPT-5.5 multi-agent | +8.17% | +21.41% | +13.24 | 18.26% | 10.20% |

Returns improved for 3 of 6 LLM strategies in the 30-ticker configuration. The shared VOO buy-and-hold baseline returned +11.04%.

GPT-5.5 multi-agent went from +8.17% to +21.41% in return and from 18.26% to 10.20% in maximum drawdown. It validated 43 of 43 decisions in the expanded run and averaged 88.7% exposure.

The 10-ticker portfolios could hold up to 10 positions at 20% per ticker. The 30-ticker portfolios could hold up to 20, with 20% caps for VOO and QQQ and 5% caps elsewhere. Some agents also ran with different context budgets and call timeouts. The results measure the combined configuration changes over one retrospectively selected window.

## Conclusion

GPT-5.5 multi-agent led the reported 30-ticker LLM strategies and finished +10.37 percentage points relative to VOO buy and hold. Its maximum drawdown was 10.20%, versus 8.89% for VOO.

This benchmark leaves the effect of universe size on its own unresolved. A follow-up would vary the ticker universe while holding allocation and inference settings fixed and repeat the comparison on a held-out period.

## Appendix: Portfolio and inference audit

### Momentum (20/50 sessions)

Peak holdings were 20. There were 208 closes with holdings above their weight caps. Allocation-related order rejections were none. Tickers traded among RKLB, PLTR, and COIN were RKLB, PLTR, COIN.

Momentum used weekly 20/50-session moving-average signals and capped equal-weight targets.

### Qwen 3.5 9B single-agent (16,384 context tokens, 180s call timeout)

Peak holdings were 20. There were 187 closes with holdings above their weight caps. Allocation-related order rejections were Position or exposure limit (11), Maximum positions (8), Reduction no longer needed at open (2). Tickers traded among RKLB, PLTR, and COIN were RKLB, PLTR, COIN.

The run recorded 56 model calls, 0 skipped weeks, and 59.7 seconds per scheduled decision on average. Recorded inference errors were audit/duplicate_signal_symbol (3), portfolio/duplicate_signal_symbol (3), portfolio/invalid_model_json (9). Reported token usage was 448,407 input tokens, 74,908 output tokens.

### Qwen 3.5 9B multi-agent

Peak holdings were 18. There were 169 closes with holdings above their weight caps. Allocation-related order rejections were none. Tickers traded among RKLB, PLTR, and COIN were RKLB, PLTR, COIN.

The run recorded 174 model calls, 0 skipped weeks, and 96.1 seconds per scheduled decision on average. Recorded inference errors were audit/duplicate_signal_symbol (1), portfolio/duplicate_signal_symbol (1). Reported token usage was 855,101 input tokens, 113,759 output tokens.

### Gemma 4 12B single-agent (16,384 context tokens)

Peak holdings were 20. There were 204 closes with holdings above their weight caps. Allocation-related order rejections were Reduction no longer needed at open (4), Maximum positions (41). Tickers traded among RKLB, PLTR, and COIN were RKLB, PLTR, COIN.

The run recorded 80 model calls, 0 skipped weeks, and 68.5 seconds per scheduled decision on average. Recorded inference errors were audit/input_context_limit (2), portfolio/call_timeout (1), portfolio/input_context_limit (2). Reported token usage was 823,238 input tokens, 44,223 output tokens.

### Gemma 4 12B multi-agent

Peak holdings were 17. There were 172 closes with holdings above their weight caps. Allocation-related order rejections were none. Tickers traded among RKLB, PLTR, and COIN were RKLB, PLTR, COIN.

The run recorded 172 model calls, 0 skipped weeks, and 83.0 seconds per scheduled decision on average. Recorded inference errors were none. Reported token usage was 772,815 input tokens, 75,641 output tokens.

### GPT-5.5 single-agent

Peak holdings were 20. There were 208 closes with holdings above their weight caps. Allocation-related order rejections were Maximum positions (24). Tickers traded among RKLB, PLTR, and COIN were RKLB, PLTR.

The run recorded 43 model calls, 0 skipped weeks, and 6.4 seconds per scheduled decision on average. Recorded inference errors were none. Reported token usage was 278,660 input tokens, 19,815 output tokens, 2,816 cached input tokens.

GPT-5.5 priced usage was $2.0651 across smoke and measured runs. Spend plus unsettled reservations was $2.0651 of the $5.00 campaign cap. The cap limited 0 measured weeks. [API pricing](https://developers.openai.com/api/docs/models/gpt-5.5)

### GPT-5.5 multi-agent

Peak holdings were 20. There were 208 closes with holdings above their weight caps. Allocation-related order rejections were Maximum positions (20). Tickers traded among RKLB, PLTR, and COIN were RKLB, PLTR.

The run recorded 172 model calls, 0 skipped weeks, and 22.9 seconds per scheduled decision on average. Recorded inference errors were none. Reported token usage was 781,329 input tokens, 84,052 output tokens, 3,584 cached input tokens.

GPT-5.5 priced usage was $6.7523 across smoke and measured runs. Spend plus unsettled reservations was $6.7523 of the $10.00 campaign cap. The cap limited 0 measured weeks. [API pricing](https://developers.openai.com/api/docs/models/gpt-5.5)
