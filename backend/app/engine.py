from decimal import Decimal
from datetime import timedelta
import math
import numpy as np
import pandas as pd
from .contracts import Signal
from .disclosures import selected_records, events_for_session
from .provenance import digest
from .data import sessions
from .inference import evaluate

def D(x): return Decimal(str(x))
class Ledger:
    def __init__(self, capital):
        self.cash=D(capital); self.positions={}; self.fills=[]; self.ids=set(); self.costs={}; self.lots={}; self.realized=D(0); self.profits=[]; self.holding_days=[]; self.action_ids=set()
    def equity(self, prices): return self.cash+sum((q*D(prices.get(t,0)) for t,q in self.positions.items()),D(0))
    def fill(self, key, ticker, quantity, price, fee, date=None):
        if key in self.ids: return False
        quantity,price,fee=map(D,(quantity,price,fee))
        if price<=0 or fee<0 or quantity==0: raise ValueError('Invalid fill')
        new_cash=self.cash-quantity*price-fee; new_qty=self.positions.get(ticker,D(0))+quantity
        if new_cash < D('-0.00000001') or new_qty<0: raise ValueError('Insufficient cash or shares')
        lots = self.lots.setdefault(ticker, [])
        if quantity > 0:
            lots.append([quantity, price + fee/quantity, date])
        else:
            remaining = -quantity; profit = -fee
            while remaining > 0 and lots:
                lot = lots[0]; matched = min(remaining, lot[0])
                profit += matched * (price-lot[1]); remaining -= matched; lot[0] -= matched
                if date and lot[2]: self.holding_days.append((pd.Timestamp(date)-pd.Timestamp(lot[2])).days)
                if lot[0] == 0: lots.pop(0)
            self.realized += profit; self.profits.append(profit)
        self.cash=max(D(0),new_cash); self.positions[ticker]=new_qty; self.ids.add(key)
        self.fills.append(dict(id=key,ticker=ticker,quantity=float(quantity),price=float(price),fee=float(fee)))
        return True

    def split(self, ticker, ratio):
        ratio = D(ratio)
        self.positions[ticker] = self.positions.get(ticker,D(0))*ratio
        for lot in self.lots.get(ticker, []):
            lot[0] *= ratio; lot[1] /= ratio

    def accounting_state(self):
        return dict(lots={t:[[str(q),str(p),d] for q,p,d in lots] for t,lots in self.lots.items()}, realized=str(self.realized), profits=[str(x) for x in self.profits], holding_days=self.holding_days, action_ids=sorted(self.action_ids))

    def restore_accounting(self, state):
        self.lots={t:[[D(q),D(p),d] for q,p,d in lots] for t,lots in state.get('lots',{}).items()}
        self.realized=D(state.get('realized',0)); self.profits=[D(x) for x in state.get('profits',[])]
        self.holding_days=state.get('holding_days',[]); self.action_ids=set(state.get('action_ids',[]))

def metrics(curve, fills, capital):
    values=np.array([x['equity'] for x in curve]); returns=values[1:]/values[:-1]-1 if len(values)>1 else np.array([])
    total=values[-1]/capital-1 if len(values) else 0
    years=(pd.Timestamp(curve[-1]['date'])-pd.Timestamp(curve[0]['date'])).days/365.25 if len(curve)>1 else 0
    cagr=(values[-1]/capital)**(1/years)-1 if years>0 else None
    vol=float(np.std(returns,ddof=1)*np.sqrt(252)) if len(returns)>1 else None
    downside=float(np.sqrt(np.mean(np.minimum(returns,0)**2))*np.sqrt(252)) if len(returns) else 0
    dd=float(np.min(values/np.maximum.accumulate(np.r_[capital,values])[1:]-1)) if len(values) else 0
    return dict(initial_value=capital,final_value=float(values[-1]) if len(values) else capital,total_return=total,cagr=cagr,volatility=vol,sharpe=float(np.mean(returns)*252/vol) if vol else None,sortino=float(np.mean(returns)*252/downside) if downside else None,max_drawdown=dd,calmar=cagr/abs(dd) if dd and cagr is not None else None,trade_count=len(fills),transaction_costs=sum(f['fee'] for f in fills),turnover=sum(abs(f['quantity']*f['price']) for f in fills)/capital)

async def simulate(c, frame, manifest, checkpoint=None, resume=None):
    ledger=Ledger(c.initial_capital); curve=[]; decisions=[]; orders=[]; pending=[]; prices={}; bullish=set(); seen=set(); failures=0; active=set(); copied=set(); disclosure_audit=[]
    normalized = c.strategy=='congressional' and bool(c.disclosure_snapshot)
    records, skipped = selected_records(c, manifest.get('disclosures', [])) if normalized else ([], [])
    disclosure_audit.extend(skipped)
    if resume:
        ledger.cash=D(resume.get('state',{}).get('exact_cash',resume['cash'])); ledger.positions={t:D(q) for t,q in resume.get('state',{}).get('exact_positions',resume['positions']).items()}
        ledger.fills=resume['trades']; ledger.ids={f['id'] for f in ledger.fills}
        curve=resume['equity']; decisions=resume['decisions']; orders=resume['orders']
        state=resume.get('state',{}); pending=[Signal(**s) for s in state.get('pending',[])]
        if ledger.fills and 'accounting' not in state: raise ValueError('Legacy checkpoint lacks exact FIFO state; create a new experiment')
        ledger.restore_accounting(state.get('accounting',{}))
        active=set(state.get('active',[])); copied=set(state.get('copied',[])); disclosure_audit=state.get('disclosure_audit',skipped)
        prices=state.get('prices',{}); bullish=set(state.get('bullish',[])); seen=set(state.get('seen',[])); failures=resume.get('failures',0)
    dates=sessions(c.start,c.end)
    if not len(dates): raise ValueError('No trading sessions in requested range')
    if c.mode=='historical' and (str(dates[0].date())<manifest['start'] or str(dates[-1].date())>manifest['end']): raise ValueError('Date range outside dataset coverage')
    if c.mode=='forward':
        import exchange_calendars as xcals
        calendar=xcals.get_calendar('XNYS')
        dates=pd.DatetimeIndex([d for d in dates if calendar.session_close(d)<=pd.Timestamp.now(tz='UTC') and d<=frame.date.max()])
    if resume and curve: dates=dates[dates>pd.Timestamp(curve[-1]['date'])]
    cap=1. if c.strategy=='buy_and_hold' else c.max_position_weight
    for index,day in enumerate(dates):
        stamp=str(day.date()); today=frame[frame.date==day]; opens=dict(zip(today.ticker,today.open)); closes=dict(zip(today.ticker,today.close))
        if not len(today):
            decisions.append(dict(date=stamp,status='skipped',reason='No fresh bars; actions still processed'))
        reinvest = {}
        for action in sorted(manifest.get('actions',[]), key=lambda a:a['type']!='split'):
            if action['date']!=stamp: continue
            identity = action.get('id', digest(action))
            if identity in ledger.action_ids: continue
            ledger.action_ids.add(identity)
            ticker=action['ticker']; qty=ledger.positions.get(ticker,D(0))
            if action['type']=='split':
                ledger.split(ticker, action['ratio'])
                if ticker in prices: prices[ticker] = float(D(prices[ticker])/D(action['ratio']))
            elif action['type']=='dividend':
                cash=qty*D(action['amount']); ledger.cash+=cash
                if c.reinvest_dividends and cash>0: reinvest[ticker] = cash
        if c.strategy=='congressional' and normalized:
            events = events_for_session(records, day, seen)
            candidates = []
            for d in events:
                seen.add(d['source_id']+':'+d['revision'])
                identity = d.get('amends') or d['source_id']
                if identity in copied:
                    disclosure_audit.append(dict(source_id=d['source_id'], reason='amended: already processed; no replay'))
                    continue
                candidates.append(d)
            conflicts = {d['ticker'] for d in candidates if len({x['action'] for x in candidates if x['ticker']==d['ticker']})>1 and any(x.get('source_order') is None for x in candidates if x['ticker']==d['ticker'])}
            sells = set()
            for d in candidates:
                identity = d.get('amends') or d['source_id']
                if identity in copied:
                    disclosure_audit.append(dict(source_id=d['source_id'], reason='amended: already processed; no replay')); continue
                copied.add(identity)
                if d['ticker'] in conflicts:
                    disclosure_audit.append(dict(source_id=d['source_id'], reason='ambiguous same-open conflicting disclosures')); continue
                if d['ticker'] not in set(frame.ticker):
                    disclosure_audit.append(dict(source_id=d['source_id'], reason='unmatched price history')); continue
                if d['action']=='BUY': active.add(d['ticker']); sells.discard(d['ticker'])
                else: active.discard(d['ticker']); sells.add(d['ticker'])
                disclosure_audit.append(dict(source_id=d['source_id'], owner=d['owner'], reason='eligible', date=stamp))
            selected = sorted(active)[:c.max_positions]
            sells.update(t for t,q in ledger.positions.items() if q>0 and t not in selected)
            if candidates:
                weight = min(cap,c.max_exposure/max(1,len(selected)))
                if c.copy_method=='fixed': weight=min(weight,c.fixed_allocation)
                weights={t:weight for t in selected}
                if c.copy_method=='proportional':
                    values={t:sum((d['value_low']+d['value_high'])/2 for d in candidates if d['ticker']==t and d['action']=='BUY') for t in selected}
                    total=sum(values.values())
                    weights={t:min(cap,c.max_exposure*values[t]/total) if total else 0 for t in selected}
                pending = [Signal(ticker=t,action='SELL',rationale='Public sell disclosure: full exit') for t in sorted(sells)] + [Signal(ticker=t,action='BUY',target_weight=weights[t],rationale='Public disclosure eligible purchase set') for t in selected]
        if c.strategy=='buy_and_hold' and index==0 and not curve: pending=[Signal(ticker='VOO',action='BUY',target_weight=1,rationale='Initial passive allocation')]
        mark={**prices,**opens}; equity=ledger.equity(mark)
        for ticker, cash in reinvest.items():
            if any(s.ticker==ticker and s.action=='SELL' for s in pending): continue
            if ticker in opens and equity>0:
                weight = min(cap, float((ledger.positions.get(ticker,D(0))*D(opens[ticker])+cash)/equity))
                pending.append(Signal(ticker=ticker,action='BUY',target_weight=weight,rationale='Ex-date dividend reinvestment approximation'))
        def reducing(signal):
            return signal.action=='SELL' or (signal.ticker in opens and equity*D(signal.target_weight)<ledger.positions.get(signal.ticker,D(0))*D(opens[signal.ticker]))
        for n,s in enumerate(sorted(pending,key=lambda x:not reducing(x))):
            record=dict(date=stamp,signal=s.model_dump(),status='rejected',reason='')
            orders.append(record)
            if s.ticker not in (active | set(ledger.positions) if normalized and c.strategy=='congressional' else set(c.universe)): record['reason']='Symbol outside universe'; continue
            if s.target_weight>cap or s.target_weight>c.max_exposure: record['reason']='Position or exposure limit'; continue
            if s.ticker not in opens: record.update(status='unfilled',reason='Missing opening price'); continue
            if s.action=='HOLD': record.update(status='held'); continue
            weight=s.target_weight if s.action=='BUY' else 0
            is_reduction = reducing(s) and s.rationale!='Ex-date dividend reinvestment approximation'
            px=D(opens[s.ticker])*(1+D(c.slippage_bps)/10000*(-1 if is_reduction else 1))
            current=ledger.positions.get(s.ticker,D(0)); target=equity*D(weight)/D(opens[s.ticker]); qty=target-current
            if s.action=='BUY' and not is_reduction:
                if current==0 and sum(q>0 for q in ledger.positions.values())>=c.max_positions and c.strategy!='buy_and_hold': record['reason']='Maximum positions'; continue
                exposure=sum((q*D(mark.get(t,0)) for t,q in ledger.positions.items()),D(0))
                budget=max(D(0),min(ledger.cash-D(c.fee),equity*D(c.max_exposure)-exposure))
                if s.rationale=='Ex-date dividend reinvestment approximation': budget=min(budget,max(D(0),reinvest[s.ticker]-D(c.fee)))
                qty=min(max(D(0),qty),budget/px)
            elif s.action=='SELL': qty=-current
            else: qty=min(D(0),qty)
            if not qty: record['reason']='No executable quantity'; continue
            if ledger.cash-qty*px-D(c.fee)<0: record['reason']='Fees exceed cash'; continue
            ledger.fill(stamp+':'+str(n),s.ticker,qty,px,c.fee,stamp); ledger.fills[-1]['date']=stamp
            ledger.fills[-1]['slippage_cost']=float(abs(qty)*abs(px-D(opens[s.ticker])))
            record.update(status='filled',fill=ledger.fills[-1])
        pending=[]; prices.update(closes)
        value=float(ledger.equity(prices)); curve.append(dict(date=stamp,equity=value,cash=float(ledger.cash),positions={t:float(q) for t,q in ledger.positions.items()},prices=dict(prices)))
        history=frame[(frame.date<=day)&frame.ticker.isin(c.universe)].copy()
        history['close']=history['close'].astype(float)
        for action in manifest.get('actions',[]):
            if action['type']=='split' and action['date']<=stamp:
                mask=(history.ticker==action['ticker']) & (history.date<pd.Timestamp(action['date']))
                history.loc[mask,'close'] /= action['ratio']
        signals=[]; trace=[]; reason=''
        if c.strategy=='congressional' and not normalized:
            eligible=[]
            for d in manifest.get('disclosures',[]):
                identity=d.get('amends',d['id'])
                available=pd.Timestamp(d.get('published_at',d['disclosure_date']))
                if available.tzinfo: available=available.tz_convert('America/New_York').tz_localize(None)
                if available < pd.Timestamp(c.start): continue
                if available>day+pd.Timedelta(hours=16) or identity in seen: continue
                seen.add(identity)
                if d.get('security_type') not in ('stock','etf'): reason+='Skipped unsupported '+d['id']+'; '; continue
                eligible.append(d)
            buys=[d for d in eligible if d['action']=='BUY']
            midpoint=sum((d['value_low']+d['value_high'])/2 for d in buys)
            for d in eligible:
                weight=min(cap,1/max(1,len(buys)))
                if c.copy_method=='fixed': weight=min(cap,c.fixed_allocation)
                if c.copy_method=='proportional': weight=min(cap,((d['value_low']+d['value_high'])/2)/midpoint) if midpoint else 0
                signals.append(Signal(ticker=d['ticker'],action=d['action'],target_weight=weight if d['action']=='BUY' else 0,rationale='Public disclosure '+d['id']))
        elif c.strategy in ('momentum','single_agent','multi_agent'):
            indicators={}
            for ticker in sorted(c.universe):
                h=history[history.ticker==ticker].close
                if len(h)<c.long_window+1: continue
                short=h.rolling(c.short_window).mean(); long=h.rolling(c.long_window).mean()
                if not curve[:-1] and short.iloc[-2]>long.iloc[-2]: bullish.add(ticker)
                indicators[ticker]=dict(close=float(h.iloc[-1]),short=float(short.iloc[-1]),long=float(long.iloc[-1]))
                if short.iloc[-2]<=long.iloc[-2] and short.iloc[-1]>long.iloc[-1]: bullish.add(ticker)
                if short.iloc[-2]>=long.iloc[-2] and short.iloc[-1]<long.iloc[-1]: bullish.discard(ticker)
            following=dates[index+1] if index+1<len(dates) else day+pd.Timedelta(days=1)
            rebalance=c.rebalance=='daily' or (c.rebalance=='weekly' and following.isocalendar().week!=day.isocalendar().week) or (c.rebalance=='monthly' and following.month!=day.month)
            if rebalance:
                selected=sorted(bullish)[:c.max_positions]
                if c.strategy=='momentum':
                    signals=[Signal(ticker=t,action='BUY' if t in selected else 'SELL',target_weight=min(cap,c.max_exposure/max(1,len(selected))) if t in selected else 0,rationale='Completed-bar moving-average crossover state') for t in sorted(set(selected)|{t for t,q in ledger.positions.items() if q})]
                else:
                    context=dict(timestamp=stamp,indicators=dict(list(indicators.items())[:20]),cash=float(ledger.cash),positions={t:float(q) for t,q in ledger.positions.items()},max_weight=cap,news=None,fundamentals=None)
                    try: signals,trace=await evaluate(c,context)
                    except Exception as exc: failures+=1; reason='Model failure: '+type(exc).__name__+'; no action'
        if signals or trace or reason:
            decisions.append(dict(date=stamp,signals=[s.model_dump() for s in signals],trace=trace,reason=reason,snapshot=curve[-1]))
        pending=signals
        state=dict(exact_positions={t:str(q) for t,q in ledger.positions.items()},exact_cash=str(ledger.cash),pending=[s.model_dump() for s in pending],prices=prices,bullish=sorted(bullish),seen=sorted(seen),accounting=ledger.accounting_state(),active=sorted(active),copied=sorted(copied),disclosure_audit=disclosure_audit)
        partial=dict(equity=curve,trades=ledger.fills,orders=orders,decisions=decisions,cash=str(ledger.cash),positions={t:str(q) for t,q in ledger.positions.items()},state=state,failures=failures)
        if checkpoint and not checkpoint((index+1)/len(dates),partial): return dict(canceled=True)
    if c.mode=='historical': orders.extend(dict(date=None,signal=s.model_dump(),status='unfilled',reason='No subsequent session in experiment') for s in pending)
    result=dict(state=dict(exact_positions={t:str(q) for t,q in ledger.positions.items()},exact_cash=str(ledger.cash),pending=[s.model_dump() for s in pending],prices=prices,bullish=sorted(bullish),seen=sorted(seen),accounting=ledger.accounting_state(),active=sorted(active),copied=sorted(copied),disclosure_audit=disclosure_audit),equity=curve,trades=ledger.fills,orders=orders,decisions=decisions,metrics=metrics(curve,ledger.fills,c.initial_capital),cash=float(ledger.cash),positions={t:float(q) for t,q in ledger.positions.items()},provenance=manifest,failures=failures)
    from .analytics import trading_metrics
    result['metrics'].update(trading_metrics(ledger.fills,curve,decisions))
    result['metrics'].update(realized_pnl=float(ledger.realized), trade_win_rate=sum(p>0 for p in ledger.profits)/len(ledger.profits) if ledger.profits else None, average_holding_days=sum(ledger.holding_days)/len(ledger.holding_days) if ledger.holding_days else None)
    result['disclosure_audit']=disclosure_audit
    result['disclosure_counts']={key:sum(key in d['reason'] for d in disclosure_audit) for key in ('eligible','unsupported','unverified','ambiguous','amended','unmatched')}
    result['disclosure_counts']['filled_trades']=len(ledger.fills)
    result['disclosure_counts']['skipped']=sum(d['reason']!='eligible' for d in disclosure_audit)
    result['metrics']['slippage_cost']=sum(f.get('slippage_cost',0) for f in ledger.fills)
    if normalized and not any(d['reason']=='eligible' for d in disclosure_audit):
        result['failures']+=1
        result['metrics']['total_return']=None
    result['warnings']=manifest.get('warnings',[]) + manifest.get('disclosure_snapshot',{}).get('warnings',[]) + ['Dividend cash is credited on ex-date, not payment date']
    if c.missing_price_policy=='skip':
        required = {d['ticker'] for d in records} if normalized else ({'VOO'} if c.strategy=='buy_and_hold' else set(c.universe))
        missing = {ticker:len(sessions(c.start,c.end).difference(pd.DatetimeIndex(frame[frame.ticker==ticker].date))) for ticker in required}
        result['missing_sessions']={ticker:count for ticker,count in missing.items() if count}
        if result['missing_sessions']:
            result['failures']+=1
            result['warnings'].append('Partial coverage: missing executions are unfilled and existing holdings may use stale marks')
    result['metrics']['rejected_proposals']=sum(o['status']=='rejected' for o in orders)
    result['metrics']['inference_cost_estimate']=sum(t['latency'] for d in decisions for t in d.get('trace',[]))*c.local_cost_per_hour/3600 if c.provider!='openai' else None
    result['metrics']['llm_requests']=sum(len(d['trace']) for d in decisions if 'trace' in d)
    return result
