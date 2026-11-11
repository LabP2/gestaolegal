"""Banco de exemplos rotulados do DJEN (docs/plano-processos-avulsos.md,
"Banco de exemplos"; docs/plano-djen.md, §8).

- `djen_exemplos` (nova): publicações julgadas pertinentes, não pertinentes ou
  ainda não revisadas, com o texto plano, para treinar a sugestão automática.
  Uma linha por (`tenant_id`, `id_djen`). FK composta para o usuário que
  rotulou, como as da M3.

Tabela nova em utf8mb4 explícito: o banco de produção ainda tem tabelas e
default legados em latin1, e o texto das publicações traz caracteres fora
dele. O downgrade só apaga a tabela (os exemplos se perdem).

Só MySQL: o SQLite dos testes usa `create_all` com o `tables.py`.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "b3c4d5e6f7a8"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "djen_exemplos",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("id_djen", sa.BigInteger, nullable=False),
        sa.Column("numero_processo", sa.String(20), nullable=False),
        sa.Column("data_disponibilizacao", sa.Date, nullable=False),
        sa.Column("sigla_tribunal", sa.String(30), nullable=True),
        sa.Column("nome_orgao", sa.String(300), nullable=True),
        sa.Column("nome_classe", sa.String(300), nullable=True),
        sa.Column("tipo_comunicacao", sa.String(100), nullable=True),
        sa.Column("tipo_documento", sa.String(100), nullable=True),
        sa.Column("destinatarios", sa.JSON, nullable=True),
        sa.Column(
            "texto_plano", sa.Text().with_variant(mysql.MEDIUMTEXT(), "mysql"), nullable=True
        ),
        sa.Column("termo_busca", sa.String(150), nullable=True),
        sa.Column("rotulo", sa.String(15), nullable=False),
        sa.Column("origem", sa.String(20), nullable=False),
        sa.Column("id_rotulado_por", sa.Integer, nullable=True),
        sa.Column("rotulado_em", sa.DateTime, nullable=True),
        sa.Column("criado_em", sa.DateTime, nullable=False),
        sa.Column("texto_apagado_em", sa.DateTime, nullable=True),
        sa.Column("tenant_id", sa.Integer, nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_djen_exemplos_tenant"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_djen_exemplos_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "id_djen", name="uq_djen_exemplos_tenant_id_djen"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "id_rotulado_por"],
            ["usuarios.tenant_id", "usuarios.id"],
            name="fkt_djen_exemplos_id_rotulado_por",
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("ix_djen_exemplos_tenant_id", "djen_exemplos", ["tenant_id"])
    op.create_index(
        "ix_djen_exemplos_tenant_rotulo", "djen_exemplos", ["tenant_id", "rotulo"]
    )


def downgrade() -> None:
    op.drop_table("djen_exemplos")
