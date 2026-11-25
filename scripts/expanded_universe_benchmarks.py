"""Run the 2026 expanded-universe benchmarks in order from backend/."""
import argparse
from collections import Counter
import fcntl
import json
from pathlib import Path

from app.contracts import Config
from app.db import Experiment, Session
from app.experiments import create_experiment
from app.openai_budget import NANOS_PER_USD, RequestBudget
from app.worker import execute
from audit_multi_agent import audit, average_exposure
from gpt55_benchmarks import FINISHED, save, summarize
from report_expanded_universe import publish


ROOT = Path(__file__).resolve().parents[1]
CONFIGS = ROOT / 'configs/benchmarks/2026-expanded-universe'
OUTPUT = ROOT / 'reports/2026-expanded-universe'
RUNS = ('qwen-single', 'qwen-multi', 'gemma-multi', 'gpt55-single', 'gemma-single')


def run(config: Config, folder: Path, stage: str) -> dict:
    folder.mkdir(exist_ok=True, parents=True)
    id_path = folder / f'{stage}.id'
    if id_path.exists():
        identifier = json.loads(id_path.read_text())
    else:
        identifier = create_experiment(config).id
        save(id_path, identifier)
    with Session() as db:
        row = db.get(Experiment, identifier)
        if row is None or Config.model_validate(row.config) != config:
            raise ValueError(f'Configuration mismatch for {folder.name} {stage}')
        finished = row.status in FINISHED
        if not finished:
            if row.status not in {'created', 'running', 'failed'}:
                raise RuntimeError(f'{identifier} is {row.status}')
            row.status = 'running'
            db.commit()
    print(f'{folder.name} {stage} {identifier}', flush=True)
    if not finished:
        execute(identifier)
    with Session() as db:
        row = db.get(Experiment, identifier)
        if row.status not in FINISHED:
            raise RuntimeError(f'{identifier} {row.status} {row.error}')
        stats = (summarize(row, config, stage) if config.api_budget_usd is not None
                 else dict(id=identifier, status=row.status, **audit(config, row.result)))
        equity = row.result['equity']
        stats['mean_exposure'] = average_exposure(equity)
        stats['peak_holdings'] = max(sum(q > 0 for q in day['positions'].values()) for day in equity)
        stats['sessions_with_above_cap_holdings'] = sum(
            any(q * day['prices'][ticker] / day['equity'] > config.position_weight_limit(ticker) + 1e-9
                for ticker, q in day['positions'].items() if q > 0)
            for day in equity)
        stats['traded_tickers'] = sorted({fill['ticker'] for fill in row.result['trades']})
        stats['allocation_rejections'] = dict(Counter(
            order['reason'] for order in row.result['orders']
            if order['reason'] in {'Position or exposure limit', 'Maximum positions', 'Reduction no longer needed at open'}))
        usage = Counter()
        for decision in row.result['decisions']:
            for attempt in decision['trace']:
                for key, value in attempt.get('usage', {}).items():
                    if key in {'input_tokens', 'cached_input_tokens', 'output_tokens'} and value is not None:
                        usage[key] += value
        stats['usage'] = dict(usage)
        if config.api_budget_usd is not None:
            stats['budget_blocked_weeks'] = [decision['date'] for decision in row.result['decisions']
                                             if any(attempt.get('error_code') == 'api_budget_exhausted'
                                                    for attempt in decision['trace'])]
    save(folder / f'{stage}-audit.json', stats)
    print(f"{folder.name} {stage} validated {stats['accepted']}/{stats['scheduled']}", flush=True)
    return stats


def run_campaign(through: str, config_dir: Path = CONFIGS, *, momentum: bool = False) -> None:
    keys = RUNS[:RUNS.index(through) + 1]
    if momentum:
        keys += ('momentum',)
    configs = {key: Config.model_validate_json((config_dir / f'{key}.json').read_text())
               for key in keys}
    reference = configs['qwen-single']
    max_positions = reference.max_positions
    if any((config.universe, config.dataset, config.max_positions) != (reference.universe, reference.dataset, max_positions)
           for config in configs.values()):
        raise ValueError('Selected benchmark configurations must share a universe, dataset, and position cap')
    ticker_suffix = '' if len(reference.universe) == 27 else f'-{len(reference.universe)}-tickers'
    position_suffix = '' if max_positions == 15 else f'-{max_positions}-positions'
    output = OUTPUT.with_name(f'{OUTPUT.name}{ticker_suffix}{position_suffix}')
    for key, config in configs.items():
        folder = output / key
        if key == 'momentum':
            run(config, folder, '2026')
            publish(ROOT, OUTPUT)
            continue
        smoke_changes = dict(name=f'Smoke {config.name}', end=config.start.replace(day=20))
        if config.api_budget_usd is not None:
            smoke_changes['api_budget_usd'] = min(1, config.api_budget_usd)
        smoke = run(config.model_copy(update=smoke_changes), folder, 'smoke')
        if not smoke['accepted']:
            raise RuntimeError(f'{key} smoke validated no decisions')
        if config.api_budget_usd is not None:
            with Session() as db:
                entries = RequestBudget(Session, smoke['id'], config.api_budget_usd).entries(db)
                remaining = int(config.api_budget_usd * NANOS_PER_USD) - sum(r.payload['held_nanos'] for r in entries)
            if remaining <= 0:
                raise RuntimeError('GPT-5.5 budget exhausted during smoke')
            config = config.model_copy(update={'api_budget_usd': remaining / NANOS_PER_USD})
        run(config, folder, '2026')
        publish(ROOT, OUTPUT)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--through', choices=RUNS, required=True)
    parser.add_argument('--config-dir', type=Path, default=CONFIGS)
    parser.add_argument('--momentum', action='store_true', help='Run the momentum baseline after the multi-agent runs')
    parser.add_argument('--wait-for-current', action='store_true', help='Wait for the active campaign before continuing')
    args = parser.parse_args()
    if args.momentum and args.through != 'gemma-multi':
        parser.error('--momentum requires --through gemma-multi')
    OUTPUT.mkdir(exist_ok=True, parents=True)
    with (OUTPUT / 'campaign.lock').open('a') as lock:
        try:
            if args.wait_for_current:
                print('Waiting for the active campaign lock before continuing.', flush=True)
            fcntl.flock(lock, fcntl.LOCK_EX if args.wait_for_current else fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('The expanded-universe benchmark is already running.') from None
        run_campaign(args.through, args.config_dir, momentum=args.momentum)


if __name__ == '__main__':
    main()
