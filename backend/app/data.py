import hashlib
import os
from pathlib import Path
import numpy as np
import pandas as pd
import exchange_calendars as xcals
from .db import Dataset, Session, DisclosureRow

ROOT = Path(os.getenv('DATA_DIR', './datasets'))
def sessions(start, end):
    return xcals.get_calendar('XNYS').sessions_in_range(str(start), str(end)).tz_localize(None)
def register(name, frame, provenance, synthetic=False, disclosures=None, actions=None):
    if not name.replace('-', '').replace('_', '').isalnum(): raise ValueError('Invalid dataset identifier')
    for d in disclosures or []:
        for key in ('id','ticker','action','transaction_date','disclosure_date','security_type','value_low','value_high','provenance'):
            if key not in d: raise ValueError('Disclosure missing '+key)
        if d['action'] not in ('BUY','SELL'): raise ValueError('Invalid disclosure action')
        if pd.Timestamp(d['transaction_date'])>pd.Timestamp(d['disclosure_date']): raise ValueError('Disclosure precedes transaction')
        if d['value_low']<0 or d['value_high']<d['value_low']: raise ValueError('Invalid disclosure value range')
    for a in actions or []:
        if a.get('type') not in ('split','dividend'): raise ValueError('Unsupported corporate action')
        if a.get('type')=='split' and a.get('ratio',0)<=0: raise ValueError('Split ratio must be positive')
        if a.get('type')=='dividend' and a.get('amount',-1)<0: raise ValueError('Dividend must be nonnegative')
    required = {'date','ticker','open','high','low','close','volume'}
    if not required.issubset(frame.columns): raise ValueError(f'Required columns: {sorted(required)}')
    frame = frame.copy()
    frame['date'] = pd.to_datetime(frame.date).dt.normalize()
    if frame.duplicated(['date','ticker']).any(): raise ValueError('Duplicate bars')
    if not np.isfinite(frame[['open','high','low','close','volume']].to_numpy(dtype=float)).all(): raise ValueError('Nonfinite bars')
    if (frame[['open','high','low','close']] <= 0).any().any(): raise ValueError('Prices must be positive')
    if (frame.high < frame[['open','close','low']].max(axis=1)).any() or (frame.low > frame[['open','close']].min(axis=1)).any(): raise ValueError('Invalid OHLC range')
    if (frame.volume < 0).any(): raise ValueError('Negative volume')
    frame = frame.sort_values(['date','ticker'])
    ROOT.mkdir(parents=True, exist_ok=True)
    with Session() as db:
        if db.get(Dataset, name): raise ValueError('Dataset identifiers are immutable; import a new version')
        path = ROOT / f'{name}.parquet'
        frame.to_parquet(path, index=False)
        manifest = dict(provenance=provenance, synthetic=synthetic, sha256=hashlib.sha256(path.read_bytes()).hexdigest(), price_basis='raw', disclosures=disclosures or [], actions=actions or [], start=str(frame.date.min().date()), end=str(frame.date.max().date()), symbols=sorted(frame.ticker.unique().tolist()))
        db.add(Dataset(id=name, manifest=manifest)); db.flush()
        for disclosure in disclosures or []: db.merge(DisclosureRow(dataset_id=name,source_id=disclosure['id'],payload=disclosure))
        db.commit()
    return manifest

def load(name):
    with Session() as db:
        ds = db.get(Dataset, name)
        if not ds: raise ValueError('Unknown dataset')
        manifest = ds.manifest
    path = ROOT / f'{name}.parquet'
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest['sha256']: raise ValueError('Dataset checksum mismatch')
    return pd.read_parquet(path), manifest

def seed_demo():
    with Session() as db:
        if db.get(Dataset, 'demo'): return
    rng = np.random.default_rng(42); rows = []
    for ticker in ['VOO','AAPL','MSFT','NVDA']:
        price = 100.
        for d in sessions('2024-01-02','2024-12-31'):
            op = price * np.exp(rng.normal(0,.003)); price = op * np.exp(rng.normal(.0004,.015))
            rows.append(dict(date=d,ticker=ticker,open=op,close=price,high=max(op,price)*1.005,low=min(op,price)*.995,volume=1000000))
    disclosures = [dict(id='fictional-1',person='Fictional Demo Legislator',ticker='AAPL',action='BUY',transaction_date='2024-03-01',disclosure_date='2024-04-10',security_type='stock',value_low=15000,value_high=50000,provenance='Synthetic demonstration; not a real disclosure'),dict(id='fictional-2',person='Fictional Demo Legislator',ticker='AAPL',action='SELL',transaction_date='2024-08-01',disclosure_date='2024-09-10',security_type='stock',value_low=15000,value_high=50000,provenance='Synthetic demonstration; not a real disclosure')]
    register('demo', pd.DataFrame(rows), 'Seeded synthetic prices; not historical market performance', True, disclosures)
