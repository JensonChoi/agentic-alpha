"""Persisted suite orchestration; execution belongs to the worker."""
import json
import time
from pathlib import Path
from . import data
from .contracts import Config
from .db import BenchmarkSuite, Experiment
from .experiments import create_experiment
from .provenance import digest, code_revision


def submit(settings: dict, strategies: list[str]) -> str:
    if not strategies or len(strategies)!=len(set(strategies)): raise ValueError('Select distinct strategies')
    if any(s not in ('buy_and_hold','momentum','congressional') for s in strategies): raise ValueError('Benchmark supports deterministic strategies only')
    configs=[Config(**{**settings,'strategy':s,'name':f'{s} benchmark',**({'max_exposure':1,'max_position_weight':1} if s=='buy_and_hold' else {})}) for s in strategies]
    members=[]
    for config in configs:
        try:
            row=create_experiment(config,queued=True)
            members.append(dict(strategy=config.strategy,experiment_id=row.id))
        except ValueError as exc:
            members.append(dict(strategy=config.strategy,status='blocked',reason=str(exc),config=config.model_dump(mode='json')))
    with data.Session() as db:
        suite=BenchmarkSuite(config=dict(settings=settings,strategies=strategies,sha256=digest([c.model_dump(mode='json') for c in configs]),code_revision=code_revision()), members=members)
        db.add(suite); db.commit(); return suite.id


def suite_results(identifier: str):
    with data.Session() as db:
        suite=db.get(BenchmarkSuite,identifier)
        if suite is None: raise ValueError('Unknown benchmark suite')
        rows=[]
        for member in suite.members:
            e=db.get(Experiment,member.get('experiment_id')) if member.get('experiment_id') else None
            rows.append({**member, **(dict(status=e.status,error=e.error,result=e.result,config=e.config) if e else {})})
        return suite.config, rows


def wait(identifier: str, seconds: float):
    if not 0 <= seconds <= 86400: raise ValueError('wait must be between 0 and 86400 seconds')
    deadline=time.monotonic()+seconds
    while True:
        _, rows=suite_results(identifier)
        outstanding=[r['experiment_id'] for r in rows if r.get('status') in ('created','queued','running','waiting')]
        if not outstanding or time.monotonic()>=deadline: return outstanding
        time.sleep(min(1,max(0,deadline-time.monotonic())))


def report(identifier: str, output: str) -> bool:
    config, rows=suite_results(identifier)
    completed=all(r.get('status')=='completed' for r in rows)
    baseline=next((r for r in rows if r['strategy']=='buy_and_hold' and r['status']=='completed'),None)
    base_return=baseline['result']['metrics']['total_return'] if baseline else None
    lines=['# Agentic Alpha benchmark', '', 'SIMULATION ONLY — NO REAL MONEY', '', f'Suite: {identifier}', f'Outcome: {"completed" if completed else "incomplete / blocked / partial"}', f'Configuration hash: {config["sha256"]}', f'Code revision: {config["code_revision"]}', '', '| Strategy | Experiment | Status | Return | Excess vs matched VOO | Exposure | Fees | Trades |', '|---|---|---|---:|---:|---:|---:|---:|']
    for r in rows:
        m=r.get('result',{}).get('metrics',{}); value=m.get('total_return')
        fmt=lambda v: f'{v:.4%}' if v is not None else 'unavailable'
        lines.append(f'| {r["strategy"]} | {r.get("experiment_id","blocked")} | {r.get("status")} | {fmt(value)} | {fmt(value-base_return if value is not None and base_return is not None and r["status"]=="completed" else None)} | {fmt(m.get("average_exposure"))} | {m.get("transaction_costs","unavailable")} | {m.get("trade_count","unavailable")} |')
    for r in rows:
        result=r.get('result',{})
        lines += ['', f'## {r["strategy"]}', r.get('reason') or r.get('error') or '', '```json', json.dumps(dict(configuration=r.get('config'),execution=result.get('execution_provenance'),dataset=result.get('provenance'),metrics=result.get('metrics'),disclosures=result.get('disclosure_counts'),warnings=result.get('warnings')),indent=2), '```']
    lines += ['', 'Passive VOO targets 100%; active strategies use configured position/exposure caps and retain cash. These are different risk budgets. Signals use completed bars and subsequent opens, except initial VOO allocation and eligible public disclosure events before the open. Dividends use pre-open entitlement with an ex-date cash-credit approximation. Reinvestment uses opening execution, fees and slippage. Adjusted-close returns can differ because of these conventions.', '', 'Fixed-universe studies have selection and survivorship bias. Congressional results describe a family disclosure-following simulation, not actual investment performance. Starting holdings are unknown; options are omitted; position sizing and full exits are approximations. Unknown ownership remains unknown. Missing verified records block that leg. Synthetic inputs are demonstrations only.']
    destination=Path(output); destination.parent.mkdir(parents=True,exist_ok=True); destination.write_text('\n'.join(lines))
    return completed
