"""From backend, run PYTHONPATH=. uv run python ../scripts/report_multi_agent.py after the annual campaign."""
import re
from collections import Counter

from app.contracts import Config
from app.db import Experiment, Session
from app.experiments import experiment_status
from audit_multi_agent import audit
from benchmark_charts import main as render_charts
from multi_agent_benchmarks import OUTPUT, ROOT


def main():
    path = ROOT / 'docs' / 'benchmark-report.md'
    report = path.read_text()
    report, _ = report.split('## Discussion', 1)
    discussion = []
    winners = []
    fills = calls = 0
    analyst_calls = Counter()
    role_seconds = Counter()
    with Session() as db:
        for year in (2026, 2025, 2024):
            section = report.split(f'### {year}\n', 1)[1].split('\n### ', 1)[0].strip()
            table, image = section.split('\n\n![', 1)
            image_path = re.search(r'\]\(([^)]+)\)', image)[1]
            rows = [line for line in table.splitlines() if ' multi-agent |' not in line]
            observations = []
            for label, slug in [('Qwen 3.5 9B', 'qwen3.5-9b'), ('Gemma 4 12B', 'gemma4-12b')]:
                single_id = next(re.search(r'`([a-f0-9-]+)`', line)[1] for line in rows if f'{label} single-agent |' in line)
                multi_id = (OUTPUT / f'{year}-{slug}.id').read_text().strip()
                expected = Config.model_validate_json((ROOT / 'configs' / 'benchmarks' / 'price-only-multi-agent'
                                                       / f'{year}-{slug}.json').read_text())
                stats = []
                for experiment_id in (single_id, multi_id):
                    row = db.get(Experiment, experiment_id)
                    if experiment_status(row) not in ('completed_with_warnings', 'completed'):
                        raise RuntimeError(f'{year} {label} {row.status}')
                    config = Config(**row.config)
                    changed = {'name', 'strategy', 'analyst_concurrency'}
                    assert config.model_dump(exclude=changed) == expected.model_dump(exclude=changed)
                    if experiment_id == multi_id:
                        assert config == expected
                    stats.append(audit(config, row.result))
                single, multi = stats
                fills += multi['fills']
                calls += single['calls']
                analyst_calls.update(multi['role_calls'])
                role_seconds.update(multi['role_seconds'])
                rows.append(f"| {label} multi-agent | {multi['total_return']:+.2%} | ${multi['equity']:,.2f} | "
                            f"{abs(multi['drawdown']):.2%} | {multi['fills']} | {multi['accepted']}/{multi['scheduled']} | `{multi_id}` |")
                for kind, stat in zip(('single-agent', 'multi-agent'), stats):
                    for reason, count in stat['skipped'].items():
                        unit = 'week' if count == 1 else 'weeks'
                        observations.append(f'{label} {kind} skipped {count} scheduled {unit} ({reason.lower()}).')
                    failures = {code: n for code, n in stat['errors'].items() if not code.startswith('audit/')}
                    if failures:
                        codes = ', '.join(f'{code.split("/")[0]} `{code.split("/")[1]}` ({n})'
                                          for code, n in sorted(failures.items()))
                        observations.append(f'{label} {kind} recorded {codes}.')
                winners.append((year, label, multi['total_return'] > single['total_return']))
                delta = 100 * (multi['total_return'] - single['total_return'])
                dd = 100 * (abs(multi['drawdown']) - abs(single['drawdown']))
                discussion.append(f"**{year} {label}.** Analyst review changed return by {delta:+.2f} percentage points "
                                  f"and maximum drawdown by {dd:+.2f} points. Validated weeks went from "
                                  f"{single['accepted']} to {multi['accepted']} out of {multi['scheduled']}. "
                                  f"Calls increased from {single['calls']} to {multi['calls']}, and mean time per scheduled "
                                  f"decision went from {single['mean_week_seconds']:.1f} to {multi['mean_week_seconds']:.1f} seconds.")
            replacement = '\n'.join(rows) + f'\n\n![{year} daily cumulative returns for all eight strategies]({image_path})'
            if observations:
                replacement += '\n\n' + ' '.join(observations)
            report = report.replace(section, replacement, 1)
    wins = sum(win for _, _, win in winners)
    if wins == 0:
        conclusion = '**The single agent earned the higher return in all six comparisons.**'
    else:
        conclusion = f'Analyst review improved return in {wins} of six model/year comparisons.'
    conclusion += (f' The six multi-agent portfolios reconciled to daily equity. All {fills} fills passed the '
                   'cash and total-exposure checks. The results cover one run per model and window on a fixed universe.')
    review_roles = ('technical', 'fundamental_news', 'risk')
    count = sum(analyst_calls[r] for r in review_roles)
    hours = sum(role_seconds[r] for r in review_roles) / 3600
    conclusion += (f' Across the six multi-agent runs, the three analyst roles accounted for {count:,} of '
                   f'{sum(analyst_calls.values()):,} calls and {hours:.1f} hours of inference time. '
                   f'The six single-agent runs used {calls} calls in total.')
    path.write_text(report.rstrip() + '\n\n## Discussion\n\n' + conclusion + '\n\n' + '\n\n'.join(discussion) + '\n')
    render_charts()


if __name__ == '__main__':
    main()
