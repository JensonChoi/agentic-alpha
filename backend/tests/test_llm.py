"""Offline synthetic LLM integration, never a performance benchmark."""
import asyncio
import json
import httpx
import pandas as pd
import pytest
from app.contracts import Config, Signal, TradeSignal
from app.agent_tools import snapshot, dispatch, ToolRequest, validate_records
from app.inference import evaluate, Envelope, call
from test_engine import fixture, config


def setup(**kwargs):
    c=config(strategy='single_agent',model='mock',**kwargs); f,m=fixture(); day=pd.Timestamp('2024-04-05')
    portfolio=dict(cash=100000,equity=100000,positions={},date=str(day.date()))
    return c,snapshot(c,f[f.date<=day],m,portfolio,[portfolio],day)

def final(ticker='AAPL'):
    return Envelope(final=dict(signals=[dict(ticker=ticker,action='BUY',target_weight=.1,rationale='Supported by snapshot',strategy_id='untrusted')],synthesis='Concise',agreement='',disagreement='',evidence_refs=['snapshot']))

def test_screener_and_dispatch():
    c,ctx=setup(max_candidates=1)
    assert ctx['entries']==['AAPL']
    assert dispatch(ToolRequest(name='prices',ticker='TSLA'),ctx,c)['status']=='rejected'
    assert dispatch(ToolRequest(name='news',ticker='AAPL'),ctx,c)['status']=='missing'
    assert len(dispatch(ToolRequest(name='prices',ticker='AAPL',rows=2),ctx,c)['data'])==2
    assert TradeSignal is Signal
    with pytest.raises(ValueError): ToolRequest(name='shell')
    with pytest.raises(ValueError): ToolRequest(name='prices',ticker='AAPL',rows=101)

async def test_tool_cycle_and_identity(monkeypatch):
    c,ctx=setup(); calls=[]
    async def fake(*args):
        calls.append(args)
        return (Envelope(tools=[dict(name='prices',ticker='AAPL')]) if len(calls)==1 else final()),{}
    monkeypatch.setattr('app.inference.call',fake)
    signals,trace=await evaluate(c,ctx)
    assert signals[0].strategy_id=='single_agent'
    assert trace[-1]['actual_calls']==2 and trace[0]['tools'][0]['result']['status']=='available'

async def test_roles_and_failure(monkeypatch):
    c,ctx=setup(); c.strategy='multi_agent'; c.analyst_concurrency=2
    active=0; peak=0
    async def fake(c,role,*args):
        nonlocal active,peak
        active+=1; peak=max(peak,active); await asyncio.sleep(.001); active-=1
        if role=='portfolio': return final(),{}
        return Envelope(analyst=dict(role=role,candidates_considered=['AAPL'],findings=[],missing_inputs=['news'],concerns=[])),{}
    monkeypatch.setattr('app.inference.call',fake)
    signals,trace=await evaluate(c,ctx)
    assert signals and peak==2 and trace[-1]['actual_calls']==4
    async def bad(c,role,*args):
        if role=='risk': raise ValueError('private reasoning must not persist')
        return await fake(c,role,*args)
    monkeypatch.setattr('app.inference.call',bad)
    signals,trace=await evaluate(c,ctx)
    assert not signals and trace[-1]['status']=='failed'
    assert 'private reasoning' not in json.dumps(trace)
    assert not any(t['role']=='portfolio' for t in trace)

@pytest.mark.parametrize('ticker',['UNAUTHORIZED'])
async def test_invalid_symbol(monkeypatch,ticker):
    c,ctx=setup()
    async def fake(*args): return final(ticker),{}
    monkeypatch.setattr('app.inference.call',fake)
    signals,trace=await evaluate(c,ctx)
    assert not signals and trace[-1]['status']=='failed'

async def test_budget_and_deadline(monkeypatch):
    c,ctx=setup(max_model_calls=1)
    async def fake(*args): return Envelope(tools=[dict(name='cash')]),{}
    monkeypatch.setattr('app.inference.call',fake)
    signals,trace=await evaluate(c,ctx)
    assert not signals and trace[-1]['actual_calls']==1
    async def slow(*args): await asyncio.sleep(1)
    monkeypatch.setattr('app.inference.call',slow); c.decision_timeout=.01
    signals,trace=await evaluate(c,ctx)
    assert not signals and trace[-1]['elapsed_seconds']<.2

def test_revision_cutoff_and_stale():
    c,ctx=setup()
    base=dict(id='one',ticker='AAPL',kind='fundamentals',published_at='2024-04-01T12:00:00Z',available_at='2024-04-01T12:00:00Z',provenance='fixture',metric='eps',value=2,unit='USD/share')
    ctx['_evidence']=validate_records([base,{**base,'revision':2,'available_at':'2024-04-10T12:00:00Z','value':99}])
    result=dispatch(ToolRequest(name='fundamentals',ticker='AAPL'),ctx,c)
    assert result['data'][0]['value']==2
    c.fundamentals_max_age_days=1
    assert dispatch(ToolRequest(name='fundamentals',ticker='AAPL'),ctx,c)['status']=='stale'

@pytest.mark.parametrize('model',['qwen3.5:9b','gemma4:12b'])
@pytest.mark.parametrize('provider',['ollama','compatible','openai'])
async def test_adapter_settings_and_redaction(monkeypatch,model,provider):
    c,ctx=setup(); c.model=model; c.provider=provider
    monkeypatch.setenv('ENABLE_CLOUD','true'); captured=[]
    async def post(self,url,**kwargs):
        captured.append(kwargs['json'])
        content=final().model_dump_json()
        data={'model':model,'message':{'content':content,'thinking':'SECRET'}} if provider=='ollama' else {'model':model,'choices':[{'message':{'content':content,'reasoning_content':'SECRET'}}]}
        return httpx.Response(200,json=data,request=httpx.Request('POST',url))
    monkeypatch.setattr(httpx.AsyncClient,'post',post)
    output,meta=await call(c,'portfolio',{'evidence_refs':['snapshot']})
    assert 'SECRET' not in json.dumps(meta)+output.model_dump_json()
    assert captured[0]['model']==model
    if provider=='ollama': assert captured[0]['options']['seed']==42 and captured[0]['options']['num_ctx']==8192
    else: assert captured[0]['seed']==42

async def test_synthetic_execution_resume(monkeypatch):
    from app.engine import simulate
    import copy
    c=config(strategy='single_agent',model='mock',rebalance='daily'); f,m=fixture(); calls=[]
    async def fake(*args): calls.append(1); return final(),{}
    monkeypatch.setattr('app.inference.call',fake)
    saved=[]
    def checkpoint(progress,result): saved.append(copy.deepcopy(result)); return len(saved)<3
    await simulate(c,f,m,checkpoint)
    before=len(calls)
    resumed=await simulate(c,f,m,resume=saved[-1])
    assert resumed['trades'] and resumed['trades'][0]['date']=='2024-04-02'
    assert resumed['trades'][0]['decision_id']=='2024-04-01'
    assert resumed['decisions'][:3]==saved[-1]['decisions']
    assert len(calls)-before==len(resumed['equity'])-3
    again=await simulate(c,f,m,resume=resumed)
    assert again['trades']==resumed['trades']

async def test_empty_and_held_review(monkeypatch):
    c,ctx=setup();ctx['entries']=[];ctx['holdings']={}
    async def never(*args): raise AssertionError('No call expected')
    monkeypatch.setattr('app.inference.call',never)
    signals,trace=await evaluate(c,ctx)
    assert not signals and trace[0]['status']=='skipped'
    ctx['holdings']={'AAPL':1}
    async def sell(*args):
        output=final();output.final.signals[0].action='SELL';output.final.signals[0].target_weight=0
        return output,{}
    monkeypatch.setattr('app.inference.call',sell)
    signals,trace=await evaluate(c,ctx)
    assert signals[0].action=='SELL'

async def test_retry_counted(monkeypatch):
    c,ctx=setup(); calls=[]
    async def fake(*args):
        calls.append(1)
        if len(calls)==1: raise httpx.ConnectError('secret endpoint')
        return final(),{}
    monkeypatch.setattr('app.inference.call',fake)
    signals,trace=await evaluate(c,ctx)
    assert signals and trace[-1]['actual_calls']==2 and trace[0]['status']=='failed'
    assert 'secret endpoint' not in json.dumps(trace)

async def test_final_model_override(monkeypatch):
    c,ctx=setup();c.strategy='multi_agent';c.decision_model='final-model';c.decision_provider='compatible'
    async def fake(config,role,context,model,provider):
        if role=='portfolio':
            assert model=='final-model' and provider=='compatible'
            return final(),{}
        assert model=='mock' and provider=='ollama'
        return Envelope(analyst=dict(role=role,candidates_considered=[],findings=[],missing_inputs=[],concerns=[])),{}
    monkeypatch.setattr('app.inference.call',fake)
    assert (await evaluate(c,ctx))[0]
