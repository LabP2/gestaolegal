"""Coluna tenant_id em todas as tabelas do NPJ (multitenant, M2).

Segundo passo de docs/plano-multitenant.md. Cada uma das 28 tabelas ganha
`tenant_id`, preenchido com o tenant 1 (DAJ/UFMG, criado na M1): todos os
registros existentes, de Belo Horizonte e de Nova Lima, são desse NPJ.

Como na migration de unidades, a coluna entra nula, é preenchida e só então
vira NOT NULL, com índice e FK para `tenants`. As unicidades que valiam para a
base inteira passam a valer dentro de cada tenant. O e-mail de `usuarios`
continua único na plataforma: é ele que identifica o NPJ no login.

As FKs compostas `(tenant_id, x_id)` ficam para a M3.
"""

import sqlalchemy as sa
from alembic import op

revision = "b1c2d3e4f5a6"
down_revision = "a0b1c2d3e4f5"
branch_labels = None
depends_on = None

TENANT_INICIAL_ID = 1

# Lista literal, e não o metadata vivo: uma tabela criada depois não pode mudar
# o que esta migration faz.
TABELAS = (
    "documentos_roteiro",
    "enderecos",
    "unidades",
    "assistencias_judiciarias",
    "atendidos",
    "plantao",
    "usuarios",
    "arquivos",
    "assistidos",
    "casos",
    "dias_marcados_plantao",
    "dias_plantao",
    "fila_atendimentos",
    "notificacao",
    "orientacao_juridica",
    "password_reset_tokens",
    "registro_entrada",
    "usuarios_unidades",
    "arquivosCaso",
    "assistenciasJudiciarias_xOrientacao_juridica",
    "assistidos_pessoa_juridica",
    "atendido_xOrientacaoJuridica",
    "casos_atendidos",
    "eventos",
    "historicos",
    "lembretes",
    "processos",
    "arquivosEvento",
)

# (tabela, coluna, unicidade nova composta com o tenant, nome usado no
# downgrade). No upgrade, o nome antigo é lido do banco, nunca assumido: a
# baseline criou várias unicidades sem nome explícito.
UNICIDADES = (
    ("processos", "numero", "uq_processos_tenant_numero", "numero"),
    ("assistencias_judiciarias", "email", "uq_assistencias_tenant_email", "email"),
    ("unidades", "nome", "uq_unidades_tenant_nome", "uq_unidades_nome"),
    ("unidades", "sigla", "uq_unidades_tenant_sigla", "uq_unidades_sigla"),
)


def _fk(tabela: str) -> str:
    return f"fk_{tabela}_tenant"


def _ix(tabela: str) -> str:
    return f"ix_{tabela}_tenant_id"


def _unica_de_uma_coluna(tabela: str, coluna: str) -> str:
    """Nome da unicidade (ou índice único) que cobre só `coluna`."""
    insp = sa.inspect(op.get_bind())
    for uc in insp.get_unique_constraints(tabela):
        if uc["column_names"] == [coluna] and uc["name"]:
            return uc["name"]
    for ix in insp.get_indexes(tabela):
        if ix.get("unique") and ix["column_names"] == [coluna]:
            return ix["name"]
    raise RuntimeError(f"Unicidade de {tabela}.{coluna} não encontrada")


def upgrade() -> None:
    # Um único ALTER TABLE por tabela: coluna, índice, FK e unicidades juntos
    # custam uma reconstrução, em vez de uma por operação. O DEFAULT preenche
    # as linhas existentes sem UPDATE e sai em seguida (só metadados), para
    # que todo INSERT continue obrigado a informar o tenant.
    #
    # A checagem de FK fica desligada durante o ALTER para o MySQL criar a FK
    # sem copiar a tabela (ALGORITHM=COPY). É seguro: toda linha recebe o
    # tenant inicial, cuja existência é conferida antes.
    bind = op.get_bind()
    existe = bind.execute(
        sa.text("SELECT COUNT(*) FROM tenants WHERE id = :id"), {"id": TENANT_INICIAL_ID}
    ).scalar()
    if not existe:
        raise RuntimeError(f"Tenant {TENANT_INICIAL_ID} não existe; aplique a M1 antes.")

    unicidades: dict[str, list[str]] = {}
    for tabela, coluna, nova, _ in UNICIDADES:
        antiga = _unica_de_uma_coluna(tabela, coluna)
        unicidades.setdefault(tabela, []).extend(
            [f"DROP INDEX `{antiga}`", f"ADD CONSTRAINT `{nova}` UNIQUE (tenant_id, `{coluna}`)"]
        )

    bind.execute(sa.text("SET SESSION foreign_key_checks = 0"))
    try:
        for tabela in TABELAS:
            partes = [
                f"ADD COLUMN tenant_id INT NOT NULL DEFAULT {TENANT_INICIAL_ID}",
                f"ADD INDEX `{_ix(tabela)}` (tenant_id)",
                f"ADD CONSTRAINT `{_fk(tabela)}` FOREIGN KEY (tenant_id) REFERENCES tenants (id)",
                *unicidades.get(tabela, []),
            ]
            op.execute(f"ALTER TABLE `{tabela}` " + ", ".join(partes))
            op.execute(f"ALTER TABLE `{tabela}` ALTER COLUMN tenant_id DROP DEFAULT")
    finally:
        bind.execute(sa.text("SET SESSION foreign_key_checks = 1"))


def downgrade() -> None:
    # Sem tenant_id, dados de dois NPJs ficariam misturados, e as unicidades
    # globais nem poderiam ser recriadas.
    bind = op.get_bind()
    for tabela in TABELAS:
        outros = bind.execute(
            sa.text(f"SELECT COUNT(*) FROM `{tabela}` WHERE tenant_id <> :id"),
            {"id": TENANT_INICIAL_ID},
        ).scalar()
        if outros:
            raise RuntimeError(
                f"Há registros de outros NPJs em {tabela}. "
                "Remova-os antes do downgrade."
            )

    for tabela, coluna, nova, antiga in reversed(UNICIDADES):
        op.drop_constraint(nova, tabela, type_="unique")
        op.create_unique_constraint(antiga, tabela, [coluna])

    for tabela in reversed(TABELAS):
        op.drop_constraint(_fk(tabela), tabela, type_="foreignkey")
        op.drop_index(_ix(tabela), table_name=tabela)
        op.drop_column(tabela, "tenant_id")
