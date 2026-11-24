"""Run one explicitly selected GPT-5.5 campaign stage from backend/."""
import argparse
import fcntl
import json
from collections import Counter
from pathlib import Path

from app.contracts import Config
from app.db import Experiment, Session
from app.experiments import create_experiment, experiment_status, inputs
from app.inference import GPT55_SNAPSHOT, settings
from app.openai_budget import NANOS_PER_USD, PRICING, RequestBudget, charges
from app.provenance import digest, implementation_hash
from app.worker import execute
from audit_multi_agent import audit

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = ROOT / 'configs/benchmarks/gpt-5-5-single-agent'
OUTPUT = ROOT / 'reports/gpt-5-5-single-agent'
WEEKS = {'smoke': 3, '2026': 43, '2025': 52, '2024': 52}
YEARS = ('2026', '2025', '2024')
FINISHED = {'completed', 'completed_with_warnings'}


def configurations():
    configs = {year: Config.model_validate_json((CONFIGS / f'{year}.json').read_text()) for year in YEARS}
    annual = configs['2026']
    configs['smoke'] = annual.model_copy(update={'name': 'Smoke GPT-5.5 price-only single-agent',
                                                'api_budget_usd': 2, 'end': annual.start.replace(day=20)})
    return configs


def save(path, value):
    staged = path.with_suffix('.tmp')
    staged.write_text(json.dumps(value, indent=2) + '\n')
    staged.replace(path)


def price_attempts(attempts):
    totals, missing, stops = Counter(), Counter(), Counter()
    priced_nanos = incomplete = retries = 0
    for attempt in attempts:
        retries += attempt.get('attempt', 1) > 1
        usage = attempt.get('usage', {})
        for key in PRICING['usd_per_million']:
            if usage.get(key) is None:
                missing[key] += 1
            else:
                totals[key] += usage[key]
        incomplete += any(usage.get(key) is None for key in PRICING['usd_per_million'])
        priced_nanos += charges(usage)
        if attempt.get('stop_reason'):
            stops[attempt['stop_reason']] += 1
    return dict(requests=len(attempts), retries=retries, reported_tokens=dict(totals), missing_usage_calls=dict(missing),
                incomplete_calls=incomplete, finish_reasons=dict(stops), priced_usd=priced_nanos / NANOS_PER_USD, pricing=PRICING)


def usage_summary(decisions):
    attempts = [t for d in decisions for t in d['trace'] if t['role'] != 'audit'
                and t['status'] != 'skipped' and t.get('error_stage') != 'request']
    return price_attempts(attempts)


def check_parity(config, baseline):
    excluded = {'model', 'provider', 'name', 'api_budget_usd'}
    if (config.api_budget_usd != 5 or config.model != GPT55_SNAPSHOT or config.provider != 'openai' or
            config.model_dump(exclude=excluded) != baseline.model_dump(exclude=excluded)):
        raise ValueError('GPT configuration differs from its local single-agent baseline')


def campaign_protocol(configs):
    sources = json.loads((CONFIGS / 'sources.json').read_text())
    with Session() as db:
        for year in YEARS:
            config = configs[year]
            for experiment_id in sources[year]['baselines'].values():
                row = db.get(Experiment, experiment_id)
                if row is None or experiment_status(row) not in FINISHED:
                    raise ValueError(f'Missing completed baseline {experiment_id}')
                check_parity(config, Config(**row.config))
            _, manifest = inputs(config)
            if manifest.get('content_sha256', manifest['sha256']) != sources[year]['dataset_hash']:
                raise ValueError(f'Dataset differs from {year} baseline')
    return dict(implementation=implementation_hash(), sources=sources,
                configs={stage: config.model_dump(mode='json') for stage, config in configs.items()})


def summarize(row, config, stage):
    if experiment_status(row) not in FINISHED:
        raise RuntimeError(f'{row.id} is {row.status}')
    stats = audit(config, row.result)
    for order in row.result['orders']:
        # At the window boundary the engine records pending signals as undated unfilled orders.
        if order.get('date') is None:
            last = row.result['decisions'][-1]
            if last['trace'][-1]['status'] != 'completed' or order['signal'] not in last['signals']:
                raise ValueError('Unfilled order lacks a validated decision')
    if stats['scheduled'] != WEEKS[stage]:
        raise ValueError(f'Unexpected decision count for {stage}')
    billing = usage_summary(row.result['decisions'])
    budget = RequestBudget(Session, row.id, config.api_budget_usd)
    with Session() as db:
        entries = budget.entries(db)
        ledger = price_attempts([r.payload for r in entries])
        # Include calls made before an interruption that never reached a daily checkpoint.
        ledger['uncheckpointed_requests'] = ledger['requests'] - billing['requests']
        if ledger['uncheckpointed_requests'] < 0:
            raise ValueError('Missing durable API reservations')
        ledger['finish_reasons'] = billing['finish_reasons']
        ledger['limit_usd'] = config.api_budget_usd
        ledger['spent_or_reserved_usd'] = sum(r.payload['held_nanos'] for r in entries) / NANOS_PER_USD
    billing = ledger
    stats['evaluation_attempts'] = stats['calls']
    stats['calls'] = billing['requests']
    summary = dict(id=row.id, status=experiment_status(row), snapshot=config.model, **stats, billing=billing)
    if stage == 'smoke':
        summary['projected_measured_usd'] = billing['priced_usd'] * sum(WEEKS[y] for y in YEARS) / WEEKS['smoke']
        summary['weeks'] = [dict(date=d['date'], status=d['trace'][-1]['status'],
                                 elapsed_seconds=d['trace'][-1].get('elapsed_seconds', 0),
                                 billing=usage_summary([d])) for d in row.result['decisions']]
    return summary


def run_window(folder, stage, config, *, execute_pending=True):
    id_path = folder / f'{stage}.id'
    if id_path.exists():
        experiment_id = json.loads(id_path.read_text())
    elif execute_pending:
        experiment_id = create_experiment(config).id
        save(id_path, experiment_id)
    else:
        raise ValueError(f'Missing {stage} experiment')
    with Session() as db:
        row = db.get(Experiment, experiment_id)
        if row is None or Config(**row.config) != config:
            raise ValueError(f'Experiment mismatch for {stage}')
        if experiment_status(row) not in FINISHED:
            if not execute_pending or row.status not in {'created', 'running', 'failed'}:
                raise RuntimeError(f'{experiment_id} is {row.status}')
            row.status = 'running'
            db.commit()
            execute(experiment_id)
            db.refresh(row)
        result = summarize(row, config, stage)
    save(folder / f'{stage}-audit.json', result)
    return result


def campaign(stage, reviewed_smoke):
    configs = configurations()
    protocol = campaign_protocol(configs)
    folder = OUTPUT / digest(protocol)
    folder.mkdir(exist_ok=True)
    save(folder / 'protocol.json', protocol)
    if stage in {'smoke', 'annual'}:
        base, headers = settings('openai')
        if base != 'https://api.openai.com/v1' or 'Authorization' not in headers:
            raise ValueError('Set backend OPENAI_API_KEY and use the standard OpenAI endpoint')
    smoke = run_window(folder, 'smoke', configs['smoke'], execute_pending=stage == 'smoke')
    if not smoke['accepted']:
        raise ValueError(f'Smoke produced no validated decisions. Inspect {folder}/smoke-audit.json')
    if stage == 'smoke':
        print(json.dumps(smoke, indent=2))
        print(folder)
        return
    review_path = folder / 'review.json'
    if stage == 'annual' and reviewed_smoke == smoke['id']:
        save(review_path, dict(smoke_id=reviewed_smoke, protocol=digest(protocol)))
    if (not review_path.exists() or json.loads(review_path.read_text()) !=
            dict(smoke_id=smoke['id'], protocol=digest(protocol)) or
            reviewed_smoke not in (None, smoke['id'])):
        raise ValueError('Inspect smoke-audit.json, then pass --reviewed-smoke ID to annual')
    summaries = {}
    for year in YEARS:
        summaries[year] = run_window(folder, year, configs[year], execute_pending=stage == 'annual')
        print(year, summaries[year]['id'], summaries[year]['status'], flush=True)
    if stage == 'publish':
        from report_gpt55 import publish
        publish(summaries, protocol['sources'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('smoke', 'annual', 'publish'))
    parser.add_argument('--reviewed-smoke', metavar='ID')
    args = parser.parse_args()
    OUTPUT.mkdir(exist_ok=True, parents=True)
    with (OUTPUT / 'campaign.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Another GPT-5.5 campaign command is active') from None
        campaign(args.stage, args.reviewed_smoke)


if __name__ == '__main__':
    main()
