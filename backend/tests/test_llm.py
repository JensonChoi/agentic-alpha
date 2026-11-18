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

@pytest.mark.parametrize('case,code,stage', [
    ('mixed','mixed_tools_and_output','protocol_validation'),
    ('empty','expected_portfolio_output','protocol_validation'),
    ('symbol','unauthorized_signal_symbol','semantic_validation'),
    ('duplicate','duplicate_signal_symbol','semantic_validation'),
    ('evidence','unknown_evidence_reference','semantic_validation'),
    ('entry','nonpositive_buy_weight','semantic_validation'),
    ('ineligible_entry','ineligible_buy_symbol','semantic_validation'),
    ('exit','invalid_exit','semantic_validation'),
    ('rounds','tool_rounds_exhausted','budget'),
    ('tools','tool_budget_exhausted','budget'),
])
async def test_precise_decision_errors(monkeypatch,case,code,stage):
    c,ctx=setup(); output=final()
    if case=='mixed': output.tools=[ToolRequest(name='cash')]
    if case=='empty': output=Envelope()
    if case=='symbol': output.final.signals[0].ticker='SECRET'
    if case=='duplicate': output.final.signals.append(output.final.signals[0].model_copy())
    if case=='evidence': output.final.evidence_refs=['SECRET']
    if case=='ineligible_entry':
        ctx['entries'].remove('AAPL')
        ctx['holdings']['AAPL'] = 1
    if case=='entry': output.final.signals[0].target_weight=0
    if case=='exit': output.final.signals[0].action='SELL'
    if case in ('rounds','tools'):
        output=Envelope(tools=[ToolRequest(name='cash')])
        if case=='rounds': c.tool_rounds=0
        else: c.tool_calls=0
    async def fake(*args): return output,{}
    monkeypatch.setattr('app.inference.call',fake)
    signals,trace=await evaluate(c,ctx)
    assert not signals
    assert trace[-1]['error_code']==code and trace[-1]['error_stage']==stage
    assert trace[0]['error_code']==code
    assert trace[0]['status']=='completed'  # Parsed transport response, not validated output.
    assert trace[0]['validation_status']=='failed'
    assert 'SECRET' not in json.dumps(trace)

@pytest.mark.parametrize('payload,code', [
    ('not JSON SECRET','invalid_model_json'),
    ('{"final":{"SECRET":"private"}}','output_schema_invalid'),
])
async def test_adapter_schema_error_codes_without_input_leak(monkeypatch,payload,code):
    c,ctx=setup()
    async def post(self,url,**kwargs):
        return httpx.Response(200,json={'message':{'content':payload,'thinking':'SECRET'}},request=httpx.Request('POST',url))
    monkeypatch.setattr(httpx.AsyncClient,'post',post)
    signals,trace=await evaluate(c,ctx)
    assert not signals and trace[0]['error_code']==code
    assert trace[-1]['error_code']==code
    assert 'SECRET' not in json.dumps(trace) and 'private' not in json.dumps(trace)

async def test_budget_deadline_transport_codes(monkeypatch):
    c,ctx=setup(max_model_calls=1)
    async def tool(*args): return Envelope(tools=[ToolRequest(name='cash')]),{}
    monkeypatch.setattr('app.inference.call',tool)
    assert (await evaluate(c,ctx))[1][-1]['error_code']=='model_budget_exhausted'
    async def slow(*args): await asyncio.sleep(1)
    monkeypatch.setattr('app.inference.call',slow);c.decision_timeout=.01
    trace=(await evaluate(c,ctx))[1]
    assert trace[-1]['error_code']=='decision_deadline_exceeded'
    assert trace[0]['status']=='canceled'
    assert trace[0]['validation_status']=='failed'
    async def unavailable(*args): raise httpx.ConnectError('SECRET')
    monkeypatch.setattr('app.inference.call',unavailable);c.decision_timeout=1
    trace=(await evaluate(c,ctx))[1]
    assert trace[0]['error_code']=='provider_unavailable'
    assert 'SECRET' not in json.dumps(trace)

async def test_analyst_failure_retains_role_error_code(monkeypatch):
    c,ctx=setup();c.strategy='multi_agent'
    async def fake(config,role,*args):
        if role=='risk': return final(),{}
        return Envelope(analyst=dict(role=role,candidates_considered=[],findings=[],missing_inputs=[],concerns=[])),{}
    monkeypatch.setattr('app.inference.call',fake)
    signals,trace=await evaluate(c,ctx)
    assert not signals and trace[-1]['error_code']=='required_analyst_failed'
    risk=next(t for t in trace if t['role']=='risk')
    assert risk['error_code']=='expected_analyst_output'
    assert risk['validation_status']=='failed'

@pytest.mark.parametrize('failure,code', [
    ('timeout','call_timeout'),
    ('http400','unsupported_capability_or_model'),
    ('http503','provider_http_error'),
    ('bad_json','invalid_provider_json'),
    ('bad_shape','invalid_provider_response'),
])
async def test_provider_error_classification(monkeypatch,failure,code):
    c,ctx=setup(retries=0)
    async def post(self,url,**kwargs):
        if failure=='timeout': raise httpx.ReadTimeout('SECRET')
        if failure.startswith('http'):
            return httpx.Response(int(failure[4:]),text='SECRET',request=httpx.Request('POST',url))
        if failure=='bad_json': return httpx.Response(200,text='SECRET',request=httpx.Request('POST',url))
        return httpx.Response(200,json={'thinking':'SECRET'},request=httpx.Request('POST',url))
    monkeypatch.setattr(httpx.AsyncClient,'post',post)
    signals,trace=await evaluate(c,ctx)
    assert not signals
    assert trace[0]['error_code']==trace[-1]['error_code']==code
    assert 'SECRET' not in json.dumps(trace)

async def test_price_only_limits_tools_and_citations(monkeypatch):
    c,ctx=setup(price_only=True, tool_calls=1)
    for name in ('news','fundamentals'):
        assert dispatch(ToolRequest(name=name,ticker='AAPL'),ctx,c)['status']=='unsupported'
    schemas=[]
    async def post(self,url,**kwargs):
        schema=kwargs['json']['format']
        schemas.append(schema)
        if len(schemas)==1:
            assert set(schema['$defs']['ToolRequest']['properties']['name']['enum'])=={'prices','indicators','cash','positions','rules'}
            assert schema['anyOf'][1]['properties']['tools']['maxItems']==1
            content='{"tools":[{"name":"cash"}]}'
        else:
            assert schema['required']==['final'] and not schema['additionalProperties']
            refs=schema['$defs']['PriceOnlyFinalOutput']['properties']['evidence_refs']['items']['enum']
            assert 'snapshot' in refs and len(refs)==2
            content=json.dumps({'final':final().final.model_dump()})
        return httpx.Response(200,json={'message':{'content':content}},request=httpx.Request('POST',url))
    monkeypatch.setattr(httpx.AsyncClient,'post',post)
    signals,trace=await evaluate(c,ctx)
    assert signals and trace[-1]['actual_calls']==2

@pytest.mark.parametrize('holdings,ticker,weight,error', [
    ({'AAPL': 1}, 'AAPL', {}, None),
    ({'AAPL': 1}, 'VOO', {}, 'invalid_exit'),
    ({}, 'AAPL', {}, 'invalid_exit'),
    ({'AAPL': 1}, 'AAPL', {'target_weight': 0}, 'output_schema_invalid'),
])
async def test_price_only_sell_uses_held_ticker_and_implicit_zero(monkeypatch, holdings, ticker, weight, error):
    c, ctx = setup(price_only=True, tool_calls=0)
    ctx['holdings'] = holdings

    async def post(self, url, **kwargs):
        definitions = kwargs['json']['format']['$defs']
        if holdings:
            sell = definitions['SellResponse']
            assert sell['properties']['ticker']['enum'] == sorted(holdings)
            assert 'target_weight' not in sell['properties']
            assert not sell['additionalProperties']
        else:
            assert 'SellResponse' not in definitions
        output = final().final.model_dump()
        output['signals'] = [dict(ticker=ticker, action='SELL', rationale='Exit', **weight)]
        content = json.dumps({'final': output})
        return httpx.Response(200, json={'message': {'content': content}}, request=httpx.Request('POST', url))

    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    signals, trace = await evaluate(c, ctx)
    assert trace[-1].get('error_code') == error
    if error is None:
        assert [(s.ticker, s.action, s.target_weight) for s in signals] == [('AAPL', 'SELL', 0)]
    else:
        assert not signals

@pytest.mark.parametrize('entries,ticker,weight,error', [
    (['AAPL'], 'AAPL', {'target_weight': .1}, None),
    (['AAPL'], 'AAPL', {'target_weight': 0}, 'output_schema_invalid'),
    (['AAPL'], 'AAPL', {}, 'output_schema_invalid'),
    (['AAPL'], 'VOO', {'target_weight': .1}, 'ineligible_buy_symbol'),
    ([], 'VOO', {'target_weight': .1}, 'ineligible_buy_symbol'),
])
async def test_price_only_buy_requires_eligible_ticker_and_positive_weight(monkeypatch, entries, ticker, weight, error):
    c, ctx = setup(price_only=True, tool_calls=0)
    ctx['entries'] = entries
    ctx['holdings'] = {'VOO': 1}

    async def post(self, url, **kwargs):
        definitions = kwargs['json']['format']['$defs']
        if entries:
            buy = definitions['BuyResponse']
            assert buy['properties']['ticker']['enum'] == entries
            assert 'target_weight' in buy['required']
            assert buy['properties']['target_weight']['exclusiveMinimum'] == 0
        else:
            assert 'BuyResponse' not in definitions
        assert definitions['HoldResponse']['properties']['ticker']['enum'] == sorted(set(entries) | {'VOO'})
        output = final().final.model_dump()
        output['signals'] = [dict(ticker=ticker, action='BUY', rationale='Entry', **weight)]
        content = json.dumps({'final': output})
        return httpx.Response(200, json={'message': {'content': content}}, request=httpx.Request('POST', url))

    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    signals, trace = await evaluate(c, ctx)
    assert trace[-1].get('error_code') == error
    if error is None:
        assert [(s.ticker, s.action, s.target_weight) for s in signals] == [('AAPL', 'BUY', .1)]
    else:
        assert not signals
