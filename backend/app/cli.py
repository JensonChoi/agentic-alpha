import argparse
import json
import os
from datetime import date
from pathlib import Path
import pandas as pd
from .db import Base, engine
from .data import register, seed_demo
from .contracts import Config
from .providers import YahooProvider, QuiverProvider
from .disclosures import register_snapshot
from . import benchmarks


def parser():
    p=argparse.ArgumentParser(description='Simulation-only immutable data acquisition and persisted benchmarks')
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('demo')
    imp=sub.add_parser('import'); imp.add_argument('file'); imp.add_argument('--id',required=True); imp.add_argument('--provenance',required=True); imp.add_argument('--disclosures'); imp.add_argument('--actions')
    download=sub.add_parser('download'); download.add_argument('--provider',choices=['yahoo'],default='yahoo'); download.add_argument('--id',required=True); download.add_argument('--symbols',required=True); download.add_argument('--start',type=date.fromisoformat,required=True); download.add_argument('--end',type=date.fromisoformat,required=True); download.add_argument('--long-window',type=int,default=50)
    local=sub.add_parser('import-disclosures'); local.add_argument('file'); local.add_argument('--id',required=True); local.add_argument('--provenance',required=True)
    disclosure=sub.add_parser('download-disclosures'); disclosure.add_argument('--provider',choices=['quiver'],default='quiver'); disclosure.add_argument('--id',required=True); disclosure.add_argument('--member-id',default='P000197')
    run=sub.add_parser('benchmark'); run.add_argument('--config'); run.add_argument('--suite',help='Report/wait for an existing suite without creating jobs'); run.add_argument('--output',default='reports/benchmark.md'); run.add_argument('--wait',type=float,default=0); run.add_argument('--strategies')
    for name in ('dataset','start','end','universe','rebalance','disclosure_snapshot','member_id','owners','copy_method','missing_price_policy'): run.add_argument('--'+name.replace('_','-'))
    for name in ('short_window','long_window','max_positions'): run.add_argument('--'+name.replace('_','-'),type=int)
    for name in ('initial_capital','max_position_weight','max_exposure','fee','slippage_bps','fixed_allocation'): run.add_argument('--'+name.replace('_','-'),type=float)
    run.add_argument('--reinvest-dividends',action=argparse.BooleanOptionalAction,default=None)
    return p


def main(argv=None):
    args=parser().parse_args(argv)
    if engine.dialect.name=='sqlite': Base.metadata.create_all(engine)
    if args.command=='demo': seed_demo()
    elif args.command=='import':
        frame=pd.read_parquet(args.file) if args.file.endswith('.parquet') else pd.read_csv(args.file)
        register(args.id,frame,args.provenance,False,json.loads(Path(args.disclosures).read_text()) if args.disclosures else [],json.loads(Path(args.actions).read_text()) if args.actions else [])
    elif args.command=='download':
        acquired=YahooProvider().acquire([s.strip().upper() for s in args.symbols.split(',')],args.start,args.end,args.long_window)
        print(json.dumps(register(args.id,acquired.bars,'Yahoo Finance via yfinance; authorized local research',actions=acquired.actions,metadata=acquired.metadata),indent=2))
    elif args.command=='import-disclosures':
        payload=json.loads(Path(args.file).read_text()); records=payload['records'] if isinstance(payload,dict) else payload
        metadata=payload.get('metadata',{}) if isinstance(payload,dict) else {}
        print(json.dumps(register_snapshot(args.id,records,{**metadata,'provider':'local','provenance':args.provenance,'retrieved_at':pd.Timestamp.now(tz='UTC').isoformat()}),indent=2))
    elif args.command=='download-disclosures':
        records,metadata=QuiverProvider(os.getenv('QUIVER_API_KEY','')).acquire(args.member_id)
        print(json.dumps(register_snapshot(args.id,records,metadata),indent=2))
    else:
        if args.suite: identifier=args.suite
        else:
            settings=json.loads(Path(args.config).read_text()) if args.config else {}
            configured_strategies=settings.pop('strategies','buy_and_hold,momentum')
            strategies=args.strategies or configured_strategies
            if isinstance(strategies,str): strategies=strategies.split(',')
            for key in Config.model_fields:
                value=getattr(args,key,None)
                if value is not None: settings[key]=value.split(',') if key in ('universe','owners') else value
            if settings.get('dataset','demo')=='demo': seed_demo()
            identifier=benchmarks.submit(settings,strategies)
        print('Suite:',identifier,flush=True)
        outstanding=benchmarks.wait(identifier,args.wait); completed=benchmarks.report(identifier,args.output)
        if outstanding: print('Outstanding experiment IDs (jobs remain queued/running):',','.join(outstanding))
        print('Report:',args.output,'; outcome:', 'completed' if completed else 'incomplete')
        return 0 if completed else 2
    return 0

if __name__=='__main__': raise SystemExit(main())
