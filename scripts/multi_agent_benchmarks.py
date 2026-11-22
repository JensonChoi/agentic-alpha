"""From backend: PYTHONPATH=. uv run python ../scripts/multi_agent_benchmarks.py smoke|annual."""
import argparse
import fcntl
import json
from pathlib import Path

import httpx

from audit_multi_agent import audit
from app.contracts import Config
from app.db import Experiment, Session
from app.experiments import create_experiment, inputs, validate
from app.inference import settings
from app.worker import execute

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'reports' / 'multi-agent-benchmarks'


def run(config, label):
    path = OUTPUT / f'{label}-{config.model.replace(":", "-")}'
    config_path = Path(f'{path}-config.json')
    config_path.write_text(config.model_dump_json(indent=2) + '\n')
    id_path = Path(f'{path}.id')
    if id_path.exists():
        experiment_id = id_path.read_text().strip()
    else:
        frame, manifest = inputs(config)
        validate(config, frame, manifest)
        experiment_id = create_experiment(config).id
        id_path.write_text(experiment_id + '\n')
    with Session() as db:
        row = db.get(Experiment, experiment_id)
        if Config.model_validate(row.config) != config:
            raise ValueError(f'Configuration mismatch for {experiment_id}')
        finished = row.status in ('completed', 'completed_with_warnings')
        if not finished:
            if row.status not in ('created', 'queued', 'running'):
                raise RuntimeError(f'{experiment_id} is {row.status}')
            row.status = 'running'
            db.commit()
    print(label, config.model, experiment_id, flush=True)
    if not finished:
        execute(experiment_id)
    with Session() as db:
        row = db.get(Experiment, experiment_id)
        if row.status not in ('completed', 'completed_with_warnings'):
            raise RuntimeError(f'{experiment_id} {row.status} {row.error}')
        summary = dict(id=row.id, status=row.status, **audit(config, row.result))
        Path(f'{path}-audit.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary), flush=True)
        if label == 'smoke' and not summary['accepted']:
            raise RuntimeError(f'Smoke gate failed for {config.model}')
    if not finished:
        base, headers = settings('ollama')
        httpx.post(base + '/api/generate', headers=headers, json=dict(model=config.model, keep_alive=0),
                   timeout=60).raise_for_status()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=('smoke', 'annual'))
    args = parser.parse_args()
    OUTPUT.mkdir(exist_ok=True, parents=True)
    with (OUTPUT / 'campaign.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('The local benchmark campaign is already running.') from None
        campaign(args.stage)


def campaign(stage):
    configs = ROOT / 'configs' / 'benchmarks' / 'price-only-multi-agent'
    measured = []
    for year in (2026, 2025, 2024):
        for model in ('qwen3.5-9b', 'gemma4-12b'):
            config = Config.model_validate_json((configs / f'{year}-{model}.json').read_text())
            measured.append((str(year), config))
            if year == 2026:
                smoke = config.model_copy(update={'end': config.start.replace(day=20), 'name': f'Smoke {config.name}'})
                run(smoke, 'smoke')
    if stage == 'annual':
        for year, config in measured:
            run(config, year)


if __name__ == '__main__':
    main()
