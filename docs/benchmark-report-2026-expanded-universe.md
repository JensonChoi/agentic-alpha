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
| Qwen 3.5 9B single-agent | +17.45% | $117,451.78 | 12.84% | 82.9% | 196 | 34/43 | `8a84bf27-ed85-4f92-8916-523f307a7fac` |
| Qwen 3.5 9B multi-agent | +6.90% | $106,898.70 | 9.47% | 54.6% | 233 | 42/43 | `5efa9521-545b-4e6c-b160-c88756591508` |
| Gemma 4 12B single-agent | +10.49% | $110,492.50 | 14.72% | 82.5% | 103 | 32/43 | `376cc205-758f-49c1-a8e7-cac1f1967b43` |
| Gemma 4 12B multi-agent | +6.12% | $106,119.37 | 9.31% | 47.5% | 242 | 43/43 | `dd0d5097-e169-4f1e-b16c-787ee05fed11` |
| GPT-5.5 single-agent | +10.76% | $110,764.36 | 15.70% | 87.9% | 50 | 43/43 | `d471d2fd-5b91-4831-810c-a7ef04713984` |

## Portfolio and inference audit

### Momentum (20/50 sessions)

Peak holdings were 20. There were 208 closes with holdings above their weight caps. Allocation-related order rejections were none. Tickers traded among RKLB, PLTR, and COIN were RKLB, PLTR, COIN.

Momentum used weekly 20/50-session moving-average signals and capped equal-weight targets.

### Qwen 3.5 9B single-agent

Peak holdings were 20. There were 208 closes with holdings above their weight caps. Allocation-related order rejections were Reduction no longer needed at open (2), Maximum positions (36). Tickers traded among RKLB, PLTR, and COIN were RKLB, PLTR, COIN.

The run recorded 58 model calls, 0 skipped weeks, and 78.2 seconds per scheduled decision on average. Recorded inference errors were audit/call_timeout (3), audit/duplicate_signal_symbol (5), audit/invalid_model_json (1), portfolio/call_timeout (3), portfolio/duplicate_signal_symbol (5), portfolio/invalid_model_json (14). Reported token usage was 480,556 input tokens, 85,775 output tokens.

### Qwen 3.5 9B multi-agent

Peak holdings were 18. There were 169 closes with holdings above their weight caps. Allocation-related order rejections were none. Tickers traded among RKLB, PLTR, and COIN were RKLB, PLTR, COIN.

The run recorded 174 model calls, 0 skipped weeks, and 96.1 seconds per scheduled decision on average. Recorded inference errors were audit/duplicate_signal_symbol (1), portfolio/duplicate_signal_symbol (1). Reported token usage was 855,101 input tokens, 113,759 output tokens.

### Gemma 4 12B single-agent

Peak holdings were 20. There were 185 closes with holdings above their weight caps. Allocation-related order rejections were Maximum positions (8). Tickers traded among RKLB, PLTR, and COIN were RKLB, PLTR.

The run recorded 70 model calls, 0 skipped weeks, and 48.2 seconds per scheduled decision on average. Recorded inference errors were audit/duplicate_signal_symbol (1), audit/input_context_limit (10), portfolio/duplicate_signal_symbol (1), portfolio/input_context_limit (10). Reported token usage was 565,681 input tokens, 32,042 output tokens.

### Gemma 4 12B multi-agent

Peak holdings were 17. There were 172 closes with holdings above their weight caps. Allocation-related order rejections were none. Tickers traded among RKLB, PLTR, and COIN were RKLB, PLTR, COIN.

The run recorded 172 model calls, 0 skipped weeks, and 83.0 seconds per scheduled decision on average. Recorded inference errors were none. Reported token usage was 772,815 input tokens, 75,641 output tokens.

### GPT-5.5 single-agent

Peak holdings were 20. There were 208 closes with holdings above their weight caps. Allocation-related order rejections were Maximum positions (24). Tickers traded among RKLB, PLTR, and COIN were RKLB, PLTR.

The run recorded 43 model calls, 0 skipped weeks, and 6.4 seconds per scheduled decision on average. Recorded inference errors were none. Reported token usage was 278,660 input tokens, 19,815 output tokens, 2,816 cached input tokens.

GPT-5.5 priced usage was $2.0651 across smoke and measured runs. Spend plus unsettled reservations was $2.0651 of the $5.00 campaign cap. The cap limited 0 measured weeks. [API pricing](https://developers.openai.com/api/docs/models/gpt-5.5)
