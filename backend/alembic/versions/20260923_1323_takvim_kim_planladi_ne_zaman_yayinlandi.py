"""takvim: kim planladi, ne zaman yayinlandi

Revision ID: 9d2e76410c06
Revises: 61b105d2573f
Create Date: 2026-09-23 13:23:57.463054
"""
from alembic import op
import sqlalchemy as sa


revision = '9d2e76410c06'
down_revision = '61b105d2573f'
branch_labels = None
depends_on = None

# Kisitlara ACIKCA ad veriyoruz. Autogenerate bunlari adsiz (None) birakmisti;
# adsiz bir kisit geri alinamaz ("Can't emit DROP CONSTRAINT ... it has no
# name"). Yani downgrade calismiyordu. Ad verilince geri alma da calisir.
FK_PLANLAYAN = "fk_content_calendar_planned_by_user_id_users"
FK_YAYINLAYAN = "fk_content_calendar_published_by_user_id_users"


def upgrade() -> None:
    op.add_column(
        'content_calendar',
        sa.Column('planned_by_user_id', sa.UUID(), nullable=True),
    )
    op.add_column(
        'content_calendar',
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'content_calendar',
        sa.Column('published_by_user_id', sa.UUID(), nullable=True),
    )
    # ondelete='SET NULL': kullanici silinse bile PLAN KAYDI SILINMEZ.
    # CASCADE olsaydi, ayrilan bir calisanin sildigi hesabiyla birlikte
    # gecmis yayin kaydi da yok olurdu.
    op.create_foreign_key(
        FK_PLANLAYAN, 'content_calendar', 'users',
        ['planned_by_user_id'], ['id'], ondelete='SET NULL',
    )
    op.create_foreign_key(
        FK_YAYINLAYAN, 'content_calendar', 'users',
        ['published_by_user_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint(FK_YAYINLAYAN, 'content_calendar', type_='foreignkey')
    op.drop_constraint(FK_PLANLAYAN, 'content_calendar', type_='foreignkey')
    op.drop_column('content_calendar', 'published_by_user_id')
    op.drop_column('content_calendar', 'published_at')
    op.drop_column('content_calendar', 'planned_by_user_id')
