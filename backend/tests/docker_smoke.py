"""Container-only smoke checks using synthetic data and the real worker."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, inspect, select, text

from app.db import Base, Dataset, engine


def request(method, path, **kwargs):
    response = httpx.request(method, 'http://frontend' + path, timeout=10, **kwargs)
    response.raise_for_status()
    return response


def ready():
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            assert request('GET', '/api/health').json()['simulation_only'] is True
            assert '<div id="root">' in request('GET', '/compare').text
            return
        except (httpx.HTTPError, AssertionError):
            time.sleep(1)
    raise RuntimeError('Frontend/API did not become ready within 60 seconds')


def migration():
    assert engine.dialect.name == 'postgresql'
    with engine.connect() as db:
        assert db.scalar(text('SELECT version_num FROM alembic_version')) == '002'
    # Separate database emulates revision 001 before the two additive tables existed.
    name = 'smoke_legacy_' + uuid4().hex
    with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as db:
        db.exec_driver_sql(f'CREATE DATABASE {name}')
    url = engine.url.set(database=name)
    legacy = create_engine(url)
    tables = [t for t in Base.metadata.sorted_tables
              if t.name not in ('disclosure_snapshots', 'benchmark_suites')]
    Base.metadata.create_all(legacy, tables=tables)
    manifest = {'provenance': 'synthetic legacy smoke fixture', 'price_basis': 'raw'}
    with legacy.begin() as db:
        db.execute(Dataset.__table__.insert().values(id='legacy', manifest=manifest))
        db.exec_driver_sql('CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)')
        db.exec_driver_sql("INSERT INTO alembic_version VALUES ('001')")
    for _ in range(2):
        subprocess.run(['alembic', 'upgrade', 'head'], check=True, timeout=30,
                       env={**os.environ, 'DATABASE_URL': url.render_as_string(hide_password=False)})
    assert {'disclosure_snapshots', 'benchmark_suites'} <= set(inspect(legacy).get_table_names())
    with legacy.connect() as db:
        assert db.scalar(select(Dataset.manifest).where(Dataset.id == 'legacy')) == manifest
        assert db.scalar(text('SELECT version_num FROM alembic_version')) == '002'
    legacy.dispose()
    print('Fresh migration and legacy 001 → 002 upgrade/repeat passed', flush=True)


def wait_for(identifier):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        row = request('GET', f'/api/experiments/{identifier}').json()
        assert row['status'] not in ('failed', 'partial', 'canceled'), row
        if row['status'] == 'completed':
            result = request('GET', f'/api/experiments/{identifier}/export').json()['results']
            assert result['equity'] and result['trades'] and result['metrics']
            return result
        time.sleep(1)
    raise RuntimeError(f'Worker timed out: {identifier}')


def run():
    ready()
    migration()
    datasets = request('GET', '/api/datasets').json()
    assert any(d['id'] == 'demo' and d['synthetic'] for d in datasets)
    row = request('POST', '/api/experiments', json={
        'name': 'Docker API smoke', 'strategy': 'buy_and_hold',
        'end': '2024-04-12',
    }).json()
    request('POST', f'/api/experiments/{row["id"]}/run')
    api_result = wait_for(row['id'])
    from datetime import date
    from app.house import ingest, correct_snapshot
    from app.disclosures import load_snapshot
    from tests.house_fixtures import bundle
    source = bundle(Path('/data/synthetic-house-input'))
    ingest('synthetic-house', 'P000197', date(2024,1,1), date(2024,12,31), '/data/house-artifacts', 'SYNTHETIC Docker fixture; not real source evidence', source)
    records, _ = load_snapshot('synthetic-house')
    correct_snapshot('synthetic-house', 'synthetic-reviewed', [dict(source_id=records[0]['source_id'], reviewer='Synthetic test author', evidence='SYNTHETIC publication fixture', publication_basis='synthetic_fixture', changes=dict(availability_quality='verified_date', published_date='2024-04-01', publication_evidence='SYNTHETIC test-only publication evidence'))], 'SYNTHETIC Docker fixture')
    subprocess.run([
        sys.executable, '-m', 'app.cli', 'benchmark', '--dataset', 'demo',
        '--end', '2024-04-12', '--strategies', 'buy_and_hold,momentum,congressional', '--disclosure-snapshot', 'synthetic-reviewed',
        '--wait', '120', '--output', '/data/smoke-report.md',
    ], check=True, timeout=150)
    suites = request('GET', '/api/benchmark-suites').json()
    assert len(suites) == 1 and len(suites[0]['members']) == 3
    results = {row['id']: api_result}
    for member in suites[0]['members']:
        results[member['experiment_id']] = wait_for(member['experiment_id'])
    assert 'Outcome: completed' in Path('/data/smoke-report.md').read_text()
    Path('/data/smoke-state.json').write_text(json.dumps({'suites': suites, 'results': results}))
    print('API queue, worker, PDF ingestion, persisted three-strategy suite and report passed', flush=True)


def verify():
    ready()
    state = json.loads(Path('/data/smoke-state.json').read_text())
    from app.disclosures import load_snapshot
    from app.experiments import inputs
    from app.engine import simulate
    from app.contracts import Config
    import asyncio
    load_snapshot('synthetic-reviewed')
    assert request('GET', '/api/benchmark-suites').json() == state['suites']
    for identifier, expected in state['results'].items():
        assert wait_for(identifier) == expected
        config = Config(**request('GET', f'/api/experiments/{identifier}').json()['config'])
        frame, manifest = inputs(config)
        repeated = asyncio.run(simulate(config, frame, manifest))
        assert repeated['metrics'] == expected['metrics']
        assert repeated['trades'] == expected['trades']
    print('Completed results and suite unchanged after API/worker restart', flush=True)


if __name__ == '__main__':
    {'run': run, 'verify': verify}[sys.argv[1]]()
