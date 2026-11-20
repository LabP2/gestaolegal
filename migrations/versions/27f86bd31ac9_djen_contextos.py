"""Contextos de treino e modelos por unidade e NPJ; preserva o legado."""

from alembic import op
from sqlalchemy import (
    MetaData,
    Table,
    Column,
    Integer,
    String,
    JSON,
    DateTime,
    UniqueConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    CheckConstraint,
    Index,
)

revision = "27f86bd31ac9"
down_revision = "19e72ac50bd8"
branch_labels = None
depends_on = None
metadata = MetaData()
for nome in ("tenants", "unidades", "usuarios", "djen_publicacoes"):
    Table(
        nome,
        metadata,
        Column("id", Integer, primary_key=True),
        Column("tenant_id", Integer),
    )


def coluna_tenant():
    return Column(
        "tenant_id", Integer, ForeignKey("tenants.id"), nullable=False, index=True
    )


def coluna_unidade():
    return Column("unidade_id", Integer, nullable=False, index=True)


def unica_tenant_id(t):
    return UniqueConstraint("tenant_id", "id", name=f"uq_{t}_tenant_id_id")


def fk_tenant(t, c, alvo):
    return ForeignKeyConstraint(
        ["tenant_id", c], [f"{alvo}.tenant_id", f"{alvo}.id"], name=f"fkt_{t}_{c}"
    )


djen_contextos = Table(
    "djen_contextos",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("nome", String(150), nullable=False),
    Column("nomes", JSON, nullable=False),
    Column("tribunais", JSON, nullable=False),
    Column("criado_em", DateTime, nullable=False),
    coluna_unidade(),
    coluna_tenant(),
    unica_tenant_id("djen_contextos"),
    fk_tenant("djen_contextos", "unidade_id", "unidades"),
)
djen_modelos = Table(
    "djen_modelos",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("contexto_id", Integer, nullable=False),
    Column("criado_em", DateTime, nullable=False),
    Column("artefato", JSON, nullable=False),
    Column("metricas", JSON, nullable=False),
    coluna_tenant(),
    unica_tenant_id("djen_modelos"),
    fk_tenant("djen_modelos", "contexto_id", "djen_contextos"),
)
djen_publicacao_contextos = Table(
    "djen_publicacao_contextos",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("id_publicacao", Integer, nullable=False),
    Column("contexto_id", Integer, nullable=False),
    Column("rotulo", String(20), nullable=False),
    Column("origem", String(30), nullable=False),
    Column("id_rotulado_por", Integer, nullable=True),
    Column("rotulado_em", DateTime, nullable=True),
    Column("modelo_id", Integer, nullable=True),
    Column("sugestao", String(20), nullable=True),
    Column("probabilidade", String(24), nullable=True),
    coluna_tenant(),
    unica_tenant_id("djen_publicacao_contextos"),
    UniqueConstraint(
        "tenant_id", "id_publicacao", "contexto_id", name="uq_djen_pub_contexto"
    ),
    Index("ix_djen_contexto_rotulo", "tenant_id", "contexto_id", "rotulo"),
    CheckConstraint(
        "rotulo IN ('relevante','irrelevante','nao_classificado')",
        name="ck_djen_ctx_rotulo",
    ),
    fk_tenant("djen_publicacao_contextos", "id_publicacao", "djen_publicacoes"),
    fk_tenant("djen_publicacao_contextos", "contexto_id", "djen_contextos"),
    fk_tenant("djen_publicacao_contextos", "id_rotulado_por", "usuarios"),
    fk_tenant("djen_publicacao_contextos", "modelo_id", "djen_modelos"),
)
djen_contexto_historico = Table(
    "djen_contexto_historico",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("relacao_id", Integer, nullable=False),
    Column("rotulo_anterior", String(20), nullable=False),
    Column("rotulo", String(20), nullable=False),
    Column("origem", String(30), nullable=False),
    Column("id_rotulado_por", Integer, nullable=True),
    Column("rotulado_em", DateTime, nullable=False),
    Column("modelo_id", Integer, nullable=True),
    Column("sugestao", String(20), nullable=True),
    coluna_tenant(),
    fk_tenant("djen_contexto_historico", "relacao_id", "djen_publicacao_contextos"),
    fk_tenant("djen_contexto_historico", "id_rotulado_por", "usuarios"),
    fk_tenant("djen_contexto_historico", "modelo_id", "djen_modelos"),
)

TABELAS = (
    djen_contextos,
    djen_modelos,
    djen_publicacao_contextos,
    djen_contexto_historico,
)


def upgrade():
    for t in TABELAS:
        t.create(op.get_bind())


def downgrade():
    for t in reversed(TABELAS):
        t.drop(op.get_bind())
