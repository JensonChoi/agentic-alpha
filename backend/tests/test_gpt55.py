"""Offline GPT-5.5 adapter, spend limit, campaign and report regression tests."""
import json
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID
from xml.etree import ElementTree

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import inference
from app.data import sessions
from app.db import Base, Experiment
from app.openai_budget import GPT55_SNAPSHOT, RequestBudget, current_budget
from test_llm import setup

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import benchmark_charts
import gpt55_benchmarks as campaign
from report_gpt55 import updated_report


@pytest.fixture
def database(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path}/test.db')
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


async def test_pinned_requests_retries_and_persistent_cap(monkeypatch, database):
    config, context = setup(price_only=True)
    config.model, config.provider, config.thinking = GPT55_SNAPSHOT, 'openai', False
    config.api_budget_usd = 5
    with database.begin() as db:
        row = Experiment(config={})
        db.add(row)
    monkeypatch.setenv('ENABLE_CLOUD', 'true')
    monkeypatch.delenv('OPENAI_BASE_URL', raising=False)
    bodies = []

    async def post(self, url, json, **kwargs):
        bodies.append(json)
        first = len(bodies) == 1
        content = '{"final":{"signals":[],"synthesis":"Hold","agreement":"","disagreement":"","evidence_refs":["snapshot"]}}'
        data = dict(model=GPT55_SNAPSHOT, choices=[dict(message=dict(content='{' if first else content),
                                                        finish_reason='length' if first else 'stop')],
                    usage=dict(prompt_tokens=300, completion_tokens=90, prompt_tokens_details=dict(cached_tokens=100)))
        return httpx.Response(200, json=data, request=httpx.Request('POST', url))

    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    budget = RequestBudget(database, row.id, 5)
    token = current_budget.set(budget)
    try:
        _, trace = await inference.evaluate(config, context)
        assert trace[-1]['status'] == 'completed' and trace[-1]['actual_calls'] == 2
        assert trace[0]['stop_reason'] == 'length' and trace[0]['model'] == GPT55_SNAPSHOT
        assert bodies[1]['max_completion_tokens'] == 2 * bodies[0]['max_completion_tokens']
        assert bodies[0]['reasoning_effort'] == 'none' and bodies[0]['response_format'] == {'type': 'json_object'}
        assert not {'max_tokens', 'temperature', 'seed', 'tools'} & bodies[0].keys()
        assert 'JSON' in bodies[0]['messages'][0]['content']
        usage = campaign.usage_summary([dict(trace=trace)])
        assert usage['requests'] == 2 and usage['retries'] == 1
        assert usage['priced_usd'] == pytest.approx(2 * (200*5 + 100*.5 + 90*30) / 1e6)

        # An interrupted attempt retains its entire reservation after worker restart.
        while budget.reserve(bodies[0]) is not None:
            pass
        resumed = RequestBudget(database, row.id, 5)
        current_budget.set(resumed)
        _, trace = await inference.evaluate(config, context)
        assert trace[-1]['error_code'] == 'api_budget_exhausted' and len(bodies) == 2
        assert campaign.usage_summary([dict(trace=trace)])['requests'] == 0
        with database() as db:
            assert sum(r.payload['held_nanos'] for r in resumed.entries(db)) <= resumed.limit
    finally:
        current_budget.reset(token)


def test_partial_billing_and_zero():
    stats = campaign.usage_summary([dict(trace=[
        dict(role='portfolio', status='failed', usage={}),
        dict(role='portfolio', status='completed', usage=dict(input_tokens=0, cached_input_tokens=0, output_tokens=0)),
        dict(role='portfolio', status='completed', usage=dict(input_tokens=200, output_tokens=20)),
    ])])
    assert stats['requests'] == 3 and stats['incomplete_calls'] == 2
    assert stats['missing_usage_calls'] == dict(input_tokens=1, cached_input_tokens=2, output_tokens=1)
    assert stats['priced_usd'] == pytest.approx(20*30/1e6)
    assert stats['reported_tokens']['cached_input_tokens'] == 0


def test_configs_and_calendar():
    configs = campaign.configurations()
    for stage, config in configs.items():
        days = sessions(config.start, config.end)
        count = sum(d.isocalendar()[:2] != n.isocalendar()[:2] for d, n in
                    zip(days, list(days[1:]) + [days[-1] + timedelta(days=1)]))
        assert count == campaign.WEEKS[stage] and config.api_budget_usd == (2 if stage == 'smoke' else 5)
        assert config.model == GPT55_SNAPSHOT and config.thinking is False and config.price_only
        if stage != 'smoke':
            for slug in ('qwen3.5-9b', 'gemma4-12b'):
                source = campaign.CONFIGS.parent / 'price-only-multi-agent' / f'{stage}-{slug}.json'
                local = config.model_validate_json(source.read_text()).model_copy(update={'strategy': 'single_agent',
                                                                                       'analyst_concurrency': config.analyst_concurrency})
                campaign.check_parity(config, local)
                with pytest.raises(ValueError):
                    campaign.check_parity(config, local.model_copy(update={'max_model_calls': 1}))


def test_campaign_requires_review_and_orders_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(campaign, 'OUTPUT', tmp_path)
    monkeypatch.setattr(campaign, 'campaign_protocol', lambda configs: {'version': 1})
    monkeypatch.setattr(campaign, 'settings', lambda provider: ('https://api.openai.com/v1', {'Authorization': 'mock'}))
    calls = []

    def stub(folder, stage, config, execute_pending):
        calls.append((stage, execute_pending))
        return dict(id='fixture', accepted=1, status='completed_with_warnings')

    monkeypatch.setattr(campaign, 'run_window', stub)
    with pytest.raises(ValueError, match='reviewed-smoke'):
        campaign.campaign('annual', None)
    assert calls == [('smoke', False)]
    calls.clear()
    campaign.campaign('annual', 'fixture')
    assert calls == [('smoke', False), ('2026', True), ('2025', True), ('2024', True)]


def test_resume_reuses_experiment(monkeypatch, database, tmp_path):
    config = campaign.configurations()['2026']
    with database.begin() as db:
        row = Experiment(config=config.model_dump(mode='json'), status='running', result={'state': {'checkpoint': 1}})
        db.add(row)
    campaign.save(tmp_path / '2026.id', row.id)
    calls = []

    def resume(experiment_id):
        with database.begin() as db:
            experiment = db.get(Experiment, experiment_id)
            assert experiment.result['state']['checkpoint'] == 1
            experiment.status = 'completed_with_warnings'
        calls.append(experiment_id)

    monkeypatch.setattr(campaign, 'Session', database)
    monkeypatch.setattr(campaign, 'execute', resume)
    monkeypatch.setattr(campaign, 'summarize', lambda r, c, stage: dict(id=r.id, status=r.status))
    for _ in range(2):
        assert campaign.run_window(tmp_path, '2026', config)['status'] == 'completed_with_warnings'
    assert calls == [row.id]


def test_report_preserves_multi_agent_row_and_chart(monkeypatch):
    report = (benchmark_charts.DOCS / 'benchmark-report.md').read_text()
    report = '\n'.join(line for line in report.splitlines() if not line.startswith('| GPT-5.5 single-agent |'))
    sources = json.loads((campaign.CONFIGS / 'sources.json').read_text())
    billing = campaign.usage_summary([])
    summaries = {year: dict(id=str(UUID(int=int(year))), accepted=1, scheduled=campaign.WEEKS[year],
                            total_return=0, equity=100000, fills=0, drawdown=0, mean_week_seconds=0,
                            skipped={}, errors={}, billing=billing) for year in campaign.YEARS}
    updated = updated_report(report, summaries, sources)
    assert updated_report(updated, summaries, sources) == updated
    assert updated.count('| GPT-5.5 single-agent |') == 3 and 'Across all six comparisons' in updated

    class FixtureSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, model, experiment_id):
            year = next(y for y in campaign.YEARS if experiment_id in
                        updated.split(f'### {y}\n', 1)[1].split('\n!', 1)[0])
            return SimpleNamespace(config=dict(initial_capital=100000),
                                   result=dict(equity=[dict(date=f'{year}-01-02', equity=100000)]))

    monkeypatch.setattr(benchmark_charts, 'Session', FixtureSession)
    for text, count in ((report, 8), (updated, 9)):
        for year, svg in benchmark_charts.render_report(text).items():
            root = ElementTree.fromstring(svg)
            has_multi = year == 2026 and '| GPT-5.5 multi-agent |' in report
            assert len(root.findall('.//{*}polyline')) == count + has_multi
            assert ('GPT-5.5 multi-agent' in svg) == has_multi
            assert ('GPT-5.5 single-agent' in svg) == (count == 9)


@pytest.mark.parametrize('limit, expected_roles', [
    (10, ['technical', 'fundamental_news', 'risk', 'portfolio']),
    (0.00001, []),
])
async def test_multi_agent_roles_share_budget(monkeypatch, database, limit, expected_roles):
    config, context = setup(price_only=True)
    config = config.model_copy(update=dict(strategy='multi_agent', provider='openai', model=GPT55_SNAPSHOT,
                                           api_budget_usd=limit, thinking=False, analyst_concurrency=1))
    with database.begin() as db:
        row = Experiment(config={})
        db.add(row)
    monkeypatch.setenv('ENABLE_CLOUD', 'true')
    monkeypatch.delenv('OPENAI_BASE_URL', raising=False)
    roles = []

    async def post(self, url, **kwargs):
        prompt = kwargs['json']['messages'][0]['content']
        role = prompt.split('Role ', 1)[1].split('.', 1)[0]
        roles.append(role)
        if role == 'portfolio':
            output = dict(final=dict(signals=[], synthesis='Hold', agreement='', disagreement='', evidence_refs=['snapshot']))
        else:
            output = dict(analyst=dict(role=role, candidates_considered=[], findings=[], missing_inputs=['news'], concerns=[]))
        raw = dict(model=GPT55_SNAPSHOT, choices=[dict(message=dict(content=json.dumps(output)), finish_reason='stop')],
                   usage=dict(prompt_tokens=100, completion_tokens=20, prompt_tokens_details=dict(cached_tokens=0)))
        return httpx.Response(200, json=raw, request=httpx.Request('POST', url))

    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    budget = RequestBudget(database, row.id, limit)
    token = current_budget.set(budget)
    try:
        _, trace = await inference.evaluate(config, context)
    finally:
        current_budget.reset(token)
    assert roles == expected_roles
    with database() as db:
        assert len(budget.entries(db)) == len(expected_roles)
    if expected_roles:
        assert trace[-1]['status'] == 'completed'
    else:
        assert {t['error_code'] for t in trace[:-1]} == {'api_budget_exhausted'}
