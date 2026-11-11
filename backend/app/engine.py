from decimal import Decimal
from datetime import timedelta
import math
import numpy as np
import pandas as pd
from .contracts import Signal
from .data import sessions
from .inference import evaluate

def D(x): return Decimal(str(x))
class Ledger:
    def __init__(self, capital):
        self.cash=D(capital); self.positions={}; self.fills=[]; self.ids=set(); self.costs={}
    def equity(self, prices): return self.cash+sum((q*D(prices.get(t,0)) for t,q in self.positions.items()),D(0))
    def fill(self, key, ticker, quantity, price, fee):
        if key in self.ids: return False
        quantity,price,fee=map(D,(quantity,price,fee))
        if price<=0 or fee<0 or quantity==0: raise ValueError('Invalid fill')
        new_cash=self.cash-quantity*price-fee; new_qty=self.positions.get(ticker,D(0))+quantity
        if new_cash < D('-0.00000001') or new_qty<0: raise ValueError('Insufficient cash or shares')
        self.cash=max(D(0),new_cash); self.positions[ticker]=new_qty; self.ids.add(key)
        self.fills.append(dict(id=key,ticker=ticker,quantity=float(quantity),price=float(price),fee=float(fee)))
        return True

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
    ledger=Ledger(c.initial_capital); curve=[]; decisions=[]; orders=[]; pending=[]; prices={}; bullish=set(); seen=set(); failures=0
    if resume:
        ledger.cash=D(resume.get('state',{}).get('exact_cash',resume['cash'])); ledger.positions={t:D(q) for t,q in resume.get('state',{}).get('exact_positions',resume['positions']).items()}
        ledger.fills=resume['trades']; ledger.ids={f['id'] for f in ledger.fills}
        curve=resume['equity']; decisions=resume['decisions']; orders=resume['orders']
        state=resume.get('state',{}); pending=[Signal(**s) for s in state.get('pending',[])]
        prices=state.get('prices',{}); bullish=set(state.get('bullish',[])); seen=set(state.get('seen',[])); failures=resume.get('failures',0)
    dates=sessions(c.start,c.end)
    if not len(dates): raise ValueError('No trading sessions in requested range')
    if c.mode=='historical' and (str(c.start)<manifest['start'] or str(c.end)>manifest['end']): raise ValueError('Date range outside dataset coverage')
    if c.mode=='forward':
        import exchange_calendars as xcals
        calendar=xcals.get_calendar('XNYS')
        dates=pd.DatetimeIndex([d for d in dates if calendar.session_close(d)<=pd.Timestamp.now(tz='UTC') and d<=frame.date.max()])
    if resume and curve: dates=dates[dates>pd.Timestamp(curve[-1]['date'])]
    cap=1. if c.strategy=='buy_and_hold' else c.max_position_weight
    for index,day in enumerate(dates):
        stamp=str(day.date()); today=frame[frame.date==day]; opens=dict(zip(today.ticker,today.open)); closes=dict(zip(today.ticker,today.close))
        if not len(today):
            decisions.append(dict(date=stamp,status='skipped',reason='No fresh bars')); continue
        for action in manifest.get('actions',[]):
            if action['date']!=stamp: continue
            ticker=action['ticker']; qty=ledger.positions.get(ticker,D(0))
            if action['type']=='split': ledger.positions[ticker]=qty*D(action['ratio'])
            elif action['type']=='dividend':
                cash=qty*D(action['amount']); ledger.cash+=cash
                if c.reinvest_dividends and ticker in opens and cash>0:
                    ledger.fill('dividend-'+stamp+ticker,ticker,cash/D(opens[ticker]),opens[ticker],0)
                    ledger.fills[-1]['date']=stamp
        if c.strategy=='buy_and_hold' and index==0 and not curve: pending=[Signal(ticker='VOO',action='BUY',target_weight=1,rationale='Initial passive allocation')]
        mark={**prices,**opens}; equity=ledger.equity(mark)
        for n,s in enumerate(sorted(pending,key=lambda x:x.action!='SELL')):
            record=dict(date=stamp,signal=s.model_dump(),status='rejected',reason='')
            orders.append(record)
            if s.ticker not in c.universe: record['reason']='Symbol outside universe'; continue
            if s.target_weight>cap or s.target_weight>c.max_exposure: record['reason']='Position or exposure limit'; continue
            if s.ticker not in opens: record.update(status='unfilled',reason='Missing opening price'); continue
            if s.action=='HOLD': record.update(status='held'); continue
            weight=s.target_weight if s.action=='BUY' else 0
            px=D(opens[s.ticker])*(1+D(c.slippage_bps)/10000*(1 if s.action=='BUY' else -1))
            current=ledger.positions.get(s.ticker,D(0)); target=equity*D(weight)/px; qty=target-current
            if s.action=='BUY':
                exposure=sum((q*D(mark.get(t,0)) for t,q in ledger.positions.items()),D(0))
                budget=max(D(0),min(ledger.cash-D(c.fee),equity*D(c.max_exposure)-exposure))
                qty=min(max(D(0),qty),budget/px)
            else: qty=-current
            if not qty: record['reason']='No executable quantity'; continue
            if ledger.cash-qty*px-D(c.fee)<0: record['reason']='Fees exceed cash'; continue
            ledger.fill(stamp+':'+str(n),s.ticker,qty,px,c.fee); ledger.fills[-1]['date']=stamp
            record.update(status='filled',fill=ledger.fills[-1])
        pending=[]; prices.update(closes)
        value=float(ledger.equity(prices)); curve.append(dict(date=stamp,equity=value,cash=float(ledger.cash),positions={t:float(q) for t,q in ledger.positions.items()},prices=dict(prices)))
        history=frame[(frame.date<=day)&frame.ticker.isin(c.universe)]
        signals=[]; trace=[]; reason=''
        if c.strategy=='congressional':
            eligible=[]
            for d in manifest.get('disclosures',[]):
                identity=d.get('amends',d['id'])
                available=pd.Timestamp(d.get('published_at',d['disclosure_date']))
                if available.tzinfo: available=available.tz_convert('America/New_York').tz_localize(None)
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
        state=dict(exact_positions={t:str(q) for t,q in ledger.positions.items()},exact_cash=str(ledger.cash),pending=[s.model_dump() for s in pending],prices=prices,bullish=sorted(bullish),seen=sorted(seen))
        partial=dict(equity=curve,trades=ledger.fills,orders=orders,decisions=decisions,cash=str(ledger.cash),positions={t:str(q) for t,q in ledger.positions.items()},state=state,failures=failures)
        if checkpoint and not checkpoint((index+1)/len(dates),partial): return dict(canceled=True)
    if c.mode=='historical': orders.extend(dict(date=None,signal=s.model_dump(),status='unfilled',reason='No subsequent session in experiment') for s in pending)
    result=dict(state=dict(exact_positions={t:str(q) for t,q in ledger.positions.items()},exact_cash=str(ledger.cash),pending=[s.model_dump() for s in pending],prices=prices,bullish=sorted(bullish),seen=sorted(seen)),equity=curve,trades=ledger.fills,orders=orders,decisions=decisions,metrics=metrics(curve,ledger.fills,c.initial_capital),cash=float(ledger.cash),positions={t:float(q) for t,q in ledger.positions.items()},provenance=manifest,failures=failures)
    from .analytics import trading_metrics
    result['metrics'].update(trading_metrics(ledger.fills,curve,decisions))
    if any(a['type']=='split' for a in manifest.get('actions',[])):
        for key in ('realized_pnl','trade_win_rate','average_holding_days'): result['metrics'][key]=None
    result['metrics']['rejected_proposals']=sum(o['status']=='rejected' for o in orders)
    result['metrics']['inference_cost_estimate']=sum(t['latency'] for d in decisions for t in d.get('trace',[]))*c.local_cost_per_hour/3600 if c.provider!='openai' else None
    result['metrics']['llm_requests']=sum(len(d['trace']) for d in decisions if 'trace' in d)
    return result
