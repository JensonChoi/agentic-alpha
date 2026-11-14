import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Depends, Header, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select, delete
from .db import Base, engine, Session, Experiment, Dataset, Record, now, ConfigRow, StrategyRow
from .contracts import Config, STRATEGIES
from .experiments import create_experiment, queue
from .db import DisclosureSnapshot, BenchmarkSuite
from .data import seed_demo, load
from .engine import simulate
from .inference import models

@asynccontextmanager
async def lifespan(app):
    if engine.dialect.name=='sqlite': Base.metadata.create_all(engine)
    with Session() as db:
        for strategy in STRATEGIES: db.merge(StrategyRow(id=strategy,version='1'))
        db.commit()
    seed_demo()
    yield
app=FastAPI(title='Agentic Alpha — Simulation Only',lifespan=lifespan)
def auth(authorization: str=Header(default='')):
    import hmac
    token=os.getenv('API_TOKEN','')
    if token and not hmac.compare_digest(authorization,'Bearer '+token): raise HTTPException(401,'Invalid API token')
@app.exception_handler(ValueError)
async def value_error(request,exc): return JSONResponse(status_code=422,content={'detail':str(exc)})
def get(db,id):
    row=db.scalar(select(Experiment).where(Experiment.id == id).with_for_update())
    if not row: raise HTTPException(404,'Experiment not found')
    return row
def describe(e): return dict(execution_provenance=e.result.get('execution_provenance',{}), id=e.id,config=e.config,status=e.status,progress=e.progress,created=e.created,updated=e.updated,error=e.error)
@app.get('/api/health')
def health(): return {'status':'ok','simulation_only':True}
@app.get('/api/strategies',dependencies=[Depends(auth)])
def strategies(): return [dict(id=s,name=s.replace('_',' ').title(),version='1') for s in STRATEGIES]
@app.get('/api/strategies/{id}',dependencies=[Depends(auth)])
def strategy(id:str):
    if id not in STRATEGIES: raise HTTPException(404,'Unknown strategy')
    return dict(id=id,version='1',schema=Config.model_json_schema())
@app.get('/api/datasets',dependencies=[Depends(auth)])
def datasets():
    with Session() as db: return [dict(id=d.id,**{**d.manifest,'warnings':d.manifest.get('warnings',[]) + (['Legacy provenance: adjustment conventions unverified'] if d.manifest.get('schema_version')!=2 else [])}) for d in db.scalars(select(Dataset))]
@app.post('/api/experiments',dependencies=[Depends(auth)],status_code=201)
def create(config:Config):
    return describe(create_experiment(config, Session))
@app.get('/api/experiments',dependencies=[Depends(auth)])
def experiments(offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200)):
    with Session() as db: return [describe(e) for e in db.scalars(select(Experiment).order_by(Experiment.created.desc()).offset(offset).limit(limit))]
@app.get('/api/experiments/{id}',dependencies=[Depends(auth)])
def experiment(id:str):
    with Session() as db: return describe(get(db,id))
@app.post('/api/experiments/{id}/run',dependencies=[Depends(auth)])
async def run(id:str):
    with Session() as db:
        e=get(db,id); c=Config(**e.config)
        if e.status not in ('created','failed','partial'): raise HTTPException(409,'Experiment is already queued or completed')
        if c.strategy in ('single_agent','multi_agent'):
            available=await models(c.provider)
            if c.model not in available or (c.decision_model and c.decision_model not in available): raise ValueError('Configured model is unavailable')
        queue(e); db.commit(); return describe(e)
@app.post('/api/experiments/{id}/cancel',dependencies=[Depends(auth)])
def cancel(id:str):
    with Session() as db:
        e=get(db,id)
        if e.status in ('created','queued','running','waiting'): e.status='canceled'; db.commit()
        return describe(e)
@app.delete('/api/experiments/{id}', dependencies=[Depends(auth)])
def delete_experiment(id: str):
    with Session() as db:
        experiment = get(db, id)
        if experiment.status in ('queued', 'running', 'waiting'):
            raise HTTPException(409, 'Cancel the active experiment before deleting it')
        # Delete dependent rows before their parents; preserve shared datasets.
        for table in reversed(Base.metadata.sorted_tables):
            if 'experiment_id' in table.c:
                db.execute(delete(table).where(table.c.experiment_id == id))
        db.delete(experiment)
        db.commit()
    return {'id': id, 'deleted': True}

@app.get('/api/experiments/{id}/{section}',dependencies=[Depends(auth)])
def result(id:str,section:str,offset:int=Query(0,ge=0),limit:int=Query(200,ge=1,le=10000)):
    if section not in ('metrics','equity','trades','decisions','orders','export'): raise HTTPException(404)
    with Session() as db:
        e=get(db,id)
        if section=='export': return dict(experiment=describe(e),results=e.result)
        value=e.result.get(section,{} if section=='metrics' else [])
        return value[offset:offset+limit] if isinstance(value,list) else value
@app.get('/api/portfolios/{id}',dependencies=[Depends(auth)])
def portfolio(id:str):
    with Session() as db:
        e=get(db,id); return dict(id=id,simulated=True,cash=e.result.get('cash',e.config['initial_capital']),positions=e.result.get('positions',{}))
@app.get('/api/portfolios/{id}/{section}',dependencies=[Depends(auth)])
def portfolio_section(id:str,section:str):
    with Session() as db:
        e=get(db,id)
        if section=='positions': return e.result.get('positions',{})
        if section=='transactions': return e.result.get('trades',[])
        raise HTTPException(404)
@app.get('/api/providers/status',dependencies=[Depends(auth)])
def providers(): return dict(simulation_only=True,cloud_enabled=os.getenv('ENABLE_CLOUD','false')=='true',market_data='Versioned local imports',inference='Optional; check model availability',brokerage='Not implemented')
@app.get('/api/models',dependencies=[Depends(auth)])
async def model_list(provider:str='ollama'):
    if provider not in ('ollama','compatible','openai'): raise ValueError('Unknown provider')
    try: return await models(provider)
    except Exception: raise HTTPException(503,'Model provider unavailable or disabled')

from pydantic import BaseModel, Field
import pandas as pd
from .data import register
class ImportRequest(BaseModel):
    id: str
    provenance: str = Field(min_length=1)
    synthetic: bool = False
    bars: list[dict] = Field(min_length=1,max_length=200000)
    disclosures: list[dict] = []
    actions: list[dict] = []
@app.post('/api/datasets/import',dependencies=[Depends(auth)],status_code=201)
def import_dataset(request:ImportRequest):
    return register(request.id,pd.DataFrame(request.bars),request.provenance,request.synthetic,request.disclosures,request.actions)
class AdvanceRequest(BaseModel):
    dataset: str
@app.post('/api/experiments/{id}/advance',dependencies=[Depends(auth)])
def advance(id:str,request:AdvanceRequest):
    with Session() as db:
        e=get(db,id)
        if e.config['mode']!='forward' or e.status not in ('waiting','created'): raise HTTPException(409,'Only idle forward experiments can advance')
        old,old_manifest=load(e.config['dataset']); new,new_manifest=load(request.dataset)
        cutoff=old.date.max()
        if not old.reset_index(drop=True).equals(new[new.date<=cutoff].reset_index(drop=True)): raise ValueError('New dataset must preserve every previous bar unchanged')
        if old_manifest['actions']!=[a for a in new_manifest['actions'] if a['date']<=str(cutoff.date())]: raise ValueError('Corporate-action history changed')
        e.config={**e.config,'dataset':request.dataset}; e.status='queued'; db.commit(); return describe(e)

@app.get('/api/disclosure-snapshots',dependencies=[Depends(auth)])
def disclosure_snapshots():
    with Session() as db: return [dict(id=d.id,**d.manifest) for d in db.scalars(select(DisclosureSnapshot))]

@app.get('/api/benchmark-suites',dependencies=[Depends(auth)])
def benchmark_suites():
    with Session() as db: return [dict(id=s.id,config=s.config,members=s.members) for s in db.scalars(select(BenchmarkSuite))]
