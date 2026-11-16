from copy import deepcopy
import pytest
from app.contracts import Config
from app.disclosures import inferred_holdings
from app.engine import simulate
from app.experiments import validate
from test_engine import fixture
from test_real_data import disclosure


def config(**updates):
    return Config(**dict(strategy='congressional', disclosure_snapshot='current', starting_holdings_snapshot='history', starting_holdings_since='2024-01-01', start='2024-04-01', end='2024-04-30', availability_policy='filing_date', max_position_weight=.2, **updates))


def row(identity, ticker='AAPL', action='BUY', filing='2024-03-01', **updates):
    return disclosure(source_id=identity, ticker=ticker, action=action, filing_date=filing, transaction_date='2024-01-02', availability_quality='unverified', published_at=None, **updates)


def test_initial_cutoff_partial_sales_and_no_future_leakage():
    c=config()
    rows=[row('buy'),row('partial',action='SELL',filing='2024-03-02',original={'sale_description':'S (partial)'}),row('future','MSFT',filing='2024-04-01'),row('old','TSLA',filing='2023-12-31')]
    initial=inferred_holdings(c,rows)
    assert initial['selected']==['AAPL']
    assert inferred_holdings(c,rows+[row('full',action='SELL',filing='2024-03-03')])['selected']==[]
    assert inferred_holdings(c.model_copy(update={'availability_policy':'verified'}),rows)['selected']==[]


def test_initial_caps_and_amendment_no_replay():
    rows=[row(str(i),t) for i,t in enumerate(['Z','C','B','A','D','E'])]
    c=config(max_positions=2)
    initial=inferred_holdings(c,rows)
    assert initial['selected']==['A','B'] and initial['excluded']==['C','D','E','Z']
    rows += [row('amend','A',action='SELL',filing='2024-03-03',amends='3')]
    assert inferred_holdings(c,rows)['selected']==['A','B']


async def test_initial_shared_execution_later_exit_and_restart():
    c=config(); f,m=fixture()
    m['starting_holdings']=inferred_holdings(c,[row('initial')])
    m['disclosures']=[row('sale',action='SELL',filing='2024-04-05')]
    checkpoints=[]
    def save(progress,state): checkpoints.append(deepcopy(state)); return True
    result=await simulate(c,f,m,save)
    assert [(t['ticker'],t['date']) for t in result['trades']]==[('AAPL','2024-04-01'),('AAPL','2024-04-08')]
    assert result['trades'][0]['quantity']>0 and result['trades'][1]['quantity']<0
    assert result['trades'][0]['slippage_cost']>0
    assert result['positions']['AAPL']==0
    resumed=await simulate(c,f,m,resume=checkpoints[2])
    for key in ('metrics','trades','equity','starting_holdings'): assert resumed[key]==result[key]


def test_initial_price_and_quality_preflight():
    c=config(); f,m=fixture(); m['symbols']=['VOO','AAPL'];m['disclosures']=[]
    m['starting_holdings']=inferred_holdings(c,[row('buy')])
    validate(c,f,m)
    with pytest.raises(ValueError,match='missing'): validate(c,f[f.ticker!='AAPL'],m)
    m['starting_holdings_snapshot']={'quarantines':[{'reason':'unknown row'}]}
    with pytest.raises(ValueError,match='quarantines'): validate(c,f,m)


def test_initial_conflicts_fail_closed():
    c=config(); f,m=fixture();m['symbols']=['VOO','AAPL']
    m['disclosures']=[row('current',filing='2024-04-05')]
    m['starting_holdings']=inferred_holdings(c,[row('b'),row('s',action='SELL')])
    assert m['starting_holdings']['selected']==[]
    with pytest.raises(ValueError,match='ambiguous'):validate(c,f,m)


async def test_reserve_candidate_missing_prices_fail_or_report_partial():
    import pandas as pd
    c=config()
    f,m=fixture()
    tickers=['AAPL','B','C','D','E','Z']
    f=pd.concat([f]+[f[f.ticker=='AAPL'].assign(ticker=t) for t in tickers[1:-1]],ignore_index=True)
    m['symbols']=sorted(f.ticker.unique())
    m['starting_holdings']=inferred_holdings(c,[row(t,t) for t in tickers])
    assert m['starting_holdings']['excluded']==['Z']
    m['disclosures']=[row('exit',action='SELL',filing='2024-04-05')]
    with pytest.raises(ValueError,match='Missing price histories: Z'):validate(c,f,m)
    permissive=c.model_copy(update={'missing_price_policy':'skip'})
    validate(permissive,f,m)
    result=await simulate(permissive,f,m)
    assert result['failures']>0 and result['missing_sessions']['Z']>0
    assert any(o['signal']['ticker']=='Z' and o['status']=='unfilled' for o in result['orders'])
    m['symbols'].append('Z')
    with pytest.raises(ValueError,match='Z: missing'):validate(c,f,m)


@pytest.mark.parametrize('description,expected',[('S (partial)',['AAPL']),('S (full)',[])])
def test_repeated_corrections_preserve_sale_semantics(tmp_path,monkeypatch,description,expected):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app import data
    from app.db import Base
    from app.disclosures import register_snapshot,load_snapshot
    from app.house import correct_snapshot
    engine=create_engine('sqlite:///'+str(tmp_path/'corrections.db'))
    Base.metadata.create_all(engine)
    monkeypatch.setattr(data,'Session',sessionmaker(engine,expire_on_commit=False))
    records=[row('buy'),row('sell',action='SELL',filing='2024-03-02',original={'sale_description':description})]
    register_snapshot('original',records,{'provenance':'Synthetic'})
    source='original'
    for target in ('review1','review2'):
        correct_snapshot(source,target,[dict(source_id='sell',reviewer='Synthetic reviewer',evidence='Synthetic owner confirmation',changes={'owner':'spouse'})],'Synthetic review')
        corrected,_=load_snapshot(target)
        assert inferred_holdings(config(),corrected)['selected']==expected
        source=target
