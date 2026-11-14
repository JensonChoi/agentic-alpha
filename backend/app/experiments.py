"""Shared API/CLI preflight and persisted experiment creation."""
import pandas as pd
from . import data
from .data import sessions
from .db import Experiment, ConfigRow
from .disclosures import load_snapshot, selected_records
from .provenance import digest, code_revision, implementation_hash


def inputs(config):
    frame, manifest = data.load(config.dataset)
    manifest = dict(manifest)
    if config.disclosure_snapshot and config.strategy=='congressional':
        records, provenance = load_snapshot(config.disclosure_snapshot)
        manifest['disclosure_snapshot'] = provenance
        manifest['disclosures'] = records
    return frame, manifest


def validate(config, frame, manifest):
    dates = sessions(config.start, config.end)
    if not len(dates): raise ValueError('No trading sessions in requested range')
    required = set(['VOO'] if config.strategy=='buy_and_hold' else config.universe) | {'VOO'}
    if config.strategy == 'congressional' and (config.disclosure_snapshot or not manifest.get('synthetic')):
        if not config.disclosure_snapshot: raise ValueError('Congressional benchmark blocked: select a verified disclosure snapshot')
        records, skipped = selected_records(config, manifest['disclosures'])
        if not records: raise ValueError('Congressional benchmark blocked: no usable disclosures in selected scope/range')
        required = {d['ticker'] for d in records} | {'VOO'}
    missing = required - set(manifest['symbols'])
    if missing and config.missing_price_policy == 'fail': raise ValueError('Missing price histories: '+','.join(sorted(missing)))
    if config.mode == 'historical':
        for ticker in sorted(required):
            bars = frame[frame.ticker==ticker]
            gaps = dates.difference(pd.DatetimeIndex(bars.date))
            if len(gaps) and config.missing_price_policy == 'fail': raise ValueError(f'{ticker}: missing {len(gaps)} required sessions, first {gaps[0].date()}')
            if config.strategy in ('momentum','single_agent','multi_agent'):
                warmup = sessions(dates[0]-pd.Timedelta(days=config.long_window*3+30), dates[0]-pd.Timedelta(days=1))[-(config.long_window+1):]
                if len(warmup.difference(pd.DatetimeIndex(bars.date))): raise ValueError(f'{ticker}: requires {config.long_window+1} preceding sessions for warmup')
    return required


def create_experiment(config, session_factory=None, queued=False):
    frame, manifest = inputs(config)
    validate(config, frame, manifest)
    with (session_factory or data.Session)() as db:
        row = Experiment(config=config.model_dump(mode='json'), status='queued' if queued else 'created', result={'execution_provenance':dict(version='2', implementation_hash=implementation_hash(), dataset_hash=manifest.get('content_sha256',manifest['sha256']), config_hash=digest(config.model_dump(mode='json')), disclosure_hash=manifest.get('disclosure_snapshot',{}).get('sha256'), code_revision=code_revision())})
        db.add(row); db.flush()
        db.add(ConfigRow(experiment_id=row.id, payload=row.config)); db.commit()
        return row


def queue(row):
    if row.status not in ('created','failed','partial'): raise ValueError('Experiment is already queued or completed')
    from .contracts import Config
    frame, manifest = inputs(Config(**row.config))
    validate(Config(**row.config), frame, manifest)
    row.status = 'queued'
