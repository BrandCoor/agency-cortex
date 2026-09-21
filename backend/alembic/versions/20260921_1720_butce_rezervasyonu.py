"""AI butce rezervasyonu: ai_cost_events.reserved_until

Butce kontrolunun atomik olabilmesi icin, AI cagrisi baslamadan ONCE
tahmini tutar "acik rezervasyon" olarak yazilir. Cagri bitince satir
gercek maliyete cekilir ve bu alan NULL olur.

Revision ID: 4c1d6a2f9b30
Revises: bb9e08a93abd
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = '4c1d6a2f9b30'
down_revision = 'bb9e08a93abd'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'ai_cost_events',
        sa.Column('reserved_until', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f('ix_ai_cost_events_reserved_until'),
        'ai_cost_events',
        ['reserved_until'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_ai_cost_events_reserved_until'), table_name='ai_cost_events')
    op.drop_column('ai_cost_events', 'reserved_until')
