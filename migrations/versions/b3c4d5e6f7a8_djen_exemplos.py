"""Acervo e classificação DJEN. Substitui estruturas experimentais descartáveis.

Revisão exclusiva da branch, ainda não aplicada em produção. Eventos existentes
são preservados, apenas sua referência ao acervo experimental é removida.
"""

from alembic import op
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    CheckConstraint,
)
from sqlalchemy.dialects.mysql import MEDIUMTEXT

revision = "b3c4d5e6f7a8"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None
metadata = MetaData()
TEXTO_LONGO = Text().with_variant(MEDIUMTEXT(), "mysql")


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


# Referenced tables exist from earlier revisions.
for nome in ("tenants", "usuarios", "processos", "casos", "unidades"):
    Table(
        nome,
        metadata,
        Column("id", Integer, primary_key=True),
        Column("tenant_id", Integer),
    )
# Acervo canônico: conteúdo único por NPJ, independente das decisões.
djen_publicacoes = Table(
    "djen_publicacoes",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("id_djen", BigInteger, nullable=False),  # `id` da API
    Column("hash", String(100), nullable=True),  # link da certidão
    Column("numero_processo", String(20), nullable=False),
    Column("numero_processo_mascara", String(30), nullable=True),
    Column("data_disponibilizacao", Date, nullable=False),
    Column("sigla_tribunal", String(30), nullable=True),
    Column("nome_orgao", String(300), nullable=True),
    Column("tipo_comunicacao", String(100), nullable=True),
    Column("tipo_documento", String(100), nullable=True),
    Column("nome_classe", String(300), nullable=True),
    # Original da API: conteúdo de terceiros, nunca vai cru para o front.
    Column("texto_html", TEXTO_LONGO, nullable=True),
    Column("texto_plano", TEXTO_LONGO, nullable=True),
    Column("link", String(1000), nullable=True),
    Column("destinatarios", JSON, nullable=True),
    Column("advogados", JSON, nullable=True),
    # False = publicação cancelada no DJEN.
    Column("ativo", Boolean, nullable=False, default=True, server_default="1"),
    Column("motivo_cancelamento", Text, nullable=True),
    Column("capturada_em", DateTime, nullable=False),
    Column("atualizada_em", DateTime, nullable=True),
    coluna_tenant(),
    unica_tenant_id("djen_publicacoes"),
    UniqueConstraint("tenant_id", "id_djen", name="uq_djen_publicacoes_tenant_djen"),
    Index(
        "ix_djen_publicacoes_tenant_data", "tenant_id", "data_disponibilizacao", "id"
    ),
    Index("ix_djen_publicacoes_tenant_numero", "tenant_id", "numero_processo", "id"),
    mysql_charset="utf8mb4",
    mysql_collate="utf8mb4_0900_ai_ci",
)

djen_comunicacoes = Table(
    "djen_comunicacoes",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("id_publicacao", Integer, nullable=False),
    Column("id_processo", Integer, nullable=True),
    Column("id_caso", Integer, nullable=True),
    Column("situacao", String(12), nullable=False),
    Column("data_situacao", DateTime, nullable=True),
    Column("oab_origem", String(12), nullable=True),
    Column("id_vinculado_por", Integer, nullable=True),
    coluna_unidade(),
    coluna_tenant(),
    unica_tenant_id("djen_comunicacoes"),
    UniqueConstraint(
        "tenant_id", "id_publicacao", name="uq_djen_comunicacoes_publicacao"
    ),
    Index("ix_djen_comunicacoes_tenant_situacao", "tenant_id", "situacao"),
    fk_tenant("djen_comunicacoes", "id_publicacao", "djen_publicacoes"),
    fk_tenant("djen_comunicacoes", "id_processo", "processos"),
    fk_tenant("djen_comunicacoes", "id_caso", "casos"),
    fk_tenant("djen_comunicacoes", "id_vinculado_por", "usuarios"),
    fk_tenant("djen_comunicacoes", "unidade_id", "unidades"),
)

ROTULOS_CLASSIFICACAO = ("relevante", "irrelevante", "nao_classificado")
djen_classificacoes = Table(
    "djen_classificacoes",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("id_publicacao", Integer, nullable=False),
    Column("rotulo", String(20), nullable=False),
    Column("origem", String(30), nullable=False),
    Column("id_rotulado_por", Integer, nullable=True),
    Column("rotulado_em", DateTime, nullable=True),
    coluna_tenant(),
    UniqueConstraint(
        "tenant_id", "id_publicacao", name="uq_djen_classificacoes_publicacao"
    ),
    CheckConstraint(
        "rotulo IN ('relevante', 'irrelevante', 'nao_classificado')",
        name="ck_djen_classificacao_rotulo",
    ),
    Index(
        "ix_djen_classificacoes_tenant_rotulo", "tenant_id", "rotulo", "id_publicacao"
    ),
    fk_tenant("djen_classificacoes", "id_publicacao", "djen_publicacoes"),
    fk_tenant("djen_classificacoes", "id_rotulado_por", "usuarios"),
)

djen_classificacao_historico = Table(
    "djen_classificacao_historico",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("id_publicacao", Integer, nullable=False),
    Column("rotulo_anterior", String(20), nullable=False),
    Column("rotulo", String(20), nullable=False),
    Column("origem", String(30), nullable=False),
    Column("id_rotulado_por", Integer, nullable=True),
    Column("rotulado_em", DateTime, nullable=False),
    coluna_tenant(),
    Index("ix_djen_historico_publicacao", "tenant_id", "id_publicacao", "id"),
    fk_tenant("djen_classificacao_historico", "id_publicacao", "djen_publicacoes"),
    fk_tenant("djen_classificacao_historico", "id_rotulado_por", "usuarios"),
)

djen_consultas = Table(
    "djen_consultas",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("origem", String(20), nullable=False),
    Column("parametros", JSON, nullable=False),
    Column("inicio", DateTime, nullable=False),
    Column("fim", DateTime, nullable=True),
    Column("status", String(15), nullable=False),
    Column("id_executor", Integer, nullable=True),
    coluna_unidade(),
    coluna_tenant(),
    unica_tenant_id("djen_consultas"),
    fk_tenant("djen_consultas", "unidade_id", "unidades"),
    fk_tenant("djen_consultas", "id_executor", "usuarios"),
)

djen_consulta_resultados = Table(
    "djen_consulta_resultados",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("id_consulta", Integer, nullable=False),
    Column("id_publicacao", Integer, nullable=False),
    coluna_tenant(),
    UniqueConstraint(
        "tenant_id", "id_consulta", "id_publicacao", name="uq_djen_consulta_resultado"
    ),
    Index("ix_djen_resultado_publicacao", "tenant_id", "id_publicacao"),
    fk_tenant("djen_consulta_resultados", "id_consulta", "djen_consultas"),
    fk_tenant("djen_consulta_resultados", "id_publicacao", "djen_publicacoes"),
)


TABELAS = (
    djen_publicacoes,
    djen_comunicacoes,
    djen_classificacoes,
    djen_classificacao_historico,
    djen_consultas,
    djen_consulta_resultados,
)


def upgrade():
    op.execute(
        "UPDATE eventos SET id_djen_comunicacao = NULL WHERE id_djen_comunicacao IS NOT NULL"
    )
    op.drop_constraint("fkt_eventos_id_djen_comunicacao", "eventos", type_="foreignkey")
    op.drop_table("djen_comunicacoes")
    for tabela in TABELAS:
        tabela.create(op.get_bind())
    op.create_foreign_key(
        "fkt_eventos_id_djen_comunicacao",
        "eventos",
        "djen_comunicacoes",
        ["tenant_id", "id_djen_comunicacao"],
        ["tenant_id", "id"],
    )


def downgrade():
    import runpy
    from pathlib import Path

    op.execute(
        "UPDATE eventos SET id_djen_comunicacao = NULL WHERE id_djen_comunicacao IS NOT NULL"
    )
    op.drop_constraint("fkt_eventos_id_djen_comunicacao", "eventos", type_="foreignkey")
    for tabela in reversed(TABELAS):
        tabela.drop(op.get_bind())
    anterior = runpy.run_path(str(Path(__file__).with_name("d3e4f5a6b7c8_djen.py")))
    anterior["_criar_comunicacoes"]()
    op.create_foreign_key(
        "fkt_eventos_id_djen_comunicacao",
        "eventos",
        "djen_comunicacoes",
        ["tenant_id", "id_djen_comunicacao"],
        ["tenant_id", "id"],
    )
