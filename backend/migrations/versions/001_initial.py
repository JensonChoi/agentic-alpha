from app.db import Base
from alembic import op
revision='001'
down_revision=None
def upgrade(): Base.metadata.create_all(op.get_bind())
def downgrade(): Base.metadata.drop_all(op.get_bind())
