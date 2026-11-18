import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app import main,worker,data
from app.db import Base,Experiment
@pytest.fixture
def client(monkeypatch,tmp_path):
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    with engine.connect() as connection:
        connection.exec_driver_sql('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine); session=sessionmaker(engine,expire_on_commit=False)
    for module in (main,worker,data): monkeypatch.setattr(module,'Session',session)
    monkeypatch.setattr(data,'ROOT',tmp_path)
    monkeypatch.setattr(main,'engine',engine)
    with TestClient(main.app) as client: yield client

def test_full_flow(client):
    c=client.post('/api/experiments',json={'strategy':'buy_and_hold'});assert c.status_code==201
    id=c.json()['id'];assert client.post(f'/api/experiments/{id}/run').status_code==200
    worker.execute(id)
    r=client.get(f'/api/experiments/{id}/export').json()
    assert r['experiment']['status']=='completed',r
    assert len(r['results']['trades'])==1
    assert client.post(f'/api/experiments/{id}/run').status_code==409
    assert client.get(f'/api/portfolios/{id}').json()['simulated']

def test_auth(client,monkeypatch):
    monkeypatch.setenv('API_TOKEN','test-token')
    assert client.get('/api/experiments').status_code==401
    assert client.get('/api/experiments',headers={'Authorization':'Bearer test-token'}).status_code==200

def test_invalid_config(client):
    assert client.post('/api/experiments',json={'short_window':60,'long_window':50}).status_code==422

@pytest.mark.parametrize('status', ['created', 'completed', 'failed', 'partial', 'canceled'])
def test_delete_experiment_and_dependents(client, status):
    from app.db import Dataset
    from sqlalchemy import select
    experiment_id = client.post('/api/experiments', json={'strategy': 'buy_and_hold'}).json()['id']
    other_id = client.post('/api/experiments', json={}).json()['id']
    worker.execute(experiment_id)
    with main.Session() as db:
        db.get(Experiment, experiment_id).status = status
        db.commit()
    response = client.delete(f'/api/experiments/{experiment_id}')
    assert response.status_code == 200
    assert response.json()['deleted'] is True
    assert client.get(f'/api/experiments/{experiment_id}').status_code == 404
    assert client.get(f'/api/portfolios/{experiment_id}').status_code == 404
    assert client.delete(f'/api/experiments/{experiment_id}').status_code == 404
    assert client.get(f'/api/experiments/{other_id}').status_code == 200
    with main.Session() as db:
        assert db.get(Dataset, 'demo') is not None
        for table in Base.metadata.sorted_tables:
            if 'experiment_id' in table.c:
                assert db.execute(select(table).where(table.c.experiment_id == experiment_id)).first() is None
    worker.execute(experiment_id)  # A late worker must not resurrect a deleted run.

@pytest.mark.parametrize('status', ['queued', 'running', 'waiting'])
def test_delete_requires_canceling_active_experiment(client, status):
    experiment_id = client.post('/api/experiments', json={}).json()['id']
    with main.Session() as db:
        db.get(Experiment, experiment_id).status = status
        db.commit()
    assert client.delete(f'/api/experiments/{experiment_id}').status_code == 409
    assert client.post(f'/api/experiments/{experiment_id}/cancel').status_code == 200
    assert client.delete(f'/api/experiments/{experiment_id}').status_code == 200

def test_delete_requires_auth(client, monkeypatch):
    experiment_id = client.post('/api/experiments', json={}).json()['id']
    monkeypatch.setenv('API_TOKEN', 'test-token')
    assert client.delete(f'/api/experiments/{experiment_id}').status_code == 401
    assert client.delete(f'/api/experiments/{experiment_id}', headers={'Authorization': 'Bearer test-token'}).status_code == 200

def test_worker_stops_when_canceled_experiment_deleted(client, monkeypatch):
    experiment_id = client.post('/api/experiments', json={}).json()['id']
    async def interrupted(config, frame, manifest, checkpoint, resume):
        client.post(f'/api/experiments/{experiment_id}/cancel')
        assert client.delete(f'/api/experiments/{experiment_id}').status_code == 200
        assert checkpoint(.5, {}) is False
        return {'canceled': True}
    monkeypatch.setattr(worker, 'simulate', interrupted)
    worker.execute(experiment_id)
    assert client.get(f'/api/experiments/{experiment_id}').status_code == 404

def test_llm_audit_persistence(client, monkeypatch):
    from app.inference import Envelope
    from app.db import ToolCallRow, RecommendationRow
    from sqlalchemy import select
    from test_engine import fixture
    frame,_=fixture()
    data.register('llm-fixture',frame,'Synthetic rising-price integration fixture',True)
    calls={}
    async def fake(config,role,context,*args):
        key=context['snapshot']['cutoff']; calls[key]=calls.get(key,0)+1
        if calls[key]==1:
            return Envelope(tools=[{'name':'cash'}]), {'usage':{'input_tokens':20,'output_tokens':10}}
        return Envelope(final=dict(signals=[],synthesis='No trade with missing evidence',agreement='',disagreement='',evidence_refs=['snapshot'])), {'usage':{'input_tokens':20,'output_tokens':10}}
    async def models(*args): return ['mock']
    monkeypatch.setattr('app.inference.call',fake)
    monkeypatch.setattr('app.main.models',models)
    response=client.post('/api/experiments',json=dict(strategy='single_agent',dataset='llm-fixture',model='mock',universe=['VOO','AAPL'],start='2024-04-01',end='2024-04-05',rebalance='daily'))
    assert response.status_code==201
    identifier=response.json()['id']
    assert client.post(f'/api/experiments/{identifier}/run').status_code==200
    worker.execute(identifier)
    exported=client.get(f'/api/experiments/{identifier}/export').json()
    assert exported['experiment']['status']=='completed'
    assert exported['results']['decisions']
    with main.Session() as db:
        assert db.scalar(select(ToolCallRow).where(ToolCallRow.experiment_id==identifier))
        assert db.scalar(select(RecommendationRow).where(RecommendationRow.experiment_id==identifier))


def test_evidence_import_rejects_bad_availability(client):
    payload=dict(id='bad-evidence',provenance='Synthetic fixture',synthetic=True,bars=[dict(date='2024-04-01',ticker='VOO',open=100,high=101,low=99,close=100,volume=10)],agent_evidence=[dict(id='news',ticker='VOO',kind='news',published_at='2024-04-01T12:00:00Z',available_at='2024-03-01T12:00:00Z',provenance='fixture')])
    assert client.post('/api/datasets/import',json=payload).status_code==422


def test_full_window_with_failed_decisions_is_completed_with_warnings(client, monkeypatch):
    simulate = worker.simulate

    async def simulation_with_warning(*args):
        result = await simulate(*args)
        result['failures'] = 1
        return result

    monkeypatch.setattr(worker, 'simulate', simulation_with_warning)
    response = client.post('/api/experiments', json={'strategy': 'buy_and_hold'})
    identifier = response.json()['id']
    worker.execute(identifier)

    def assert_completed_with_warning():
        exported = client.get(f'/api/experiments/{identifier}/export').json()
        experiment = exported['experiment']
        assert experiment['status'] == 'completed_with_warnings'
        assert experiment['progress'] == 1
        assert experiment['decision_failures'] == 1
        assert client.post(f'/api/experiments/{identifier}/run').status_code == 409

    assert_completed_with_warning()
    with main.Session() as db:
        row = db.get(Experiment, identifier)
        assert row.status == 'completed_with_warnings'
        row.status = 'partial'
        db.commit()

    assert_completed_with_warning()
    with main.Session() as db:
        row = db.get(Experiment, identifier)
        row.progress = 0.5
        db.commit()
    assert client.get(f'/api/experiments/{identifier}').json()['status'] == 'partial'
