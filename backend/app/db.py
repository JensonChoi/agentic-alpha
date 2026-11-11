import os
from decimal import Decimal
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import create_engine, String, JSON, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

def now(): return datetime.now(timezone.utc)
def uid(): return str(uuid4())
engine = create_engine(os.getenv('DATABASE_URL', 'sqlite:///./alpha.db'), pool_pre_ping=True)
Session = sessionmaker(engine, expire_on_commit=False)
class Base(DeclarativeBase): pass
class Experiment(Base):
    __tablename__ = 'experiments'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    config: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String, default='created')
    progress: Mapped[float] = mapped_column(default=0.)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(String, default='')
class Dataset(Base):
    __tablename__ = 'market_data_metadata'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    manifest: Mapped[dict] = mapped_column(JSON)
class Record(Base):
    __tablename__ = 'ledger_events'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    experiment_id: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[dict] = mapped_column(JSON)

from sqlalchemy import ForeignKey, Numeric, UniqueConstraint
class StrategyRow(Base):
    __tablename__='strategies'
    id: Mapped[str]=mapped_column(String,primary_key=True)
    version: Mapped[str]=mapped_column(String,default='1')
class ConfigRow(Base):
    __tablename__='experiment_configs'
    experiment_id: Mapped[str]=mapped_column(ForeignKey('experiments.id'),primary_key=True)
    version: Mapped[int]=mapped_column(default=1)
    payload: Mapped[dict]=mapped_column(JSON)
class PortfolioRow(Base):
    __tablename__='portfolios'
    experiment_id: Mapped[str]=mapped_column(ForeignKey('experiments.id'),primary_key=True)
    cash: Mapped[Decimal]=mapped_column(Numeric(30,12))

class PositionRow(Base):
    __tablename__='positions'
    experiment_id: Mapped[str]=mapped_column(ForeignKey('portfolios.experiment_id'),primary_key=True)
    ticker: Mapped[str]=mapped_column(String,primary_key=True)
    quantity: Mapped[Decimal]=mapped_column(Numeric(30,12))

def event_table(name):
    return type(name.title().replace('_',''),(Base,),{
        '__tablename__':name,
        '__annotations__':{'id':Mapped[str],'experiment_id':Mapped[str],'payload':Mapped[dict]},
        'id':mapped_column(String,primary_key=True),
        'experiment_id':mapped_column(ForeignKey('experiments.id'),index=True),
        'payload':mapped_column(JSON)})
SnapshotRow=event_table('portfolio_snapshots')
OrderRow=event_table('simulated_orders')
FillRow=event_table('simulated_fills')
DecisionRow=event_table('agent_decisions')
ToolCallRow=event_table('agent_tool_calls')
RecommendationRow=event_table('agent_recommendations')
MetricRow=event_table('experiment_metrics')
class DisclosureRow(Base):
    __tablename__='disclosures'
    dataset_id: Mapped[str]=mapped_column(ForeignKey('market_data_metadata.id'),primary_key=True)
    source_id: Mapped[str]=mapped_column(String,primary_key=True)
    payload: Mapped[dict]=mapped_column(JSON)

def persist_result(db,e,result):
    db.merge(PortfolioRow(experiment_id=e.id,cash=Decimal(str(result['cash']))))
    db.flush()
    for ticker,qty in result['positions'].items(): db.merge(PositionRow(experiment_id=e.id,ticker=ticker,quantity=Decimal(str(qty))))
    for kind,model in [('equity',SnapshotRow),('orders',OrderRow),('trades',FillRow),('decisions',DecisionRow)]:
        for i,payload in enumerate(result[kind]): db.merge(model(id=f'{e.id}:{i}',experiment_id=e.id,payload=payload))
    for i,decision in enumerate(result['decisions']):
        for j,trace in enumerate(decision.get('trace',[])): db.merge(RecommendationRow(id=f'{e.id}:{i}:{j}',experiment_id=e.id,payload=trace))
    db.merge(MetricRow(id=e.id,experiment_id=e.id,payload=result['metrics']))
