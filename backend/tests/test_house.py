"""Synthetic House sources only. Historical evidence is explicitly fictional."""
from datetime import date
from io import BytesIO
import json
import zipfile
import httpx
import pytest
from app import benchmarks, worker
from app.house import parse_pdf, parse_index, HouseProvider, ingest, correct_snapshot, MAX_BYTES
from app.disclosures import load_snapshot
from house_fixtures import pdf, index, bundle
from test_real_data import storage, disclosure

DOC = dict(document_id='900001',filing_date='2024-04-01',source_url='https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2024/900001.pdf',retrieved_at='2024-04-02T00:00:00Z')


def test_layout_wrapping_pages_owners_and_distinct_identity():
    rows = [dict(owner=owner,ticker='AAPL') for owner in ('SP','DC','JT','')]
    result = parse_pdf(pdf(rows,pages=2), DOC)
    assert not result['quarantines']
    assert [r['owner'] for r in result['records'][:4]] == ['spouse','dependent','joint','unknown']
    assert len({r['source_id'] for r in result['records']}) == 8
    assert all(r['availability_quality']=='unverified' and r['published_at'] is None and r['value_low']==1001 and r['value_high']==15000 for r in result['records'])
    assert all(r['original']['bbox'] and 'Synthetic wrapped company' in r['original']['original_text'] for r in result['records'])


@pytest.mark.parametrize('row,reason',[(dict(owner='X'),'owner'),(dict(ticker=''),'ticker'),(dict(status='Amended'),'Amendment'),(dict(action='Q'),'transaction type')])
def test_uncertain_rows_quarantined(row,reason):
    result=parse_pdf(pdf([row]),DOC)
    assert not result['records'] and reason in result['quarantines'][0]['reason']


@pytest.mark.parametrize('row',[dict(code='OP'),dict(note='Exercised options'),dict(action='E'),dict(note='Gift of shares'),dict(code='PS')])
def test_unsupported_assets_never_become_stock_purchases(row):
    result=parse_pdf(pdf([row]),DOC)
    assert not result['quarantines']
    record=result['records'][0]
    assert record['security_type']=='unsupported' or record['action']=='UNSUPPORTED'


def test_invalid_scanned_and_resource_limits():
    for raw in (b'<html>denied',b'%PDF-'+b' '*MAX_BYTES):
        with pytest.raises(ValueError):parse_pdf(raw,DOC)
    with pytest.raises(ValueError,match='page limit'):parse_pdf(pdf(pages=2),DOC,max_pages=1)
    assert parse_pdf(pdf(scanned=True),DOC)['quarantines']
    assert parse_pdf(pdf(docid='900002'),DOC)['quarantines']


def test_index_exact_identity_archive_safety_and_schema():
    rows,total=parse_index(index(),2024,'P000197')
    assert len(rows)==total==1 and rows[0]['filing_date']=='2024-04-01'
    assert not parse_index(index(first='Other'),2024,'P000197')[0]
    with pytest.raises(ValueError):parse_index(index(),2024,'wrong')
    raw=BytesIO()
    with zipfile.ZipFile(raw,'w') as z:z.writestr('../2024FD.xml','bad')
    with pytest.raises(ValueError,match='Unsafe'):parse_index(raw.getvalue(),2024,'P000197')
    with pytest.raises(ValueError,match='Missing'):parse_index(index(year=2025),2024,'P000197')


def test_retries_throttling_denial_and_limits(monkeypatch):
    waits=[];monkeypatch.setattr('app.house.time.sleep',waits.append)
    calls=[]
    def handle(request):
        calls.append(request)
        return httpx.Response(429,headers={'Retry-After':'2'}) if len(calls)<3 else httpx.Response(200,content=b'ok',headers={'content-type':'application/pdf'})
    provider=HouseProvider(client=httpx.Client(transport=httpx.MockTransport(handle)))
    assert provider.fetch(DOC['source_url'])==b'ok' and len(calls)==3 and waits.count(2)==2
    for status in (403,302):
        provider.client=httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(status)))
        with pytest.raises(httpx.HTTPStatusError):provider.fetch(DOC['source_url'])
    provider.client=httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,content=b'x'*(MAX_BYTES+1),headers={'content-type':'application/pdf'})))
    with pytest.raises(ValueError,match='byte limit'):provider.fetch(DOC['source_url'])
    with pytest.raises(ValueError):provider.fetch('https://example.com')


def imported(storage,tmp_path,**kwargs):
    b=bundle(tmp_path/'input',**kwargs)
    m=ingest('house','P000197',date(2024,1,1),date(2024,12,31),str(tmp_path/'artifacts'),'SYNTHETIC fixture',b)
    return b,m


def test_ingestion_integrity_collisions_review_and_incomplete(storage,tmp_path):
    b,m=imported(storage,tmp_path)
    assert m['schema_version']==2 and m['counts']['documents']==1
    records,_=load_snapshot('house');assert len(records)==1
    assert (tmp_path/'artifacts/house/review.json').exists()
    with pytest.raises(FileExistsError):ingest('house','P000197',date(2024,1,1),date(2024,12,31),str(tmp_path/'artifacts'),'test',b)
    b['documents']=[]
    with pytest.raises(ValueError,match='Incomplete acquisition'):ingest('missing','P000197',date(2024,1,1),date(2024,12,31),str(tmp_path/'artifacts'),'test',b)
    with pytest.raises(ValueError,match='Unknown'):load_snapshot('missing')
    path=tmp_path/'artifacts/house/900001.pdf';path.write_bytes(path.read_bytes()+b'changed')
    with pytest.raises(ValueError,match='artifact checksum'):load_snapshot('house')


def test_evidence_corrections_revision_and_blocked_suite(storage,tmp_path):
    from app import data
    from test_engine import fixture
    imported(storage,tmp_path)
    records,m=load_snapshot('house');key=records[0]['source_id']
    correction=dict(source_id=key,reviewer='Synthetic fixture author',evidence='Synthetic test only',publication_basis='filing_date',changes=dict(availability_quality='verified_date',published_date='2024-04-01',publication_evidence='Synthetic evidence'))
    with pytest.raises(ValueError,match='not historical'):correct_snapshot('house','bad',[correction],'test')
    correction['publication_basis']='synthetic_fixture'
    correct_snapshot('house','reviewed',[correction],'SYNTHETIC fixture')
    amended,_=load_snapshot('reviewed');assert amended[0]['original']['previous_record']==records[0]
    assert load_snapshot('house')[0]==records
    f,_=fixture();data.register('market',f,'Synthetic',metadata={'price_basis':'raw'})
    settings=dict(dataset='market',start='2024-04-01',end='2024-04-30',strategy_settings={'buy_and_hold':{'universe':['VOO']},'momentum':{'universe':['VOO'],'fee':7},'congressional':{'disclosure_snapshot':'reviewed','universe':['VOO']}})
    suite=benchmarks.submit(settings,['buy_and_hold','momentum','congressional'],{'fee':2})
    for i in benchmarks.wait(suite,0):worker.execute(i)
    _,rows=benchmarks.suite_results(suite)
    assert all(r['status']=='completed' and r['config']['fee']==2 for r in rows)
    assert rows[1]['config']['universe']==['VOO'] and rows[0]['config']['max_position_weight']==1
    assert benchmarks.report(suite,str(tmp_path/'report.md'))
    settings['strategy_settings']['congressional']['disclosure_snapshot']='house'
    blocked=benchmarks.submit(settings,['congressional'])
    _,rows=benchmarks.suite_results(blocked)
    assert rows[0]['status']=='blocked' and rows[0]['disclosure_provenance']['counts']['unverified']==1


def test_changed_document_bytes_require_identity_review(storage,tmp_path):
    b,_=imported(storage,tmp_path)
    from pathlib import Path
    Path(b['documents'][0]['path']).write_bytes(pdf([dict(ticker='VOO')]))
    m=ingest('changed','P000197',date(2024,1,1),date(2024,12,31),str(tmp_path/'artifacts'),'Synthetic revised file',b)
    assert m['counts']['quarantines']==1 and m['count']==0


async def test_alphabetical_cap_audit_and_no_future_universe_leakage():
    from test_engine import fixture
    from app.engine import simulate
    from app.contracts import Config
    import pandas as pd
    f,m=fixture()
    tickers=['AAPL','B','C','D','E','F']
    f=pd.concat([f]+[f[f.ticker=='AAPL'].assign(ticker=t) for t in tickers[1:]])
    m['disclosures']=[disclosure(source_id=t,ticker=t) for t in tickers]
    c=Config(strategy='congressional',disclosure_snapshot='s',start='2024-04-01',end='2024-04-30',max_position_weight=.2)
    result=await simulate(c,f,m)
    assert 'F' not in {t['ticker'] for t in result['trades']}
    assert any(d.get('ticker')=='F' and 'alphabetical' in d['reason'] for d in result['disclosure_audit'])
    momentum=await simulate(c.model_copy(update={'strategy':'momentum','universe':['VOO']}),f,m)
    assert all(t['ticker']=='VOO' for t in momentum['trades'])


def test_split_notes_and_cross_page_continuation():
    result=parse_pdf(pdf([dict(action='S (partial)')], pages=2, split_notes=True, continuation=True), DOC)
    assert not result['quarantines']
    assert len(result['records'])==1
    record=result['records'][0]
    assert record['action']=='UNSUPPORTED'
    assert record['original']['sale_description']=='S (partial)'
    assert record['original']['continuations'][0]['page']==2


def test_acquisition_failure_preserves_discovery_and_no_registration(storage,tmp_path,monkeypatch):
    monkeypatch.setattr('app.house.time.sleep',lambda _:None)
    def handle(request):
        url=str(request.url)
        if url.endswith('ViewReport'):return httpx.Response(200,content=b'/public_disc/financial-pdfs/2024FD.zip')
        if url.endswith('.zip'):return httpx.Response(200,content=index())
        return httpx.Response(404)
    provider=HouseProvider(client=httpx.Client(transport=httpx.MockTransport(handle)))
    with pytest.raises(httpx.HTTPStatusError):
        ingest('failed','P000197',date(2024,1,1),date(2024,12,31),str(tmp_path),'test',provider=provider)
    assert json.loads((tmp_path/'failed/2024.discovery.json').read_text())['expected_documents']==['900001']
    assert (tmp_path/'failed/failure.json').exists()
    with pytest.raises(ValueError,match='Unknown'):load_snapshot('failed')


def test_amendment_evidence_and_invalid_links(storage,tmp_path):
    imported(storage,tmp_path,rows=[dict(ticker='AAPL'),dict(ticker='AAPL',status='Amended')])
    records,m=load_snapshot('house')
    original=records[0]['source_id'];key=m['quarantines'][0]['source_id']
    correction=dict(source_id=key,reviewer='Synthetic reviewer',evidence='Synthetic row mapping',changes={k:v for k,v in disclosure(amends=original).items() if k not in ('source_id','original','revision')},publication_basis='synthetic_fixture')
    with pytest.raises(ValueError,match='Amendment requires'):correct_snapshot('house','bad-link',[correction],'Synthetic')
    correction['amendment_evidence']='Synthetic original and corrected document row correspondence'
    correct_snapshot('house','linked',[correction],'Synthetic')
    revised,_=load_snapshot('linked')
    assert next(d for d in revised if d['source_id']==key)['amends']==original

async def test_house_amendment_checkpoint_restart_no_replay():
    import copy
    from test_engine import fixture
    from app.engine import simulate
    from app.contracts import Config
    f,m=fixture()
    m['disclosures']=[disclosure(source_id='house:original',published_date='2024-04-01',published_at=None,availability_quality='verified_date'),disclosure(source_id='house:amended',amends='house:original',published_date='2024-04-08',published_at=None,availability_quality='verified_date')]
    c=Config(strategy='congressional',disclosure_snapshot='synthetic',start='2024-04-01',end='2024-04-30')
    saved=[]
    def checkpoint(_,result):
        saved.append(copy.deepcopy(result))
        return len(saved)<4
    await simulate(c,f,m,checkpoint)
    full=await simulate(c,f,m)
    restarted=await simulate(c,f,m,resume=saved[-1])
    assert restarted['trades']==full['trades'] and len(full['trades'])==1
    assert restarted['metrics']==full['metrics']
    assert restarted['disclosure_counts']['amended']==1


def test_duplicate_index_retrieval_keeps_document_identity():
    from app.house import parse_index
    raw=BytesIO()
    with zipfile.ZipFile(BytesIO(index())) as z:
        xml=z.read('2024FD.xml').decode()
    member=xml.removeprefix('<FinancialDisclosure>').removesuffix('</FinancialDisclosure>')
    with zipfile.ZipFile(raw,'w') as z:z.writestr('2024FD.xml','<FinancialDisclosure>'+member+member+'</FinancialDisclosure>')
    rows,total=parse_index(raw.getvalue(),2024,'P000197')
    assert len(rows)==1 and total==2
