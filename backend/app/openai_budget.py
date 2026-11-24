"""Durable reservations for standard-tier GPT-5.5 requests, in nanodollars."""
from contextvars import ContextVar
from uuid import uuid4

from sqlalchemy import select, update

from .db import Experiment, Record

GPT55_SNAPSHOT = 'gpt-5.5-2026-04-23'
PRICING = dict(as_of='2026-11-23', source='https://developers.openai.com/api/docs/models/gpt-5.5',
               tier='standard', usd_per_million=dict(input_tokens=5, cached_input_tokens=0.5, output_tokens=30))
NANOS_PER_USD = 1_000_000_000
RATES = {key: int(value * 1000) for key, value in PRICING['usd_per_million'].items()}
current_budget = ContextVar('current_openai_budget', default=None)


def charges(usage):
    prompt = usage.get('input_tokens')
    cached = usage.get('cached_input_tokens')
    output = usage.get('output_tokens')
    amount = 0
    if prompt is not None and cached is not None:
        if cached > prompt:
            raise ValueError('Invalid cached token count')
        amount += (prompt - cached) * RATES['input_tokens'] + cached * RATES['cached_input_tokens']
    if output is not None:
        amount += output * RATES['output_tokens']
    return amount


class RequestBudget:
    def __init__(self, session, experiment_id, limit_usd):
        self.session = session
        self.experiment_id = experiment_id
        self.limit = int(limit_usd * NANOS_PER_USD)

    def entries(self, db):
        return db.scalars(select(Record).where(Record.experiment_id == self.experiment_id,
                                              Record.kind == 'openai_request')).all()

    def reserve(self, body, attempt_number=1):
        # Byte-level tokenization uses at most one token per UTF-8 byte.
        # Allow 256 extra tokens for framing the two fixed text-only messages.
        input_bound = 256 + sum(len(m['content'].encode('utf-8')) for m in body['messages'])
        if input_bound > 272_000:
            raise ValueError('Request exceeds standard short-context pricing range')
        maximum = input_bound * RATES['input_tokens'] + body['max_completion_tokens'] * RATES['output_tokens']
        with self.session.begin() as db:
            # Serialize reservations on both SQLite and PostgreSQL before reading balances.
            db.execute(update(Experiment).where(Experiment.id == self.experiment_id).values(updated=Experiment.updated))
            held = sum(r.payload['held_nanos'] for r in self.entries(db))
            if held + maximum > self.limit:
                return None
            request_id = str(uuid4())
            db.add(Record(id=request_id, experiment_id=self.experiment_id, kind='openai_request',
                          payload=dict(held_nanos=maximum, maximum_nanos=maximum, attempt=attempt_number, usage={})))
        return request_id

    def settle(self, request_id, usage):
        with self.session.begin() as db:
            entry = db.get(Record, request_id)
            maximum = entry.payload['maximum_nanos']
            # Unknown input/cache or output usage retains its full reservation.
            complete = all(usage.get(k) is not None for k in RATES)
            amount = charges(usage) if complete else maximum
            entry.payload = {**entry.payload, 'held_nanos': amount, 'usage': usage}
