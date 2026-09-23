"""Rakip gozlemleri izlenen hesaplara baglandi

Rakip hesaplar artik `tracked_accounts` tablosunda tutuluyor.
`competitor_accounts` HIC KULLANILMAMISTI; kaldiriliyor.

Revision ID: a22e897d4746
Revises: 5489175ca0e3
Create Date: 2026-09-23 17:48:31.668958
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'a22e897d4746'
down_revision = '5489175ca0e3'
branch_labels = None
depends_on = None

FK_YENI = "fk_competitor_observations_tracked_account_id"
FK_ESKI = "competitor_observations_competitor_id_fkey"


def upgrade() -> None:
    # YETIM KAYITLARI TEMIZLE.
    #
    # Mevcut satirlar, kaldirilan `competitor_accounts` tablosuna isaret
    # ediyor. Hicbir kod yolu bu tabloya yazmiyordu, yani uretimde satir
    # olmamali. Yine de VARSA: yeni sutuna koyacak gecerli bir deger
    # uretilemez (hangi izlenen hesaba ait oldugu bilinemez). Uydurma bir
    # baglanti kurmak, gozlemi YANLIS hesaba atfetmek olurdu.
    op.execute("DELETE FROM competitor_observations")

    op.add_column(
        'competitor_observations',
        sa.Column('tracked_account_id', sa.UUID(), nullable=False),
    )
    op.drop_index(
        op.f('ix_competitor_observations_competitor_id'),
        table_name='competitor_observations',
    )
    op.create_index(
        op.f('ix_competitor_observations_tracked_account_id'),
        'competitor_observations', ['tracked_account_id'], unique=False,
    )
    op.drop_constraint(
        op.f(FK_ESKI), 'competitor_observations', type_='foreignkey',
    )
    # Kisita ACIK ad: adsiz kisit geri alinamaz
    # ("Can't emit DROP CONSTRAINT ... it has no name").
    op.create_foreign_key(
        FK_YENI, 'competitor_observations', 'tracked_accounts',
        ['tracked_account_id'], ['id'], ondelete='CASCADE',
    )
    op.drop_column('competitor_observations', 'competitor_id')

    op.drop_index(
        op.f('ix_competitor_accounts_workspace_id'),
        table_name='competitor_accounts',
    )
    op.drop_table('competitor_accounts')


def downgrade() -> None:
    op.create_table(
        'competitor_accounts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column(
            'platform',
            postgresql.ENUM(
                'INSTAGRAM', 'FACEBOOK', 'TIKTOK', 'YOUTUBE', 'LINKEDIN',
                'X', 'PINTEREST', name='platform', create_type=False,
            ),
            nullable=False,
        ),
        sa.Column('username', sa.VARCHAR(length=200), nullable=False),
        sa.Column('display_name', sa.VARCHAR(length=300), nullable=True),
        sa.Column('notes', sa.TEXT(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('competitor_accounts_workspace_id_fkey'), ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('competitor_accounts_pkey')),
    )
    op.create_index(
        op.f('ix_competitor_accounts_workspace_id'),
        'competitor_accounts', ['workspace_id'], unique=False,
    )

    # Ileri yonde yetim kayitlar silindigi gibi, geri donuste de gecerli
    # bir `competitor_id` uretilemez. Satirlar temizlenir.
    op.execute("DELETE FROM competitor_observations")

    op.add_column(
        'competitor_observations',
        sa.Column('competitor_id', sa.UUID(), nullable=False),
    )
    op.drop_constraint(FK_YENI, 'competitor_observations', type_='foreignkey')
    op.create_foreign_key(
        op.f(FK_ESKI), 'competitor_observations', 'competitor_accounts',
        ['competitor_id'], ['id'], ondelete='CASCADE',
    )
    op.drop_index(
        op.f('ix_competitor_observations_tracked_account_id'),
        table_name='competitor_observations',
    )
    op.create_index(
        op.f('ix_competitor_observations_competitor_id'),
        'competitor_observations', ['competitor_id'], unique=False,
    )
    op.drop_column('competitor_observations', 'tracked_account_id')
