"""Add immutable disclosure snapshots and benchmark suites; preserve legacy data."""
from alembic import op
from app.db import DisclosureSnapshot, BenchmarkSuite
revision = '002'
down_revision = '001'

def upgrade():
    for table in (DisclosureSnapshot.__table__, BenchmarkSuite.__table__):
        table.create(op.get_bind(), checkfirst=True)

def downgrade():
    for table in (BenchmarkSuite.__table__, DisclosureSnapshot.__table__):
        table.drop(op.get_bind(), checkfirst=True)
