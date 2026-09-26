"""AI saglayicilari, gorev atamalari ve duzenlenebilir istemler

Revision ID: c41a7e93b208
Revises: 6b85e61b6196
Create Date: 2026-09-26 22:00:00.000000

'ai_saglayici_turu' YENI bir PostgreSQL turudur. Tur ACIKCA olusturulur ve
sutun tanimi create_type=False ile onu KULLANIR; ikisi birden olusturmaya
calisirsa "type already exists" hatasi cikar. Geri alinirken tur de
DUSURULUR, yoksa tekrar ileri alindiginda ayni hata verir.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'c41a7e93b208'
down_revision = '6b85e61b6196'
branch_labels = None
depends_on = None

TUR_DEGERLERI = ('ANTHROPIC', 'GEMINI', 'MANUS', 'OPENAI_UYUMLU')
TUR = postgresql.ENUM(*TUR_DEGERLERI, name='ai_saglayici_turu', create_type=False)


def upgrade() -> None:
    TUR.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'ai_saglayicilar',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('anahtar', sa.String(length=60), nullable=False),
        sa.Column('ad', sa.String(length=120), nullable=False),
        sa.Column('tur', TUR, nullable=False),
        sa.Column('etkin', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('taban_url', sa.String(length=500), nullable=True),
        sa.Column('model', sa.String(length=200), nullable=True),
        sa.Column('anahtar_ayari', sa.String(length=80), nullable=True),
        sa.Column('yerlesik', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('son_sinama_zamani', sa.DateTime(timezone=True), nullable=True),
        sa.Column('son_sinama_basarili', sa.Boolean(), nullable=True),
        sa.Column('son_sinama_mesaji', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_ai_saglayicilar'),
        sa.UniqueConstraint('anahtar', name='uq_ai_saglayici_anahtar'),
    )
    op.create_index('ix_ai_saglayicilar_anahtar', 'ai_saglayicilar', ['anahtar'])

    op.create_table(
        'ai_gorev_atamalari',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('gorev_turu', sa.String(length=60), nullable=False),
        sa.Column('saglayici_anahtari', sa.String(length=60), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_ai_gorev_atamalari'),
        sa.UniqueConstraint('gorev_turu', name='uq_ai_gorev_turu'),
    )
    op.create_index('ix_ai_gorev_atamalari_gorev_turu', 'ai_gorev_atamalari',
                    ['gorev_turu'])

    op.create_table(
        'istem_sablonlari',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('kod', sa.String(length=60), nullable=False),
        sa.Column('ad', sa.String(length=160), nullable=False),
        sa.Column('akis', sa.String(length=20), nullable=True),
        sa.Column('aciklama', sa.Text(), nullable=False, server_default=''),
        sa.Column('metin', sa.Text(), nullable=False),
        sa.Column('surum', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('etkin', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('yerlesik', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_istem_sablonlari'),
        sa.UniqueConstraint('kod', name='uq_istem_kod'),
    )
    op.create_index('ix_istem_sablonlari_kod', 'istem_sablonlari', ['kod'])


def downgrade() -> None:
    op.drop_index('ix_istem_sablonlari_kod', table_name='istem_sablonlari')
    op.drop_table('istem_sablonlari')
    op.drop_index('ix_ai_gorev_atamalari_gorev_turu', table_name='ai_gorev_atamalari')
    op.drop_table('ai_gorev_atamalari')
    op.drop_index('ix_ai_saglayicilar_anahtar', table_name='ai_saglayicilar')
    op.drop_table('ai_saglayicilar')
    TUR.drop(op.get_bind(), checkfirst=True)
