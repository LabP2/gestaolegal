"""Monitoramento unificado e acesso permanente ao acervo."""

import runpy
from pathlib import Path
import sqlalchemy as sa
from sqlalchemy import (
    Table,
    Column,
    Integer,
    String,
    JSON,
    Boolean,
    DateTime,
    Date,
    UniqueConstraint,
    CheckConstraint,
)
from alembic import op

revision = "19e72ac50bd8"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None
_anterior = runpy.run_path(
    str(Path(__file__).with_name("b3c4d5e6f7a8_djen_exemplos.py"))
)
metadata = _anterior["metadata"]
coluna_unidade = _anterior["coluna_unidade"]
coluna_tenant = _anterior["coluna_tenant"]
fk_tenant = _anterior["fk_tenant"]
# Origem e acesso permanentes: independem da retenção dos logs.
djen_publicacao_unidades = Table(
    "djen_publicacao_unidades",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("id_publicacao", Integer, nullable=False),
    Column("origem", String(20), nullable=False),
    coluna_unidade(),
    coluna_tenant(),
    UniqueConstraint(
        "tenant_id",
        "id_publicacao",
        "unidade_id",
        "origem",
        name="uq_djen_pub_unidade_origem",
    ),
    fk_tenant("djen_publicacao_unidades", "id_publicacao", "djen_publicacoes"),
    fk_tenant("djen_publicacao_unidades", "unidade_id", "unidades"),
)

djen_monitoramentos = Table(
    "djen_monitoramentos",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("tipo", String(15), nullable=False),
    Column("valor", String(150), nullable=False),
    Column("tribunais", JSON, nullable=False),
    Column("ativo", Boolean, nullable=False, server_default="1"),
    Column("removido", Boolean, nullable=False, server_default="0"),
    Column("automatico", Boolean, nullable=False, server_default="0"),
    Column("criado_em", DateTime, nullable=False),
    Column("ultimo_sucesso", Date, nullable=True),
    coluna_unidade(),
    coluna_tenant(),
    UniqueConstraint(
        "tenant_id", "unidade_id", "tipo", "valor", name="uq_djen_monitor_unidade_item"
    ),
    fk_tenant("djen_monitoramentos", "unidade_id", "unidades"),
    CheckConstraint(
        "tipo IN ('oab', 'parte', 'processo')", name="ck_djen_monitor_tipo"
    ),
)


def upgrade():
    bind = op.get_bind()
    djen_publicacao_unidades.create(bind)
    djen_monitoramentos.create(bind)
    op.add_column(
        "djen_consultas",
        sa.Column("modo", sa.String(15), nullable=False, server_default="manual"),
    )
    op.add_column("djen_consultas", sa.Column("execucao_id", sa.Integer, nullable=True))
    op.add_column(
        "djen_consultas",
        sa.Column("encontradas", sa.Integer, nullable=False, server_default="0"),
    )
    op.add_column(
        "djen_consultas",
        sa.Column("novas", sa.Integer, nullable=False, server_default="0"),
    )
    op.add_column("djen_consultas", sa.Column("mensagem", sa.Text, nullable=True))
    op.create_index(
        "ix_djen_consultas_tenant_inicio", "djen_consultas", ["tenant_id", "inicio"]
    )
    op.execute(
        sa.text("""INSERT INTO djen_publicacao_unidades (tenant_id,id_publicacao,unidade_id,origem)
      SELECT DISTINCT q.tenant_id,r.id_publicacao,q.unidade_id,q.origem
      FROM djen_consultas q JOIN djen_consulta_resultados r ON r.id_consulta=q.id AND r.tenant_id=q.tenant_id""")
    )
    rows = bind.execute(sa.text("SELECT * FROM djen_oabs")).mappings()
    for row in rows:
        bind.execute(
            djen_monitoramentos.insert().values(
                tenant_id=row["tenant_id"],
                unidade_id=row["unidade_id"],
                tipo="oab",
                valor=f"{row['numero_oab']}/{row['uf_oab']}",
                tribunais=[],
                ativo=row["ativo"],
                criado_em=row["criado_em"],
            )
        )


def downgrade():
    op.drop_index("ix_djen_consultas_tenant_inicio", table_name="djen_consultas")
    for name in ("mensagem", "novas", "encontradas", "execucao_id", "modo"):
        op.drop_column("djen_consultas", name)
    djen_monitoramentos.drop(op.get_bind())
    djen_publicacao_unidades.drop(op.get_bind())
