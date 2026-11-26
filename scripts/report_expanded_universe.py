"""Publish audited results for the 30-ticker expanded universe."""
import json
from pathlib import Path


LABELS = {
    'momentum': 'Momentum (20/50 sessions)',
    'qwen-single': 'Qwen 3.5 9B single-agent',
    'qwen-multi': 'Qwen 3.5 9B multi-agent',
    'gemma-single': 'Gemma 4 12B single-agent',
    'gemma-multi': 'Gemma 4 12B multi-agent',
    'gpt55-single': 'GPT-5.5 single-agent',
    'gpt55-multi': 'GPT-5.5 multi-agent',
}

# Return and maximum drawdown in percent from the original report's 2026 table.
TEN_TICKER_RESULTS = {
    'momentum': (-6.30, 11.74),
    'qwen-single': (26.52, 15.51),
    'qwen-multi': (1.81, 11.26),
    'gemma-single': (11.13, 11.46),
    'gemma-multi': (12.33, 16.67),
    'gpt55-single': (-4.56, 14.51),
    'gpt55-multi': (8.17, 18.26),
}
VOO_RETURN = 11.04
VOO_DRAWDOWN = 8.89


def discussion(results: dict[str, dict]) -> list[str]:
    lines = [
        '## Discussion',
        '',
        'The comparison pairs the same strategies over the 2026 window ending October 30. '
        'Return changes are in percentage points and use the percentages shown in the table. '
        '[Original 10-ticker results](benchmark-report.md#2026)',
        '',
        '| Strategy | 10-ticker return | 30-ticker return | Return change (pp) | 10-ticker max drawdown | 30-ticker max drawdown |',
        '| --- | ---: | ---: | ---: | ---: | ---: |',
    ]
    changes = {}
    for key, (previous_return, previous_drawdown) in TEN_TICKER_RESULTS.items():
        if key not in results:
            continue
        current_return = round(results[key]['total_return'] * 100, 2)
        current_drawdown = abs(results[key]['drawdown']) * 100
        changes[key] = current_return - previous_return
        lines.append(f'| {LABELS[key]} | {previous_return:+.2f}% | {current_return:+.2f}% | '
                     f'{changes[key]:+.2f} | {previous_drawdown:.2f}% | {current_drawdown:.2f}% |')

    agent_changes = [change for key, change in changes.items() if key != 'momentum']
    if agent_changes:
        improved = sum(change > 0 for change in agent_changes)
        lines.extend(['', f'Returns improved for {improved} of {len(agent_changes)} LLM strategies in the 30-ticker configuration. '
                      f'The shared VOO buy-and-hold baseline returned {VOO_RETURN:+.2f}%.'])
    if 'gpt55-multi' in changes:
        stats = results['gpt55-multi']
        previous_return, previous_drawdown = TEN_TICKER_RESULTS['gpt55-multi']
        lines.extend(['', f"GPT-5.5 multi-agent went from {previous_return:+.2f}% to {stats['total_return']:+.2%} in return "
                      f"and from {previous_drawdown:.2f}% to {abs(stats['drawdown']):.2%} in maximum drawdown. "
                      f"It validated {stats['accepted']} of {stats['scheduled']} decisions in the expanded run and "
                      f"averaged {stats['mean_exposure']:.1%} exposure."])
    lines.extend([
        '',
        'The 10-ticker portfolios could hold up to 10 positions at 20% per ticker. '
        'The 30-ticker portfolios could hold up to 20, with 20% caps for VOO and QQQ and 5% caps elsewhere. '
        'Some agents also ran with different context budgets and call timeouts. '
        'The results measure the combined configuration changes over one retrospectively selected window.',
        '',
    ])
    return lines


def conclusion(results: dict[str, dict]) -> list[str]:
    lines = ['## Conclusion', '']
    agents = {key: stats for key, stats in results.items() if key != 'momentum'}
    if agents:
        leader = max(agents, key=lambda key: agents[key]['total_return'])
        stats = agents[leader]
        lead = round(stats['total_return'] * 100, 2) - VOO_RETURN
        lines.extend([
            f"{LABELS[leader]} led the reported 30-ticker LLM strategies and finished {lead:+.2f} percentage points "
            f"relative to VOO buy and hold. Its maximum drawdown was {abs(stats['drawdown']):.2%}, "
            f"versus {VOO_DRAWDOWN:.2f}% for VOO.",
            '',
        ])
    lines.extend([
        'This benchmark leaves the effect of universe size on its own unresolved. '
        'A follow-up would vary the ticker universe while holding allocation and inference settings fixed '
        'and repeat the comparison on a held-out period.',
        '',
    ])
    return lines


def publish(root: Path, reports: Path) -> None:
    output = reports.with_name(f'{reports.name}-30-tickers-20-positions')
    report = [
        '# 2026 expanded-universe benchmark', '',
        '**Does giving trading agents a larger ticker universe improve simulated trading performance in 2026?**', '',
        'This report presents the 30-ticker runs. Return and maximum drawdown measure performance. '
        'Average exposure shows the mean percentage of portfolio equity invested at each trading-session close. '
        'Comparisons with the original benchmark reflect changes in both the universe and allocation rules. '
        '[Original benchmark report](benchmark-report.md#2026)', '',
        '## Method', '',
        'Price-only simulations started with $100,000 on January 1, 2026, and ran through the October 30 trading session. '
        'Agents made weekly decisions using completed bars and traded at the next eligible open. '
        'Each decision screened all 30 tickers and shortlisted up to 10 entries.', '',
        'VOO and QQQ could each reach 20% of portfolio equity because each ETF already spreads exposure across many underlying companies. '
        'All other tickers were capped at 5% each. Portfolios could hold up to 20 positions with 100% maximum total exposure.', '',
        'The Yahoo Finance dataset `yahoo-expanded-2026-30-v1` has 51 warm-up sessions per symbol and no missing market sessions. '
        'The universe includes Rocket Lab (RKLB), Palantir (PLTR), and Coinbase (COIN). '
        'The universe was selected retrospectively, and agents received real ticker symbols and dates.', '',
        'ETHA underwent a one-for-three reverse split on October 6. The simulator applies the split to share quantities at the open '
        'and carries fractional shares under its usual accounting convention. '
        '[Nasdaq corporate action notice](https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-713)', '',
        '## Performance', '',
        'The passive baseline reuses the original 2026 VOO buy-and-hold experiment. [Original benchmark report](benchmark-report.md#2026)', '',
        '| Strategy | Return | Final equity | Max drawdown | Avg. exposure | Fills | Validated weeks | Experiment |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |',
        f'| VOO buy and hold | {VOO_RETURN:+.2f}% | $111,038.44 | {VOO_DRAWDOWN:.2f}% | 99.7% | 1 | — | `157861d6-8a27-4459-bd03-66013269e233` |',
    ]
    details = []
    results = {}
    runs = {key: [(output / key, None)] for key in LABELS}
    for context_dir in sorted(output.glob('context-*')):
        tokens = int(context_dir.name.removeprefix('context-'))
        for key in ('qwen-single', 'gemma-single'):
            folder = context_dir / key
            runs[key].extend((candidate, tokens) for candidate in [folder, *sorted(folder.glob('repeat-*'))]
                             if (candidate / '2026-audit.json').is_file())
    for key, candidates in runs.items():
        completed = [(folder, tokens) for folder, tokens in candidates if (folder / '2026-audit.json').is_file()]
        # The experiment ID is written once, while an audit can be regenerated.
        folder, tokens = max(completed, key=lambda run: (run[0] / '2026.id').stat().st_mtime_ns,
                             default=candidates[0])
        label = LABELS[key]
        path = folder / '2026-audit.json'
        id_path = folder / '2026.id'
        if not path.exists():
            if key == 'qwen-single' or id_path.exists():
                identifier = f'`{json.loads(id_path.read_text())}`' if id_path.exists() else '—'
                status = 'Pending audit' if id_path.exists() else 'Awaiting measured run'
                report.append(f'| {label} | {status} | — | — | — | — | — | {identifier} |')
            continue

        stats = json.loads(path.read_text())
        results[key] = stats
        if tokens is not None:
            timeout = stats.get('call_timeout')
            settings = f', {timeout:g}s call timeout' if timeout is not None else ''
            label = f'{label} ({tokens:,} context tokens{settings})'
        validated = '—' if key == 'momentum' else f"{stats['accepted']}/{stats['scheduled']}"
        report.append(f"| {label} | {stats['total_return']:+.2%} | ${stats['equity']:,.2f} | "
                      f"{abs(stats['drawdown']):.2%} | {stats['mean_exposure']:.1%} | {stats['fills']} | "
                      f"{validated} | `{stats['id']}` |")
        added = ', '.join(ticker for ticker in ('RKLB', 'PLTR', 'COIN') if ticker in stats['traded_tickers']) or 'none'
        errors = ', '.join(f'{code} ({count})' for code, count in sorted(stats['errors'].items())) or 'none'
        blocked = ', '.join(f'{reason} ({count})' for reason, count in stats['allocation_rejections'].items()) or 'none'
        usage = ', '.join(f'{count:,} {kind.replace("_", " ")}' for kind, count in stats['usage'].items()) or 'unavailable'
        details.extend([
            f'### {label}', '',
            f"Peak holdings were {stats['peak_holdings']}. "
            f"There were {stats['sessions_with_above_cap_holdings']} closes with holdings above their weight caps. "
            f'Allocation-related order rejections were {blocked}. Tickers traded among RKLB, PLTR, and COIN were {added}.', '',
        ])
        if key == 'momentum':
            details.extend(['Momentum used weekly 20/50-session moving-average signals and capped equal-weight targets.', ''])
        else:
            details.extend([f"The run recorded {stats['calls']} model calls, {sum(stats['skipped'].values())} skipped weeks, "
            f"and {stats['mean_week_seconds']:.1f} seconds per scheduled decision on average. "
            f'Recorded inference errors were {errors}. Reported token usage was {usage}.', ''])
        if 'billing' in stats:
            smoke = json.loads((folder / 'smoke-audit.json').read_text())['billing']
            measured = stats['billing']
            spent = smoke['priced_usd'] + measured['priced_usd']
            reserved = smoke['spent_or_reserved_usd'] + measured['spent_or_reserved_usd']
            campaign_cap = smoke['spent_or_reserved_usd'] + measured['limit_usd']
            details.extend([
                f'GPT-5.5 priced usage was ${spent:.4f} across smoke and measured runs. '
                f'Spend plus unsettled reservations was ${reserved:.4f} of the ${campaign_cap:.2f} campaign cap. '
                f"The cap limited {len(stats['budget_blocked_weeks'])} measured weeks. "
                f"[API pricing]({measured['pricing']['source']})", '',
            ])
    if results:
        report.extend(['', *discussion(results), *conclusion(results),
                       '## Appendix: Portfolio and inference audit', '', *details])
    path = root / 'docs/benchmark-report-2026-expanded-universe.md'
    staged = path.with_suffix('.staged')
    staged.write_text('\n'.join(report).rstrip() + '\n')
    staged.replace(path)
