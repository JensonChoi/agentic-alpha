"""Single persistent worker. PostgreSQL advisory lock prevents duplicate workers."""
import asyncio
import time
from datetime import timedelta
from sqlalchemy import select, text
from .db import Session, Experiment, Record, engine, now, persist_result
from .contracts import Config
from .data import load
from .engine import simulate

def execute(id):
    with Session() as db:
        row=db.get(Experiment,id)
        if row is None or row.status=='canceled': return
        config=Config(**row.config); resume=row.result or None
    def checkpoint(progress,partial):
        with Session() as db:
            e=db.scalar(select(Experiment).where(Experiment.id==id).with_for_update())
            if e is None or e.status=='canceled': return False
            e.progress=progress; e.result=partial; e.updated=now(); db.commit(); return True
    try:
        frame,manifest=load(config.dataset)
        result=asyncio.run(simulate(config,frame,manifest,checkpoint,resume))
        with Session() as db:
            e=db.scalar(select(Experiment).where(Experiment.id==id).with_for_update())
            if e is None or e.status=='canceled' or result.get('canceled'): return
            # Replace a complete deterministic replay atomically; never append duplicate fills.
            for f in result['trades']:
                key=id+':'+f['id']
                if not db.get(Record,key): db.add(Record(id=key,experiment_id=id,kind='fill',payload=f))
            persist_result(db,e,result)
            e.result=result; e.status='waiting' if config.mode=='forward' else ('partial' if result['failures'] else 'completed'); e.updated=now(); db.commit()
    except Exception as exc:
        with Session() as db:
            e=db.scalar(select(Experiment).where(Experiment.id==id).with_for_update())
            if e is None or e.status=='canceled': return
            e.status='failed'; e.error=str(exc); e.updated=now(); db.commit()
def main():
    with engine.connect() as lock:
        if engine.dialect.name=='postgresql' and not lock.scalar(text('SELECT pg_try_advisory_lock(719243)')): raise RuntimeError('Worker already active')
        with Session() as db:
            for e in db.scalars(select(Experiment).where(Experiment.status=='running').with_for_update()): e.status='queued'
            db.commit()
        while True:
            with Session() as db:
                for waiting in db.scalars(select(Experiment).where(Experiment.status=='waiting').with_for_update()):
                    updated=waiting.updated.replace(tzinfo=__import__('datetime').timezone.utc)
                    if now()-updated>timedelta(seconds=60): waiting.status='queued'
                db.commit()
                e=db.scalar(select(Experiment).where(Experiment.status=='queued').order_by(Experiment.created).limit(1).with_for_update())
                if e: e.status='running'; e.updated=now(); id=e.id; db.commit()
                else: id=None
            if id: execute(id)
            else: time.sleep(2)
if __name__=='__main__': main()
