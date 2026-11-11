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
