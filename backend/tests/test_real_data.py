"""Entirely synthetic fixtures: these tests require no provider access."""
import copy
from datetime import date
from decimal import Decimal
import httpx
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app import data, worker, benchmarks
from app.contracts import Config
from app.db import Base, Dataset, Experiment
from app.providers import normalize_yahoo, YahooProvider, QuiverProvider, retry
from app.disclosures import Disclosure, register_snapshot, load_snapshot, selected_records
from app.experiments import create_experiment, validate
from app.engine import Ledger, simulate
from test_engine import fixture

@pytest.fixture
def storage(tmp_path,monkeypatch):
    engine=create_engine('sqlite:///'+str(tmp_path/'test.db'))
    Base.metadata.create_all(engine)
    session=sessionmaker(engine,expire_on_commit=False)
    monkeypatch.setattr(data,'Session',session); monkeypatch.setattr(worker,'Session',session); monkeypatch.setattr(data,'ROOT',tmp_path/'datasets')
    return session


def disclosure(**overrides):
    return Disclosure(**dict(dict(source_id='source-1',member_id='P000197',owner='spouse',ticker='AAPL',action='BUY',security_type='stock',transaction_date='2024-03-01',filing_date='2024-04-01',published_at='2024-04-05T08:00:00-04:00',availability_quality='verified_timestamp',publication_evidence='Synthetic source evidence fixture'),**overrides)).model_dump(mode='json')


def raw():
    index=pd.date_range('2024-04-01',periods=4,freq='B',tz='America/New_York')
    return pd.DataFrame(dict(Open=[50.,51,52,53],High=[51.,52,53,54],Low=[49.,50,51,52],Close=[50.,51,52,53],Volume=[2000.,2000,2000,2000],Dividends=[.5,0,0,0],**{'Adj Close':[49.,50,51,52],'Stock Splits':[0.,0,2,0]}),index=index)

@pytest.mark.parametrize('multi',[False,True])
def test_split_normalization_and_post_range(multi):
    frame=raw()
    if multi: frame.columns=pd.MultiIndex.from_product([frame.columns,['TEST']])
    bars,actions=normalize_yahoo(frame,'TEST','America/New_York')
    assert bars.close.tolist()==[100,102,52,53]
    assert bars.volume.tolist()==[1000,1000,2000,2000]
    assert actions[0]['amount']==1
    assert bars[bars.date<=pd.Timestamp('2024-04-02')].close.tolist()==[100,102] # post-range split matters
    assert bars.adjusted_close.tolist()==[49,50,51,52]


def test_reverse_split_and_invalid_shape():
    f=raw();f['Stock Splits']=[0,0,.5,0]
    bars,_=normalize_yahoo(f,'T','America/New_York');assert bars.close.iloc[0]==25
    with pytest.raises(ValueError): normalize_yahoo(f.drop(columns='Dividends'),'T','America/New_York')
    f.loc[f.index[2],['Open','High','Low','Close']]=102
    with pytest.raises(ValueError,match='ambiguous'): normalize_yahoo(f,'T','America/New_York')


def test_provider_options_warmup_and_inclusive(monkeypatch):
    import yfinance
    calls=[]
    class FakeTicker:
        history_metadata=dict(exchangeTimezoneName='America/New_York',currency='USD',instrumentType='EQUITY')
        def __init__(self,symbol): self.symbol=symbol
        def history(self,**kwargs):
            calls.append(kwargs)
            days=data.sessions(kwargs['start'],str(pd.Timestamp.now(tz='America/New_York').date())).tz_localize('America/New_York')
            return pd.DataFrame({k:[100.]*len(days) for k in ['Open','High','Low','Close','Adj Close','Volume']}|{'Dividends':0.,'Stock Splits':0.},index=days)
    monkeypatch.setattr(yfinance,'Ticker',FakeTicker)
    result=YahooProvider().acquire(['VOO','AAPL'],date(2024,4,1),date(2024,4,30),50)
    assert set(result.bars.ticker)=={'VOO','AAPL'}
    assert all(x['warmup_sessions']==51 for x in result.metadata['coverage'].values())
    assert result.bars.date.max()==pd.Timestamp('2024-04-30')
    assert all(not c['auto_adjust'] and not c['repair'] and not c['back_adjust'] and c['timeout']==15 for c in calls)
    assert date.fromisoformat(calls[0]['end'])>date(2024,4,30)


def test_retries_auth_and_schema(monkeypatch):
    monkeypatch.setattr('app.providers.time.sleep',lambda _:None)
    attempts=[]
    def transient(): attempts.append(1);raise httpx.ReadTimeout('timeout')
    with pytest.raises(httpx.ReadTimeout): retry(transient)
    assert len(attempts)==3
    attempts.clear()
    def schema(): attempts.append(1);raise ValueError('schema')
    with pytest.raises(ValueError): retry(schema)
    assert len(attempts)==1


def test_atomic_registration_and_checksums(storage,monkeypatch):
    f,_=fixture(); m=data.register('v1',f,'Synthetic test',actions=[])
    with pytest.raises(ValueError): data.register('v1',f,'new')
    with storage() as db:
        ds=db.get(Dataset,'v1');ds.manifest={**ds.manifest,'actions':[dict(type='split',ratio=2)]};db.commit()
    with pytest.raises(ValueError,match='checksum'): data.load('v1')
    def fail(*_): raise OSError('publication failure')
    monkeypatch.setattr(data.os,'link',fail)
    with pytest.raises(OSError): data.register('v2',f,'Synthetic test')
    with storage() as db: assert db.get(Dataset,'v2') is None
    assert not list(data.ROOT.glob('*.staged'))


def test_snapshot_identity_and_evidence(storage):
    a=disclosure();b=disclosure(source_id='source-2')
    register_snapshot('s',[a,a,b],{'provider':'synthetic test'})
    records,m=load_snapshot('s');assert len(records)==2 and m['owners']==['spouse']
    with pytest.raises(ValueError): register_snapshot('s',[a],{})
    with pytest.raises(ValueError): register_snapshot('conflict',[a,{**a,'ticker':'VOO'}],{})
    with pytest.raises(ValueError): disclosure(publication_evidence='')
    with pytest.raises(ValueError): disclosure(published_at='2024-04-05T08:00:00')
    selected,skipped=selected_records(Config(start='2024-04-01',end='2024-04-30'),[a,disclosure(availability_quality='unverified')])
    assert len(selected)==len(skipped)==1

@pytest.mark.parametrize('timestamp,quality,day,expected',[
    ('2024-04-05T08:00:00-04:00','verified_timestamp',None,'2024-04-05'),
    ('2024-04-05T09:30:00-04:00','verified_timestamp',None,'2024-04-08'),
    ('2024-04-05T17:00:00-04:00','verified_timestamp',None,'2024-04-08'),
    ('2024-04-06T08:00:00-04:00','verified_timestamp',None,'2024-04-08'),
    (None,'verified_date','2024-04-05','2024-04-08')])
async def test_publication_timing(timestamp,quality,day,expected):
    f,m=fixture();m['disclosures']=[disclosure(published_at=timestamp,availability_quality=quality,published_date=day)]
    c=Config(strategy='congressional',disclosure_snapshot='test',start='2024-04-01',end='2024-04-30',universe=['VOO'])
    result=await simulate(c,f,m)
    assert result['trades'][0]['date']==expected
    assert result['trades'][0]['ticker']=='AAPL' # candidate discovery does not expand momentum universe

async def test_amendments_conflicts_and_starting_cash():
    f,m=fixture();m['disclosures']=[disclosure(published_at='2024-03-20T08:00:00-04:00'),disclosure(source_id='2'),disclosure(source_id='3',amends='2',published_at='2024-04-08T08:00:00-04:00'),disclosure(source_id='4',security_type='option')]
    c=Config(strategy='congressional',disclosure_snapshot='s',start='2024-04-01',end='2024-04-30',universe=['VOO'])
    result=await simulate(c,f,m)
    assert len(result['trades'])==1
    assert result['equity'][0]['cash']==c.initial_capital
    assert result['disclosure_counts']['amended']==1
    m['disclosures']=[disclosure(),disclosure(source_id='sell',action='SELL')]
    result=await simulate(c,f,m);assert not result['trades'];assert result['disclosure_counts']['ambiguous']==2

async def test_split_fifo_entitlement_and_restart():
    f,m=fixture();f=f.copy()
    for col in ('open','high','low','close'): f[col]=100.
    f.loc[(f.ticker=='VOO')&(f.date>=pd.Timestamp('2024-04-03')),['open','high','low','close']]=50.
    m['actions']=[dict(date='2024-04-01',ticker='VOO',type='dividend',amount=7),dict(date='2024-04-03',ticker='VOO',type='split',ratio=2),dict(date='2024-04-04',ticker='VOO',type='dividend',amount=1)]
    c=Config(strategy='buy_and_hold',start='2024-04-01',end='2024-04-30',universe=['VOO'],slippage_bps=0)
    saved=[]
    def checkpoint(_,r): saved.append(copy.deepcopy(r));return len(saved)<4
    await simulate(c,f,m,checkpoint)
    full=await simulate(c,f,m);resumed=await simulate(c,f,m,resume=saved[-1])
    assert full['metrics']==resumed['metrics']
    assert full['cash']==2000 # no entitlement on first opening purchase, 2000 post-split shares
    assert full['metrics']['final_value']==102000
    assert [Decimal(v) for v in full['state']['accounting']['lots']['VOO'][0][:2]]==[Decimal(2000),Decimal(50)]
    ledger=Ledger(1000);ledger.fill('buy','X',10,100,0,'2024-04-01');ledger.split('X',2);ledger.fill('sell','X',-20,60,2,'2024-04-04')
    assert ledger.realized==Decimal(198) and not ledger.lots['X']

async def test_split_safe_indicator_and_no_warmup_trades():
    f,m=fixture();c=Config(strategy='momentum',start='2024-04-01',end='2024-04-30',universe=['VOO','AAPL'],rebalance='daily')
    original=await simulate(c,f,m)
    split=f.copy()
    for col in ('open','high','low','close'): split[col]=split[col].astype(float)
    split.loc[(split.ticker=='AAPL')&(split.date>=pd.Timestamp('2024-04-03')),['open','high','low','close']]/=2
    m['actions']=[dict(type='split',ratio=2,ticker='AAPL',date='2024-04-03')]
    result=await simulate(c,split,m)
    assert [[s['action'] for s in d['signals']] for d in result['decisions']]==[[s['action'] for s in d['signals']] for d in original['decisions']]
    assert all(t['date']>'2024-04-01' for t in result['trades'])
    assert result['metrics']['final_value']==pytest.approx(original['metrics']['final_value'])


def test_persisted_three_strategy_and_offline_repeat(storage,tmp_path):
    f,_=fixture();data.register('market',f,'Synthetic test',metadata={'price_basis':'raw'})
    register_snapshot('verified',[disclosure()],{'provider':'synthetic test'})
    settings=dict(dataset='market',disclosure_snapshot='verified',universe=['VOO','AAPL'],start='2024-04-01',end='2024-04-30')
    suite=benchmarks.submit(settings,['buy_and_hold','momentum','congressional'])
    outstanding=benchmarks.wait(suite,0);assert len(outstanding)==3
    for identifier in outstanding: worker.execute(identifier)
    assert benchmarks.report(suite,str(tmp_path/'report.md'))
    _,rows=benchmarks.suite_results(suite)
    assert all(r['status']=='completed' for r in rows)
    second=benchmarks.submit(settings,['buy_and_hold','momentum','congressional'])
    for identifier in benchmarks.wait(second,0): worker.execute(identifier)
    _,repeat=benchmarks.suite_results(second)
    assert [r['result']['metrics'] for r in rows]==[r['result']['metrics'] for r in repeat]
    blocked=benchmarks.submit({**settings,'disclosure_snapshot':None},['buy_and_hold','congressional'])
    _,rows=benchmarks.suite_results(blocked)
    assert rows[1]['status']=='blocked'
    assert not benchmarks.report(blocked,str(tmp_path/'blocked.md'))


def test_missing_prices_warmup_and_nontrading_boundaries(storage):
    f,_=fixture();manifest=data.register('f',f,'Synthetic test')
    c=Config(start='2024-04-01',end='2024-05-04',universe=['VOO','AAPL'])
    validate(c,f,manifest) # Saturday boundary
    with pytest.raises(ValueError,match='warmup'): validate(c,f[f.date>=pd.Timestamp('2024-03-01')],manifest)
    with pytest.raises(ValueError,match='missing'): validate(c,f[f.date!=pd.Timestamp('2024-04-02')],manifest)


def test_quiver_pagination_and_auth(monkeypatch):
    monkeypatch.setattr('app.providers.time.sleep',lambda _:None)
    raw_record=dict(BioGuideID='P000197',Traded='2024-01-02',Filed='2024-02-01',Ticker='AAPL',TickerType='CS',Transaction='Purchase')
    calls=[]
    def handle(request):
        calls.append(request)
        return httpx.Response(200,json=[raw_record] if request.url.params['page']=='1' else [])
    client=httpx.Client(transport=httpx.MockTransport(handle))
    records,meta=QuiverProvider('test',client).acquire('P000197')
    assert len(calls)==2 and records[0]['availability_quality']=='unverified' and not records[0]['identity_verified']
    assert calls[0].headers['Authorization']=='Bearer test'
    client=httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json=[raw_record])))
    with pytest.raises(ValueError,match='repeated'): QuiverProvider('test',client).acquire('P000197')
    client=httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(403,json={})))
    with pytest.raises(httpx.HTTPStatusError): QuiverProvider('test',client).acquire('P000197')
    with pytest.raises(ValueError): QuiverProvider('')


def test_additive_migration_preserves_legacy(tmp_path):
    import os
    import subprocess
    from sqlalchemy import inspect
    database=tmp_path/'migration.db'
    old=create_engine('sqlite:///'+str(database))
    tables=[t for t in Base.metadata.sorted_tables if t.name not in ('disclosure_snapshots','benchmark_suites')]
    Base.metadata.create_all(old,tables=tables)
    with old.begin() as db:
        db.execute(Dataset.__table__.insert().values(id='legacy',manifest={'price_basis':'raw','provenance':'legacy'}))
        db.exec_driver_sql('CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)')
        db.exec_driver_sql("INSERT INTO alembic_version VALUES ('001')")
    subprocess.run([__import__('sys').executable,'-m','alembic','upgrade','head'],env={**os.environ,'DATABASE_URL':'sqlite:///'+str(database)},check=True,capture_output=True)
    assert {'disclosure_snapshots','benchmark_suites'}.issubset(inspect(old).get_table_names())
    with old.connect() as db:
        assert db.execute(Dataset.__table__.select()).first().id=='legacy'
        assert db.exec_driver_sql('SELECT version_num FROM alembic_version').scalar()=='002'


async def test_reinvestment_costs_and_independent_voo_return():
    f,m=fixture()
    for col in ('open','high','low','close'): f[col]=100.
    m['actions']=[dict(type='dividend',ticker='VOO',date='2024-04-03',amount=2)]
    c=Config(strategy='buy_and_hold',start='2024-04-01',end='2024-04-05',universe=['VOO'],initial_capital=10000,fee=1,slippage_bps=10,reinvest_dividends=True)
    result=await simulate(c,f,m)
    first=(10000-1)/100.1
    dividend=first*2
    extra=(dividend-1)/100.1
    assert result['positions']['VOO']==pytest.approx(first+extra)
    assert result['metrics']['final_value']==pytest.approx((first+extra)*100)
    assert result['metrics']['transaction_costs']==2
    assert result['trades'][1]['date']=='2024-04-03'


def test_ownership_filter_and_unknown_preservation(storage):
    records=[disclosure(owner=owner,source_id=owner) for owner in ('self','spouse','dependent','joint','unknown')]
    register_snapshot('owners',records,{})
    frozen,manifest=load_snapshot('owners')
    selected,skips=selected_records(Config(start='2024-04-01',end='2024-04-30',owners=['unknown']),frozen)
    assert len(selected)==1 and selected[0]['owner']=='unknown' and len(skips)==4
    assert 'unknown' in manifest['owners']


def test_cli_overrides_and_default_strategies(storage,tmp_path,monkeypatch):
    from app import cli
    f,_=fixture();data.register('market',f,'test')
    config=tmp_path/'config.json';config.write_text(__import__('json').dumps(dict(dataset='market',strategies=['buy_and_hold','momentum'],universe=['VOO','AAPL'],start='2024-04-01',end='2024-04-30',fee=7)))
    monkeypatch.setattr(cli,'engine',storage.kw['bind'])
    assert cli.main(['benchmark','--config',str(config),'--fee','2','--strategies','buy_and_hold','--output',str(tmp_path/'report.md')])==2
    with storage() as db:
        from sqlalchemy import select
        row=db.scalar(select(Experiment))
        assert row.config['fee']==2 and row.config['strategy']=='buy_and_hold' and row.status=='queued'

async def test_equal_targets_reduce_existing_positions():
    f,m=fixture()
    for col in ('open','high','low','close'): f[col]=100.
    m['disclosures']=[disclosure(published_at='2024-04-01T08:00:00-04:00'),disclosure(source_id='second',ticker='VOO',published_at='2024-04-02T08:00:00-04:00')]
    c=Config(strategy='congressional',disclosure_snapshot='s',start='2024-04-01',end='2024-04-03',universe=['VOO'],max_position_weight=1,slippage_bps=0)
    result=await simulate(c,f,m)
    assert result['positions']=={'AAPL':500,'VOO':500}
    assert result['metrics']['realized_pnl']==0


def test_acquisition_registration_suite_worker_report(storage,tmp_path,monkeypatch):
    import yfinance
    class Fake:
        history_metadata={'currency':'USD','exchangeTimezoneName':'America/New_York','instrumentType':'ETF'}
        def __init__(self,_): pass
        def history(self,**kwargs):
            days=data.sessions(kwargs['start'],str(pd.Timestamp.now(tz='America/New_York').date())).tz_localize('America/New_York')
            return pd.DataFrame({k:100. for k in ('Open','High','Low','Close','Adj Close','Volume')}|{'Dividends':0.,'Stock Splits':0.},index=days)
    monkeypatch.setattr(yfinance,'Ticker',Fake)
    downloaded=YahooProvider().acquire(['VOO'],date(2024,4,1),date(2024,4,30),50)
    data.register('download',downloaded.bars,'Synthetic mock provider',actions=downloaded.actions,metadata=downloaded.metadata)
    suite=benchmarks.submit(dict(dataset='download',start='2024-04-01',end='2024-04-30',universe=['VOO']),['buy_and_hold','momentum'])
    for identifier in benchmarks.wait(suite,0): worker.execute(identifier)
    assert benchmarks.report(suite,str(tmp_path/'report.md'))
