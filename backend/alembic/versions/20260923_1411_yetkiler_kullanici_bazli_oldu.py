"""Yetkiler kullanici bazli oldu

Izinler artik (musteri, rol) ciftine degil, KULLANICIYA ait.

Revision ID: ccd07a5a0fbc
Revises: 9d2e76410c06
Create Date: 2026-09-23 14:11:51.028387
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'ccd07a5a0fbc'
down_revision = '9d2e76410c06'
branch_labels = None
depends_on = None

PAKET = sa.Enum('ADMIN', 'STRATEGIST', 'EDITOR', 'VIEWER', name='permission_package')


def upgrade() -> None:
    # --- 1) Yeni yapilar ----------------------------------------------------
    op.create_table(
        'user_permissions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('permission', sa.String(length=60), nullable=False),
        sa.Column('allowed', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'permission', name='uq_user_permission'),
    )
    op.create_index(op.f('ix_user_permissions_permission'), 'user_permissions',
                    ['permission'], unique=False)
    op.create_index(op.f('ix_user_permissions_user_id'), 'user_permissions',
                    ['user_id'], unique=False)

    # server_default ZORUNLU: mevcut satirlari olan bir tabloya
    # NOT NULL sutun eklerken varsayilan verilmezse migration COKER.
    # (Bos test veritabaninda fark edilmez, URETIMDE coker.)
    PAKET.create(op.get_bind(), checkfirst=True)
    op.add_column(
        'users',
        sa.Column('permission_package', PAKET, nullable=False,
                  server_default='VIEWER'),
    )

    # --- 2) KIMSE YETKI KAYBETMESIN -----------------------------------------
    #
    # Herkesin paketi, sahip oldugu EN YUKSEK musteri rolunden turetilir.
    # Once en dusukten baslanir, sonra yukarisi uzerine yazar; boylece
    # birden fazla musteride farkli rolleri olan kisi EN GENIS yetkiyi alir.
    for rol, paket in [
        ('VIEWER', 'VIEWER'),
        ('EDITOR', 'EDITOR'),
        ('STRATEGIST', 'STRATEGIST'),
        ('ADMIN', 'ADMIN'),
        ('OWNER', 'ADMIN'),   # Musteri sahipligi sistem capinda yoneticiliktir
    ]:
        # role bir PostgreSQL enum'u; parametre metin olarak gelir.
        # Acik cevrim olmadan "operator does not exist" hatasi verir.
        op.execute(sa.text(
            "UPDATE users SET permission_package = CAST(:paket AS permission_package) "
            "WHERE id IN ("
            "  SELECT user_id FROM workspace_members "
            "  WHERE CAST(role AS text) = :rol"
            ")"
        ).bindparams(paket=paket, rol=rol))

    # Sistem yoneticisi zaten her seyi yapar; paketi de ona gore yazilir.
    op.execute("UPDATE users SET permission_package = 'ADMIN' WHERE is_superuser")

    # --- 3) Eski yapilar -----------------------------------------------------
    #
    # role_grants: rol bazli ozellestirmeler. Kullaniciya birebir
    # cevrilemezler (bir rolde birden fazla kisi olabilir). Bu ozellik
    # yalnizca birkac saat yayinda kaldi; satirlar TASINMAZ, silinir.
    # Kullanicinin izinleri paket varsayilanindan baslar.
    op.drop_index(op.f('ix_role_grants_permission'), table_name='role_grants')
    op.drop_index(op.f('ix_role_grants_role'), table_name='role_grants')
    op.drop_index(op.f('ix_role_grants_workspace_id'), table_name='role_grants')
    op.drop_table('role_grants')

    # Uyelik artik yetki tasimaz; yalnizca erisimi belirler.
    op.drop_column('workspace_members', 'role')


def downgrade() -> None:
    # Geri alirken herkes 'admin' olur: yetkiyi DARALTMAK veri kaybi
    # olmaz ama yanlis kisiyi disarida birakabilirdi. Geri alma bir
    # kurtarma islemidir; kimsenin kilitlenmemesi onceliklidir.
    op.add_column(
        'workspace_members',
        sa.Column('role',
                  postgresql.ENUM('OWNER', 'ADMIN', 'STRATEGIST', 'EDITOR', 'VIEWER',
                                  name='workspace_role', create_type=False),
                  nullable=False, server_default='ADMIN'),
    )
    op.alter_column('workspace_members', 'role', server_default=None)

    op.create_table(
        'role_grants',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('role',
                  postgresql.ENUM('OWNER', 'ADMIN', 'STRATEGIST', 'EDITOR', 'VIEWER',
                                  name='workspace_role', create_type=False),
                  nullable=False),
        sa.Column('permission', sa.VARCHAR(length=60), nullable=False),
        sa.Column('allowed', sa.BOOLEAN(), nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'],
                                name=op.f('role_grants_workspace_id_fkey'),
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('role_grants_pkey')),
        sa.UniqueConstraint('workspace_id', 'role', 'permission',
                            name=op.f('uq_role_grant')),
    )
    op.create_index(op.f('ix_role_grants_workspace_id'), 'role_grants',
                    ['workspace_id'], unique=False)
    op.create_index(op.f('ix_role_grants_role'), 'role_grants', ['role'], unique=False)
    op.create_index(op.f('ix_role_grants_permission'), 'role_grants',
                    ['permission'], unique=False)

    op.drop_index(op.f('ix_user_permissions_user_id'), table_name='user_permissions')
    op.drop_index(op.f('ix_user_permissions_permission'), table_name='user_permissions')
    op.drop_table('user_permissions')

    op.drop_column('users', 'permission_package')
    PAKET.drop(op.get_bind(), checkfirst=True)
