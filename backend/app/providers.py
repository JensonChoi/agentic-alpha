"""Acquisition only: no registration or simulation side effects."""
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol, Callable, TypeVar
import time
import numpy as np
import pandas as pd
import exchange_calendars as xcals
import httpx
from .provenance import digest

T = TypeVar('T')

def retry(call: Callable[[], T]) -> T:
    for attempt in range(3):
        try:
            return call()
        except Exception as exc:
            status = getattr(getattr(exc, 'response', None), 'status_code', None)
            transient = isinstance(exc, (httpx.TimeoutException, httpx.TransportError, TimeoutError, ConnectionError)) or status == 429 or (status is not None and status >= 500) or type(exc).__name__ in ('YFRateLimitError', 'Timeout', 'ConnectionError')
            if not transient or attempt == 2: raise
            time.sleep(.5 * 2 ** attempt)
    raise AssertionError('unreachable')

@dataclass
class MarketDownload:
    bars: pd.DataFrame
    actions: list[dict]
    metadata: dict

class MarketProvider(Protocol):
    def acquire(self, symbols: list[str], start: date, end: date, long_window: int) -> MarketDownload: ...

class DisclosureProvider(Protocol):
    def acquire(self, member_id: str) -> tuple[list[dict], dict]: ...


def normalize_yahoo(frame: pd.DataFrame, symbol: str, timezone: str) -> tuple[pd.DataFrame, list[dict]]:
    """Undo Yahoo's split basis through the entire fetched adjustment horizon.

    OHLC and distributions multiply by subsequent split ratios; volume divides.
    Adjusted close is retained for inspection only. Same-day splits already use
    post-split units. Capital gains distributions are unsupported (fail closed).
    """
    frame = frame.copy()
    if isinstance(frame.columns, pd.MultiIndex):
        if symbol not in frame.columns.get_level_values(-1): raise ValueError('Unexpected Yahoo column shape')
        frame = frame.xs(symbol, axis=1, level=-1)
    required = {'Open','High','Low','Close','Volume','Dividends','Stock Splits','Adj Close'}
    if frame.empty or not required.issubset(frame.columns): raise ValueError(f'{symbol}: empty or invalid Yahoo schema')
    if frame.index.tz is None: raise ValueError('Yahoo session timezone missing')
    frame.index = frame.index.tz_convert(timezone).tz_localize(None).normalize()
    frame = frame.sort_index()
    if frame.index.has_duplicates: raise ValueError('Duplicate Yahoo sessions')
    if not np.isfinite(frame[list(required)].to_numpy(dtype=float)).all(): raise ValueError('Nonfinite Yahoo data')
    if (frame[['Open','High','Low','Close']] <= 0).any().any() or (frame.Volume < 0).any(): raise ValueError('Invalid Yahoo prices or volume')
    if (frame.High < frame[['Open','Close','Low']].max(axis=1)).any() or (frame.Low > frame[['Open','Close']].min(axis=1)).any(): raise ValueError('Invalid Yahoo OHLC ranges')
    if (frame['Stock Splits'] < 0).any() or (frame.Dividends < 0).any(): raise ValueError('Invalid Yahoo action')
    if 'Capital Gains' in frame and (frame['Capital Gains'] != 0).any(): raise ValueError('Unsupported capital gains distributions')
    splits = frame['Stock Splits'].replace(0, 1)
    factor = splits.iloc[::-1].cumprod().iloc[::-1] / splits
    # Reject a conspicuous unadjusted split discontinuity instead of repairing it.
    for i in range(1, len(frame)):
        ratio = splits.iloc[i]
        if ratio != 1:
            jump = frame.Close.iloc[i-1] / frame.Open.iloc[i]
            if abs(np.log(jump / ratio)) < abs(np.log(jump)) and abs(np.log(jump)) > .3:
                raise ValueError(f'{symbol}: ambiguous split adjustment at {frame.index[i].date()}')
    for col in ('Open','High','Low','Close','Dividends'): frame[col] *= factor
    frame['Volume'] = frame['Volume'] / factor
    actions = []
    for day, row in frame.iterrows():
        for kind, field in [('split','Stock Splits'),('dividend','Dividends')]:
            if row[field]:
                actions.append(dict(id=f'yahoo:{symbol}:{day.date()}:{kind}', date=str(day.date()), ticker=symbol, type=kind, **{('ratio' if kind=='split' else 'amount'):float(row[field])}))
    bars = frame.rename(columns={'Open':'open','High':'high','Low':'low','Close':'close','Volume':'volume','Adj Close':'adjusted_close'}).reset_index(names='date')
    bars['ticker'] = symbol
    return bars[['date','ticker','open','high','low','close','volume','adjusted_close']], actions

class YahooProvider:
    def acquire(self, symbols: list[str], start: date, end: date, long_window: int = 50) -> MarketDownload:
        import yfinance as yf
        if not symbols or len(set(symbols)) != len(symbols): raise ValueError('Provide distinct symbols')
        if end < start or not 3 <= long_window <= 500: raise ValueError('Invalid range or long window')
        calendar = xcals.get_calendar('XNYS', start=str(start-timedelta(days=long_window*3+30)))
        now = pd.Timestamp.now(tz='UTC')
        horizon = now.tz_convert('America/New_York').date()
        requested = calendar.sessions_in_range(str(start), str(end))
        if not len(requested): raise ValueError('No requested sessions')
        if calendar.session_close(requested[-1]) > now: raise ValueError('Requested range contains incomplete sessions')
        preceding = calendar.sessions_in_range(str(start-timedelta(days=long_window*3+30)), str(start-timedelta(days=1)))
        first = preceding[-(long_window+1)]
        frames, actions, coverage = [], [], {}
        adjustment_events, response_hashes = {}, {}
        for symbol in symbols:
            ticker = yf.Ticker(symbol)
            # Fetch through today, not benchmark end: Yahoo adjusts past rows for later splits.
            raw = retry(lambda: ticker.history(start=str(first.date()), end=str(horizon+timedelta(days=1)), interval='1d', auto_adjust=False, back_adjust=False, repair=False, actions=True, keepna=True, rounding=False, timeout=15, raise_errors=True))
            meta = ticker.history_metadata
            if meta.get('exchangeTimezoneName') != 'America/New_York' or meta.get('currency') != 'USD' or meta.get('instrumentType') not in ('EQUITY','ETF'):
                raise ValueError(f'{symbol}: only USD US exchange stocks/ETFs with established session conventions are supported')
            bars, all_actions = normalize_yahoo(raw, symbol, meta['exchangeTimezoneName'])
            adjustment_events[symbol] = all_actions
            response_hashes[symbol] = digest(raw.to_json(date_format='iso'))
            valid = calendar.sessions_in_range(str(first.date()), str(horizon))
            complete = {d for d in valid if calendar.session_close(d) <= now}
            if not complete or bars.date.max() < max(complete): raise ValueError(f'{symbol}: incomplete adjustment horizon; cannot reconstruct historical share units')
            # Current-day actions participate in adjustment reversal, but incomplete bars never publish.
            bars = bars[(bars.date <= pd.Timestamp(end)) & bars.date.isin(complete)]
            warmup = bars[bars.date < pd.Timestamp(start)]
            benchmark = bars[bars.date >= pd.Timestamp(start)]
            if len(warmup) < long_window+1 or benchmark.empty: raise ValueError(f'{symbol}: insufficient warmup or benchmark coverage')
            if benchmark.date.min() > requested[0] or benchmark.date.max() < requested[-1]: raise ValueError(f'{symbol}: incomplete boundary coverage')
            expected = calendar.sessions_in_range(str(first.date()), str(end))
            missing = [str(d.date()) for d in expected if d not in set(bars.date)]
            coverage[symbol] = dict(start=str(bars.date.min().date()), end=str(bars.date.max().date()), warmup_sessions=len(warmup), missing_sessions=missing)
            frames.append(bars)
            actions.extend(a for a in all_actions if a['date'] <= str(end))
        return MarketDownload(pd.concat(frames, ignore_index=True), actions, dict(provider='yahoo', library_version=yf.__version__, retrieved_at=now.isoformat(), requested_symbols=symbols, requested_start=str(start), requested_end=str(end), adjustment_horizon=str(horizon), adjustment_events=adjustment_events, source_response_sha256=response_hashes, coverage=coverage, price_basis='raw', original_basis='Yahoo split-adjusted OHLC, volume and distributions; Adj Close includes dividends', normalized_basis='OHLC/dividends multiplied by subsequent split product; volume divided; explicit actions', action_timing='Splits before open; dividends on pre-open holdings, ex-date cash-credit approximation', warnings=['Unofficial Yahoo access; provider terms apply', 'Fixed universe: survivorship and selection bias; no delisting or historical membership guarantees'] + (['Missing sessions present; strict preflight will reject affected runs'] if any(v['missing_sessions'] for v in coverage.values()) else [])))

class QuiverProvider:
    """Documented V2 bulk endpoint. Upload/filing times are not publication proof.

    V2 does not document a stable source transaction ID or revision chain. Keep
    every raw row with an acquisition-local locator, explicitly non-executable.
    """
    def __init__(self, token: str, client: httpx.Client | None = None):
        if not token: raise ValueError('QUIVER_API_KEY is required; historical access may require a subscription')
        self.token, self.client = token, client

    def acquire(self, member_id: str) -> tuple[list[dict], dict]:
        raw, fingerprints = [], set()
        with httpx.Client(timeout=20) if self.client is None else _borrow(self.client) as client:
            for page in range(1, 101):
                def request():
                    response = client.get('https://api.quiverquant.com/beta/bulk/congresstrading', params=dict(version='V2', bioguide_id=member_id, page=page, page_size=100, nonstock='true'), headers={'Authorization':'Bearer '+self.token})
                    response.raise_for_status()
                    return response.json()
                batch = retry(request)
                if not isinstance(batch, list): raise ValueError('Unexpected Quiver pagination/schema; no snapshot published')
                if not batch: break
                fingerprint = digest(batch)
                if fingerprint in fingerprints: raise ValueError('Quiver repeated a page; pagination incomplete')
                fingerprints.add(fingerprint)
                for row in batch:
                    if not isinstance(row, dict) or not all(k in row for k in ('BioGuideID','Traded','Filed')): raise ValueError('Invalid Quiver V2 schema')
                    if row['BioGuideID'] != member_id: raise ValueError('Quiver member coverage mismatch')
                    raw.append(row)
            else: raise ValueError('Quiver pagination exceeded 100 pages; snapshot incomplete')
        if not raw: raise ValueError('No Quiver records; historical entitlement or coverage unavailable')
        retrieved = pd.Timestamp.now(tz='UTC').isoformat()
        records = []
        for i, row in enumerate(raw):
            records.append(dict(source_id=f'acquisition-row:{i}', revision='unverified', member_id=member_id, owner='unknown', ticker=row.get('Ticker') or '', security_type={'CS':'stock','ST':'stock','ETF':'etf'}.get(row.get('TickerType'),'unsupported'), action={'Purchase':'BUY','Sale':'SELL'}.get(row.get('Transaction'),'UNSUPPORTED'), transaction_date=str(pd.Timestamp(row['Traded']).date()), filing_date=str(pd.Timestamp(row['Filed']).date()), availability_quality='unverified', identity_verified=False, ingested_at=retrieved, original=row))
        return records, dict(provider='quiver', retrieved_at=retrieved, member_id=member_id, coverage='Provider advertises history from 2014; completeness and revision history not established', warnings=['V2 has no documented stable transaction identity, owner classification or verified publication evidence; records cannot drive realistic copying', 'Source upload and last_modified timestamps retained only in originals; not publication timestamps'], terms='https://www.quiverquant.com/terms-of-service')

from contextlib import contextmanager
@contextmanager
def _borrow(client):
    yield client
