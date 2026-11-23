"""Immutable, point-in-time evidence and read-only agent retrieval."""
import json
from math import isclose
from typing import Literal
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field
from .provenance import digest

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class EvidenceRecord(Strict):
    id: str = Field(min_length=1, max_length=100)
    revision: int = Field(default=1, ge=1)
    ticker: str = Field(min_length=1, max_length=20)
    kind: Literal['news', 'fundamentals']
    published_at: str
    available_at: str
    provenance: str = Field(min_length=1, max_length=500)
    text: str = Field(default='', max_length=2000)
    metric: Literal['revenue', 'net_income', 'eps', 'debt_to_equity', 'pe_ratio'] | None = None
    value: float | None = None
    unit: str = Field(default='', max_length=40)


def validate_records(records):
    result = []; seen = set()
    for raw in records:
        row = EvidenceRecord.model_validate(raw)
        published, available = pd.Timestamp(row.published_at), pd.Timestamp(row.available_at)
        if published.tzinfo is None or available.tzinfo is None or available < published:
            raise ValueError('Evidence requires timezone-aware publication and availability timestamps')
        if row.kind == 'fundamentals' and (row.metric is None or row.value is None or not row.unit):
            raise ValueError('Fundamentals require metric, value and unit')
        key = (row.kind, row.ticker, row.id, row.revision)
        if key in seen: raise ValueError('Duplicate evidence revision')
        seen.add(key); result.append(row.model_dump())
    return result

class ToolRequest(Strict):
    name: Literal['prices','indicators','positions','cash','news','fundamentals','rules']
    ticker: str | None = Field(default=None, max_length=20)
    rows: int = Field(default=20, ge=1, le=100)


def snapshot(config, history, manifest, portfolio, curve, day):
    import exchange_calendars as xcals
    cutoff = xcals.get_calendar('XNYS').session_close(day).isoformat()
    indicators = {}; screening = []
    for ticker in sorted(config.universe):
        h = history[history.ticker == ticker].sort_values('date').close
        reason = 'insufficient_warmup'
        if len(h) >= config.long_window + 1 and not history[(history.ticker == ticker) & (history.date == day)].empty:
            momentum = float(h.iloc[-1] / h.iloc[-config.long_window-1] - 1)
            indicators[ticker] = dict(close=float(h.iloc[-1]), short=float(h.tail(config.short_window).mean()), long=float(h.tail(config.long_window).mean()), momentum=momentum, volatility=float(h.pct_change().tail(config.long_window).std()*252**.5), units='prices USD; momentum fraction; volatility annualized fraction', cutoff=cutoff)
            reason = 'eligible' if indicators[ticker]['short'] > indicators[ticker]['long'] and momentum > 0 else 'entry_conditions_failed'
        screening.append(dict(ticker=ticker, reason=reason))
    ranked = sorted((r['ticker'] for r in screening if r['reason']=='eligible'), key=lambda t: (-indicators[t]['momentum'], t))
    entries = ranked[:config.max_candidates]
    for r in screening:
        if r['ticker'] in ranked[config.max_candidates:]: r['reason']='candidate_limit'
    holdings = {t:q for t,q in portfolio['positions'].items() if q}
    if len(holdings)>config.max_positions: raise ValueError('Held-position limit exceeded; no holdings omitted')
    allowed = set(entries)|set(holdings)
    bars = history[history.ticker.isin(allowed)].sort_values('date').groupby('ticker').tail(100).copy()
    bars['date'] = bars.date.astype(str)
    peak = max([config.initial_capital]+[x['equity'] for x in curve])
    context = dict(version=1, cutoff=cutoff, entries=entries, holdings=holdings, screening=screening, indicators={t:v for t,v in indicators.items() if t in allowed}, portfolio=portfolio, rules=config.model_dump(mode='json'), risk=dict(drawdown=portfolio['equity']/peak-1, exposure=1-portfolio['cash']/portfolio['equity'], sector_status='missing', candidate_weight_limit=config.max_position_weight), input_hash=manifest.get('content_sha256', manifest.get('sha256')), missing_inputs=['sectors'], evidence_refs=['snapshot'])
    context['_bars'] = bars[['date','ticker','close']].to_dict('records')
    context['price_basis'] = 'USD closes adjusted for splits through cutoff only'
    context['risk']['candidate_scenarios'] = {t: dict(target_weight=min(config.max_position_weight,config.max_exposure), target_value=portfolio['equity']*min(config.max_position_weight,config.max_exposure), current_value=holdings.get(t,0)*indicators[t]['close']) for t in entries}
    context['risk']['missing_inputs'] = ['sectors', 'fundamental risk metrics unless retrieved']
    context['_evidence'] = manifest.get('agent_evidence', [])
    context['snapshot_hash'] = digest(context)
    return context


def holding_facts(context: dict) -> dict:
    """Value held shares with the same cutoff marks used for portfolio equity."""
    portfolio = context['portfolio']
    cap = context['rules']['max_position_weight']
    facts = {}
    for ticker, quantity in context['holdings'].items():
        mark = portfolio.get('prices', {}).get(ticker)
        value = quantity * mark if mark is not None else None
        weight = value / portfolio['equity'] if value is not None and portfolio['equity'] > 0 else None
        above_target = None if weight is None else weight > cap and not isclose(weight, cap, rel_tol=0, abs_tol=1e-12)
        facts[ticker] = dict(quantity_shares=quantity, mark_price_usd=mark, market_value_usd=value,
                             weight_fraction=weight, above_target=above_target)
    return facts


def dispatch(request, context, config):
    allowed = set(context['entries'])|set(context['holdings'])
    name = request.name
    if config.price_only and name in ('fundamentals', 'news'):
        return dict(status='unsupported', reason='Disabled for price-only experiment', evidence_refs=[])
    if name in ('prices','indicators','news','fundamentals') and request.ticker not in allowed:
        return dict(status='rejected', reason='Symbol not authorized', evidence_refs=[])
    if name in ('positions','cash','rules') and request.ticker is not None:
        return dict(status='rejected', reason='Unexpected ticker', evidence_refs=[])
    if name == 'prices': value = [b for b in context['_bars'] if b['ticker']==request.ticker][-request.rows:]
    elif name == 'indicators': value = context['indicators'].get(request.ticker)
    elif name == 'positions':
        value = holding_facts(context) if config.price_only and config.strategy == 'multi_agent' else context['holdings']
    elif name == 'cash': value = {k:context['portfolio'][k] for k in ('cash','equity')}
    elif name == 'rules': value = context['rules']
    else:
        cutoff = pd.Timestamp(context['cutoff']); latest = {}
        for r in context['_evidence']:
            if r['kind'] != name or r['ticker'] != request.ticker: continue
            if max(pd.Timestamp(r['available_at']), pd.Timestamp(r['published_at'])) > cutoff: continue
            key=r['id']
            if key not in latest or (pd.Timestamp(r['available_at']),r['revision']) > (pd.Timestamp(latest[key]['available_at']),latest[key]['revision']): latest[key]=r
        age = config.news_max_age_days if name=='news' else config.fundamentals_max_age_days
        value = sorted((r for r in latest.values() if cutoff-pd.Timestamp(r['published_at'])<=pd.Timedelta(days=age)), key=lambda r:(r['available_at'],r['id']))[-request.rows:]
        if not value: return dict(status='stale' if latest else 'missing', reason='No usable point-in-time records', evidence_refs=[])
    if value is None or value == []: return dict(status='missing', reason='Evidence unavailable', evidence_refs=[])
    if len(json.dumps(value)) > 16000: return dict(status='rejected', reason='Result size limit', evidence_refs=[])
    ref = digest(dict(request=request.model_dump(), cutoff=context['cutoff'], value=value))
    return dict(status='available', data=value, cutoff=context['cutoff'], evidence_refs=[ref])
