"""Immutable disclosure snapshots and point-in-time event selection."""
from datetime import date, datetime
from typing import Literal
import pandas as pd
import exchange_calendars as xcals
from pydantic import BaseModel, ConfigDict, Field, model_validator
from . import data
from .db import DisclosureSnapshot
from .provenance import digest

class Disclosure(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_id: str = Field(min_length=1)
    revision: str = '1'
    amends: str | None = None
    identity_verified: bool = True
    member_id: str = Field(min_length=1)
    owner: Literal['self','spouse','dependent','joint','unknown'] = 'unknown'
    ticker: str = ''
    security_type: str = 'unsupported'
    action: Literal['BUY','SELL','UNSUPPORTED']
    transaction_date: date
    filing_date: date | None = None
    published_at: datetime | None = None
    published_date: date | None = None
    availability_quality: Literal['verified_timestamp','verified_date','unverified'] = 'unverified'
    publication_evidence: str = ''
    source_url: str = ''
    ingested_at: datetime | None = None
    value_low: float = Field(default=0, ge=0, allow_inf_nan=False)
    value_high: float = Field(default=0, ge=0, allow_inf_nan=False)
    original_value_range: str = ''
    source_order: int | None = None
    original: dict = {}

    @model_validator(mode='after')
    def evidence(self):
        if self.value_high < self.value_low: raise ValueError('Invalid value range')
        if self.availability_quality != 'unverified' and not self.publication_evidence:
            raise ValueError('Verified availability requires source publication evidence')
        if self.availability_quality == 'verified_timestamp':
            if self.published_at is None or self.published_at.tzinfo is None: raise ValueError('Publication timestamp requires timezone')
        if self.availability_quality == 'verified_date' and self.published_date is None: raise ValueError('Publication date required')
        published = self.published_date or (self.published_at.date() if self.published_at else None)
        if published and published < self.transaction_date: raise ValueError('Publication precedes transaction')
        return self


def register_snapshot(identifier: str, records: list[dict], metadata: dict) -> dict:
    if not identifier.replace('-', '').replace('_', '').isalnum(): raise ValueError('Invalid snapshot identifier')
    normalized, seen = [], {}
    for record in records:
        d = Disclosure(**record).model_dump(mode='json')
        key = (d['source_id'], d['revision'])
        if key in seen:
            if seen[key] != d: raise ValueError('Conflicting duplicate source identity/revision')
            continue
        seen[key] = d
        normalized.append(d)
    normalized.sort(key=lambda d:(d['source_id'], d['revision']))
    publication_dates=[str(availability(d)) for d in normalized if availability(d) is not None]
    coverage=dict(transaction_start=min((d['transaction_date'] for d in normalized),default=None),transaction_end=max((d['transaction_date'] for d in normalized),default=None),verified_publication_start=min(publication_dates,default=None),verified_publication_end=max(publication_dates,default=None))
    manifest = dict(schema_version=1, **metadata, count=len(normalized), records_sha256=digest(normalized), members=sorted({d['member_id'] for d in normalized}), owners=sorted({d['owner'] for d in normalized}), availability={q:sum(d['availability_quality']==q for d in normalized) for q in ('verified_timestamp','verified_date','unverified')})
    manifest['observed_coverage'] = coverage
    manifest['sha256'] = digest(manifest)
    with data.Session() as db:
        if db.get(DisclosureSnapshot, identifier): raise ValueError('Disclosure snapshot identifiers are immutable')
        db.add(DisclosureSnapshot(id=identifier, manifest=manifest, records=normalized)); db.commit()
    return manifest


def load_snapshot(identifier: str) -> tuple[list[dict], dict]:
    with data.Session() as db:
        row = db.get(DisclosureSnapshot, identifier)
        if row is None: raise ValueError('Unknown disclosure snapshot')
        records, manifest = row.records, dict(row.manifest)
    expected = manifest.pop('sha256')
    if digest(manifest) != expected or digest(records) != manifest['records_sha256']: raise ValueError('Disclosure checksum mismatch')
    manifest['sha256'] = expected
    return records, manifest


def availability(d: dict) -> pd.Timestamp | None:
    if not d.get('identity_verified', True): return None
    quality = d.get('availability_quality')
    if quality == 'verified_timestamp': return pd.Timestamp(d['published_at']).tz_convert('UTC')
    if quality == 'verified_date': return (pd.Timestamp(d['published_date']) + pd.Timedelta(days=1)).tz_localize('America/New_York').tz_convert('UTC') - pd.Timedelta(nanoseconds=1)
    return None


def selected_records(c, records: list[dict]) -> tuple[list[dict], list[dict]]:
    selected, skipped = [], []
    for d in records:
        reason = None
        when = availability(d)
        if d['member_id'] != c.member_id or d['owner'] not in c.owners: reason = 'outside member/owner scope'
        elif when is None: reason = 'unverified availability or identity'
        elif not (pd.Timestamp(c.start).tz_localize('America/New_York') <= when < (pd.Timestamp(c.end)+pd.Timedelta(days=1)).tz_localize('America/New_York')): reason = 'outside experiment publication range; starting portfolio is cash'
        elif d['security_type'] not in ('stock','etf') or d['action'] not in ('BUY','SELL') or not d['ticker']: reason = 'unsupported asset, action or unresolved ticker'
        if reason: skipped.append(dict(source_id=d['source_id'], revision=d['revision'], reason=reason))
        else: selected.append(d)
    return selected, skipped


def events_for_session(records: list[dict], day, seen: set[str]) -> list[dict]:
    opening = xcals.get_calendar('XNYS').session_open(day)
    return sorted([d for d in records if availability(d) < opening and d['source_id']+':'+d['revision'] not in seen], key=lambda d:(availability(d), d.get('source_order') if d.get('source_order') is not None else 0, d['source_id'], d['revision']))
