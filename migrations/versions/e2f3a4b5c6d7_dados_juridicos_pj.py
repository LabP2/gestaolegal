"""Habilita dados jurídicos de PJ sem exigir campos fora da ficha atual.

Os registros legados e seus campos são preservados. Campos que a ficha não
coleta passam a aceitar NULL, em vez de gravar respostas inventadas.
"""

import sqlalchemy as sa
from alembic import op

revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None

OPCIONAIS = {
    "situacao_receita": sa.String(100),
    "sede_bh": sa.Boolean(),
    "area_atuacao": sa.String(50),
    "negocio_nascente": sa.Boolean(),
    "orgao_registro": sa.String(100),
    "faturamento_anual": sa.Numeric(10, 2),
    "tem_funcionarios": sa.String(20),
}


def tipos_existentes():
    # MySQL usa MODIFY COLUMN: preservar também charset/collation dos campos legados.
    return {
        coluna["name"]: coluna["type"]
        for coluna in sa.inspect(op.get_bind()).get_columns(
            "assistidos_pessoa_juridica"
        )
    }


def upgrade():
    tipos = tipos_existentes()
    with op.batch_alter_table("assistidos_pessoa_juridica") as batch:
        batch.add_column(
            sa.Column("especificacao_enquadramento", sa.String(200), nullable=True)
        )
        for nome in OPCIONAIS:
            batch.alter_column(nome, existing_type=tipos[nome], nullable=True)


def downgrade():
    # Não substituir NULL por respostas fictícias para restaurar o esquema antigo.
    table = sa.table(
        "assistidos_pessoa_juridica", *(sa.column(nome) for nome in OPCIONAIS)
    )
    nulos = (
        op.get_bind()
        .execute(
            sa.select(sa.func.count())
            .select_from(table)
            .where(sa.or_(*(table.c[nome].is_(None) for nome in OPCIONAIS)))
        )
        .scalar()
    )
    if nulos:
        raise RuntimeError(
            "Há fichas de PJ com campos opcionais vazios. Preencha-os antes do downgrade."
        )
    tipos = tipos_existentes()
    with op.batch_alter_table("assistidos_pessoa_juridica") as batch:
        for nome in OPCIONAIS:
            batch.alter_column(nome, existing_type=tipos[nome], nullable=False)
        batch.drop_column("especificacao_enquadramento")
