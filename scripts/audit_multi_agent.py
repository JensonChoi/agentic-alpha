"""Reconcile a saved benchmark with its immutable input bars and corporate actions."""
from collections import Counter, defaultdict
from datetime import timedelta
from math import isclose

from app.data import sessions
from app.experiments import inputs


def audit(config, result):
    frame, manifest = inputs(config)
    dates = [d.date() for d in sessions(config.start, config.end)]
    scheduled = [day.isoformat() for day, following in zip(dates, dates[1:] + [dates[-1] + timedelta(days=1)])
                 if day.isocalendar()[:2] != following.isocalendar()[:2]]
    decisions = result['decisions']
    assert scheduled == [d['date'] for d in decisions]
    assert [d.isoformat() for d in dates] == [p['date'] for p in result['equity']]
    roles = {'technical', 'fundamental_news', 'risk', 'portfolio'} if config.strategy == 'multi_agent' else {'portfolio'}
    accepted = set()
    errors = Counter()
    skipped = Counter()
    role_calls = Counter()
    role_seconds = Counter()
    calls = 0
    latency = 0.0
    for decision in decisions:
        trace = decision['trace']
        weekly = trace[-1]
        assert weekly['role'] == 'audit'
        if weekly['status'] == 'completed':
            assert {t['role'] for t in trace if t.get('validation_status') == 'validated'} == roles
            accepted.add(decision['date'])
        else:
            assert not decision['signals']
            if weekly['status'] == 'skipped':
                skipped[weekly['reason']] += 1
        for t in trace:
            if t['role'] != 'audit' and t['status'] != 'skipped':
                role_calls[t['role']] += 1
                role_seconds[t['role']] += t['latency']
            if t.get('error_code'):
                errors[f"{t['role']}/{t['error_code']}"] += 1
        calls += weekly.get('actual_calls', 0)
        latency += weekly.get('elapsed_seconds', 0)
    assert calls == sum(role_calls.values())
    assert all(o.get('decision_id') in accepted for o in result['orders'] if o.get('date'))
    assert len({f['id'] for f in result['trades']}) == len(result['trades'])
    fills = defaultdict(list)
    actions = defaultdict(list)
    for f in result['trades']:
        fills[f['date']].append(f)
    for action in manifest.get('actions', []):
        actions[action['date']].append(action)
    bars = frame.set_index(['date', 'ticker'])
    cash = peak = config.initial_capital
    shares = defaultdict(float)
    previous = config.start
    minimum_cash, maximum_exposure, drawdown = None, None, 0.
    for day, point in zip(dates, result['equity']):
        stamp = day.isoformat()
        cash += cash * config.cash_interest_rate * (day - previous).days / 365
        previous = day
        for action in sorted(actions[stamp], key=lambda a: a['type'] != 'split'):
            ticker = action['ticker']
            if action['type'] == 'split':
                shares[ticker] *= action['ratio']
            elif action['type'] == 'dividend':
                cash += shares[ticker] * action['amount']
        for fill in fills[stamp]:
            shares[fill['ticker']] += fill['quantity']
            cash -= fill['quantity'] * fill['price'] + fill['fee']
            market_value = sum(q * bars.loc[(stamp, t), 'open'] for t, q in shares.items() if abs(q) > 1e-9)
            exposure = market_value / (cash + market_value)
            assert cash >= -1e-6 and exposure <= config.max_exposure + 1e-9
            minimum_cash = cash if minimum_cash is None else min(minimum_cash, cash)
            maximum_exposure = exposure if maximum_exposure is None else max(maximum_exposure, exposure)
        equity = cash + sum(q * bars.loc[(stamp, t), 'close'] for t, q in shares.items() if abs(q) > 1e-9)
        assert isclose(cash, point['cash'], abs_tol=1e-6)
        assert isclose(equity, point['equity'], abs_tol=1e-6)
        peak = max(peak, equity)
        drawdown = min(drawdown, equity / peak - 1)
    metrics = result['metrics']
    total_return = equity / config.initial_capital - 1
    assert isclose(total_return, metrics['total_return'], abs_tol=1e-9)
    assert isclose(drawdown, metrics['max_drawdown'], abs_tol=1e-9)
    assert isclose(equity, metrics['final_value'], abs_tol=1e-6)
    assert calls == metrics['llm_requests'] and len(result['trades']) == metrics['trade_count']
    return dict(accepted=len(accepted), scheduled=len(scheduled), calls=calls, mean_week_seconds=latency/len(scheduled),
                role_calls=dict(role_calls), role_seconds=dict(role_seconds), errors=dict(errors), skipped=dict(skipped), minimum_fill_cash=minimum_cash, maximum_fill_exposure=maximum_exposure,
                fills=len(result['trades']), equity=equity, total_return=total_return, drawdown=drawdown)
