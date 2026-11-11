from collections import defaultdict,deque
from datetime import date

def trading_metrics(fills,curve,decisions):
    lots=defaultdict(deque); profits=[]; durations=[]; realized=0
    for f in fills:
        q=f['quantity'];t=f['ticker'];p=f['price'];d=date.fromisoformat(f['date'])
        if q>0: lots[t].append([q,p+f['fee']/q,d])
        else:
            remaining=-q;profit=-f['fee']
            while remaining>1e-9 and lots[t]:
                lot=lots[t][0]; matched=min(remaining,lot[0]);profit+=matched*(p-lot[1]);durations.append((d-lot[2]).days)
                remaining-=matched;lot[0]-=matched
                if lot[0]<1e-9: lots[t].popleft()
            profits.append(profit);realized+=profit
    traces=[t for d in decisions for t in d.get('trace',[])]
    tokens_in=sum((t.get('usage',{}).get('prompt_tokens') or t.get('usage',{}).get('input_tokens') or 0) for t in traces)
    tokens_out=sum((t.get('usage',{}).get('completion_tokens') or t.get('usage',{}).get('output_tokens') or 0) for t in traces)
    return dict(realized_pnl=realized,trade_win_rate=sum(p>0 for p in profits)/len(profits) if profits else None,average_holding_days=sum(durations)/len(durations) if durations else None,cash_allocation=curve[-1]['cash']/curve[-1]['equity'] if curve else 1,average_exposure=sum(1-p['cash']/p['equity'] for p in curve)/len(curve) if curve else 0,input_tokens=tokens_in if traces else None,output_tokens=tokens_out if traces else None,average_decision_latency=sum(t['latency'] for t in traces)/len(traces) if traces else None)
