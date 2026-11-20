"""Cria tenants e administradores da plataforma (multitenant, M1).

Primeiro passo da multitenancy (docs/plano-multitenant.md). Cria as duas
tabelas globais e o tenant 1, a DAJ/UFMG, a quem os registros existentes vão
pertencer na M2. Nenhuma tabela existente é alterada aqui.
"""

from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "a0b1c2d3e4f5"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None

TENANT_INICIAL = {
    "id": 1,
    "nome": "Divisão de Assistência Judiciária",
    "sigla": "DAJ",
    "slug": "daj-ufmg",
    "instituicao": "Faculdade de Direito da UFMG",
    "ativo": True,
}


def upgrade():
    op.create_table(
        "plataforma_admins",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("nome", sa.String(60), nullable=False),
        sa.Column("email", sa.String(80), nullable=False, unique=True),
        sa.Column("senha", sa.String(60), nullable=False),
        sa.Column("ativo", sa.Boolean, nullable=False),
        sa.Column("criado_em", sa.DateTime, nullable=False),
        sa.Column("ultimo_login_em", sa.DateTime, nullable=True),
    )
    tenants = op.create_table(
        "tenants",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("nome", sa.String(150), nullable=False),
        sa.Column("sigla", sa.String(20), nullable=False, unique=True),
        sa.Column("slug", sa.String(40), nullable=False, unique=True),
        sa.Column("instituicao", sa.String(150), nullable=True),
        sa.Column("ativo", sa.Boolean, nullable=False),
        sa.Column("criado_em", sa.DateTime, nullable=False),
        sa.Column(
            "id_criado_por",
            sa.Integer,
            sa.ForeignKey("plataforma_admins.id"),
            nullable=True,
        ),
    )
    op.bulk_insert(tenants, [{**TENANT_INICIAL, "criado_em": datetime.now()}])


def downgrade():
    # Sem a coluna tenant_id (M2), só o tenant 1 tem dados. Outro tenant ou um
    # admin da plataforma já cadastrado seriam perdidos calados.
    bind = op.get_bind()
    outros = bind.execute(
        sa.text("SELECT COUNT(*) FROM tenants WHERE id <> :id"),
        {"id": TENANT_INICIAL["id"]},
    ).scalar()
    admins = bind.execute(sa.text("SELECT COUNT(*) FROM plataforma_admins")).scalar()
    if outros or admins:
        raise RuntimeError(
            "Há tenants além da DAJ/UFMG ou administradores da plataforma "
            "cadastrados. Remova-os antes do downgrade."
        )
    op.drop_table("tenants")
    op.drop_table("plataforma_admins")
