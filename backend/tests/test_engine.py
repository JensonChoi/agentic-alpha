import pytest
import pandas as pd
from decimal import Decimal
from app.engine import Ledger,simulate
from app.contracts import Config,Signal,Proposals
from app.data import sessions

def fixture():
    rows=[]
    for i,d in enumerate(sessions('2024-01-02','2024-05-31')):
        for ticker in ['VOO','AAPL']:
            price=100+i
            rows.append(dict(date=d,ticker=ticker,open=price,close=price+1,high=price+2,low=price-1,volume=1000))
    return pd.DataFrame(rows),dict(start='2024-01-02',end='2024-05-31',disclosures=[],actions=[])
def config(**kwargs): return Config(start='2024-04-01',end='2024-04-30',universe=['VOO','AAPL'],**kwargs)
def test_accounting():
    l=Ledger(1000); l.fill('one','AAPL','2.5',100,1)
    assert l.cash==Decimal('749')
    assert l.equity({'AAPL':100})==999
    assert not l.fill('one','AAPL',2.5,100,1)
    l.fill('two','AAPL',-1,110,1)
    assert l.cash==858 and l.positions['AAPL']==Decimal('1.5')
    with pytest.raises(ValueError): l.fill('bad','AAPL',-3,100,0)
async def test_baseline():
    f,m=fixture(); r=await simulate(config(strategy='buy_and_hold'),f,m)
    assert len(r['trades'])==1
    assert r['trades'][0]['date']=='2024-04-01'
    assert r['cash']>=0
    for p in r['equity']: assert p['equity']==pytest.approx(p['cash']+sum(q*p['prices'][t] for t,q in p['positions'].items()))
async def test_disclosure_next_day():
    f,m=fixture(); m['disclosures']=[dict(id='a',ticker='AAPL',action='BUY',security_type='stock',transaction_date='2024-01-02',disclosure_date='2024-04-05',value_low=1000,value_high=2000)]
    r=await simulate(config(strategy='congressional'),f,m)
    assert r['trades'][0]['date']=='2024-04-08'
    assert len(r['trades'])==1
async def test_missing_open():
    f,m=fixture(); f=f[~((f.date==pd.Timestamp('2024-04-01'))&(f.ticker=='VOO'))]
    r=await simulate(config(strategy='buy_and_hold'),f,m)
    assert not r['trades']; assert r['orders'][0]['status']=='unfilled'
async def test_unsupported_and_duplicate_disclosure():
    f,m=fixture(); d=dict(id='a',ticker='AAPL',action='BUY',security_type='option',disclosure_date='2024-04-05',value_low=1,value_high=2);m['disclosures']=[d,d]
    r=await simulate(config(strategy='congressional'),f,m)
    assert not r['trades'];assert 'unsupported' in r['decisions'][0]['reason']
async def test_split_and_dividend():
    f,m=fixture();m['actions']=[dict(date='2024-04-03',ticker='VOO',type='split',ratio=2),dict(date='2024-04-04',ticker='VOO',type='dividend',amount=1)]
    r=await simulate(config(strategy='buy_and_hold'),f,m)
    assert r['positions']['VOO']==pytest.approx(2*r['trades'][0]['quantity'])
    assert r['cash']>=r['positions']['VOO']
async def test_llm_cannot_bypass_risk(monkeypatch):
    async def bad(*args): return [Signal(ticker='AAPL',action='BUY',target_weight=1,rationale='bad')],[]
    monkeypatch.setattr('app.engine.evaluate',bad)
    f,m=fixture();r=await simulate(config(strategy='single_agent',model='mock',rebalance='daily'),f,m)
    assert not r['trades'];assert any('limit' in o['reason'] for o in r['orders'])
async def test_failure_no_trade(monkeypatch):
    async def bad(*args): raise TimeoutError()
    monkeypatch.setattr('app.engine.evaluate',bad)
    f,m=fixture();r=await simulate(config(strategy='single_agent',model='mock',rebalance='daily'),f,m)
    assert r['failures']>0 and not r['trades']
def test_cloud_opt_in(monkeypatch):
    from app.inference import settings
    monkeypatch.delenv('ENABLE_CLOUD',raising=False)
    with pytest.raises(ValueError): settings('openai')
def test_schema():
    with pytest.raises(ValueError): Proposals.model_validate_json('{"signals":[{"ticker":"VOO","action":"SHORT"}]}')
def test_holiday(): assert not len(sessions('2024-07-04','2024-07-04'))
async def test_cancel():
    f,m=fixture(); assert (await simulate(config(),f,m,lambda *_:False))['canceled']
async def test_checkpoint_resume_matches_full_run():
    f,m=fixture();c=config(strategy='buy_and_hold');saved=[]
    def checkpoint(progress,state):
        import copy
        saved.append(copy.deepcopy(state)); return len(saved)<5
    await simulate(c,f,m,checkpoint)
    resumed=await simulate(c,f,m,resume=saved[-1]);full=await simulate(c,f,m)
    assert resumed['trades']==full['trades']
    assert resumed['metrics']['final_value']==pytest.approx(full['metrics']['final_value'])

async def test_future_bars_do_not_change_past_signals():
    f,m=fixture();c=config(strategy='momentum',rebalance='daily')
    original=await simulate(c,f,m)
    altered=f.copy();mask=altered.date>pd.Timestamp('2024-04-15');altered.loc[mask,'close']*=5
    changed=await simulate(c,altered,m)
    assert [d for d in original['decisions'] if d['date']<='2024-04-15']==[d for d in changed['decisions'] if d['date']<='2024-04-15']

async def test_forward_duplicate_poll():
    f,m=fixture();c=config(strategy='buy_and_hold',mode='forward')
    first=await simulate(c,f,m);second=await simulate(c,f,m,resume=first)
    assert second['trades']==first['trades']
    assert second['cash']==first['cash']
