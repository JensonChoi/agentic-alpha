import argparse
import asyncio
import json
from pathlib import Path
import pandas as pd
from .db import Base,engine
from .data import register, seed_demo,load
from .contracts import Config
from .engine import simulate

def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('demo')
    imp=sub.add_parser('import'); imp.add_argument('file'); imp.add_argument('--id',required=True); imp.add_argument('--provenance',required=True); imp.add_argument('--disclosures'); imp.add_argument('--actions')
    run=sub.add_parser('benchmark'); run.add_argument('--dataset',default='demo'); run.add_argument('--output',default='benchmark.md')
    args=p.parse_args()
    if engine.dialect.name=='sqlite': Base.metadata.create_all(engine)
    if args.command=='demo': seed_demo()
    elif args.command=='import':
        frame=pd.read_parquet(args.file) if args.file.endswith('.parquet') else pd.read_csv(args.file)
        register(args.id,frame,args.provenance,False,json.loads(Path(args.disclosures).read_text()) if args.disclosures else [],json.loads(Path(args.actions).read_text()) if args.actions else [])
    else:
        seed_demo(); frame,manifest=load(args.dataset); lines=['# Agentic Alpha benchmark','',manifest['provenance'],'','SIMULATION ONLY — NO REAL MONEY','','| Strategy | Return | Maximum drawdown | Trades |','|---|---:|---:|---:|']
        for strategy in ['buy_and_hold','momentum','congressional']:
            c=Config(strategy=strategy,dataset=args.dataset); result=asyncio.run(simulate(c,frame,manifest)); m=result['metrics']
            lines.append(f"| {strategy} | {m['total_return']:.2%} | {m['max_drawdown']:.2%} | {m['trade_count']} |")
        lines+=['','Daily signals, next session opens, 5 bps slippage, zero fees. VOO has a 100% allocation budget; other strategies have a 10% per-position limit. Synthetic fixtures do not measure market outperformance.']
        Path(args.output).write_text('\n'.join(lines))
if __name__=='__main__': main()
