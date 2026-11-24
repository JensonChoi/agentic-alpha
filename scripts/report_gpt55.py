"""Publish audited GPT-5.5 results alongside the original single-agent baselines."""
import re

from benchmark_charts import DOCS, render_report

HEADING = '## GPT-5.5 single-agent comparison'


def updated_report(report, summaries, sources):
    report = report.split('\n' + HEADING + '\n', 1)[0].rstrip()
    paragraphs = [HEADING]
    for year, stats in summaries.items():
        section = report.split(f'### {year}\n', 1)[1].split('\n\n![', 1)[0]
        rows = [line for line in section.splitlines() if not line.startswith('| GPT-5.5 single-agent |')]
        billing = stats['billing']
        multi_rows = [line for line in rows if line.startswith('| GPT-5.5 multi-agent |')]
        rows = [line for line in rows if line not in multi_rows]
        if len([line for line in rows if line.startswith('| ')]) != 9:
            raise ValueError(f'Expected the eight established strategies in {year}')
        rows.append(f"| GPT-5.5 single-agent | {stats['total_return']:+.2%} | ${stats['equity']:,.2f} | "
                    f"{abs(stats['drawdown']):.2%} | {stats['fills']} | {stats['accepted']}/{stats['scheduled']} | `{stats['id']}` |")
        rows.extend(multi_rows)
        report = report.replace(section, '\n'.join(rows), 1)
        count = 'ten' if multi_rows else 'nine'
        report = re.sub(rf'!\[{year} daily cumulative returns for all (eight|nine|ten) strategies\]',
                        f'![{year} daily cumulative returns for all {count} strategies]', report)
        comparisons = []
        for label, experiment_id in sources[year]['baselines'].items():
            line, = (r for r in rows if r.startswith(f'| {label} |') and f'`{experiment_id}`' in r)
            cols = [c.strip() for c in line.strip('|').split('|')]
            base_return, base_dd = (float(cols[i].rstrip('%')) for i in (1, 3))
            accepted, scheduled = map(int, cols[5].split('/'))
            if scheduled != stats['scheduled']:
                raise ValueError(f'Schedule mismatch for {year} {label}')
            comparisons.append(f"Against {label}, return differed by {100 * stats['total_return'] - base_return:+.2f} "
                               f"percentage points and maximum drawdown by {100 * abs(stats['drawdown']) - base_dd:+.2f} "
                               f"points. GPT validated {stats['accepted']}/{scheduled} weeks versus {accepted}/{scheduled}.")
        tokens = billing['reported_tokens']
        counts = ', '.join(f"{tokens.get(k, 'unreported')} {label}" for k, label in
                           [('input_tokens', 'input'), ('cached_input_tokens', 'cached input'), ('output_tokens', 'output')])
        spend = f"Estimated API spend was ${billing['priced_usd']:.4f}"
        if billing['incomplete_calls']:
            spend += f" for priced usage only ({billing['incomplete_calls']} calls had incomplete usage)"
        skipped = sum(stats['skipped'].values())
        errors = ', '.join(f'{key} ({value})' for key, value in sorted(stats['errors'].items())) or 'none'
        paragraphs.append(f"**{year}.** " + ' '.join(comparisons) +
                          f" {billing['requests']} API requests included {billing['retries']} retries, with {counts} tokens. "
                          f"Mean latency per scheduled decision was {stats['mean_week_seconds']:.1f} seconds. {spend}. "
                          f"Skipped weeks totaled {skipped}. Recorded errors were {errors}.")
    pricing = summaries['2026']['billing']['pricing']
    rates = pricing['usd_per_million']
    paragraphs.extend([
        f"Estimates use standard API rates dated {pricing['as_of']}, in USD per million tokens "
        f"(${rates['input_tokens']} uncached input, ${rates['cached_input_tokens']} cached input and "
        f"${rates['output_tokens']} output). Cached input is included in the input count. "
        f"[OpenAI pricing]({pricing['source']})",
        "The pinned `gpt-5.5-2026-04-23` snapshot used reasoning effort `none` and JSON mode. "
        "Temperature and seed were omitted. Decisions used simulator evidence and tools. "
        "Each measured year had a $5 API budget. Its December 1, 2025 model knowledge cutoff overlaps 2024 and most of 2025. The 2026 decisions fall after "
        "the cutoff, but decisions before the April 23 snapshot release are retrospective. These comparisons "
        "cover one simulated run per model and window on the fixed ten-ticker universe. "
        "[OpenAI model documentation](https://developers.openai.com/api/docs/models/gpt-5.5)"
    ])
    return report + '\n\n' + '\n\n'.join(paragraphs) + '\n'


def publish(summaries, sources):
    report_path = DOCS / 'benchmark-report.md'
    report = updated_report(report_path.read_text(), summaries, sources)
    charts = render_report(report)
    for year, svg in charts.items():
        (DOCS / 'images' / f'benchmark-returns-{year}.svg').write_text(svg)
    report_path.write_text(report)
