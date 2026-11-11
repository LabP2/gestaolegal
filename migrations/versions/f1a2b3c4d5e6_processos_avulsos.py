"""Processos sem caso e partes sem triagem (docs/plano-processos-avulsos.md, §1).

- `processos.id_caso` passa a aceitar nulo (processo sem caso) e o processo
  ganha `unidade_id` (`coluna_unidade()`, NOT NULL, FK composta), preenchida
  aqui com a unidade do caso.
- `processo_partes` (nova): partes do processo sem caso.
- `atendidos.sem_triagem` (nova, default 0) e oito colunas de dados pessoais
  passam a aceitar nulo no banco, para o cadastro simplificado da parte. O
  cadastro normal continua exigindo tudo pela validação de entrada.
- `atendido_nomes` (nova): variações do nome, para a busca no DJEN.

As colunas de `atendidos` são legadas, algumas em latin1: o MODIFY repete o
tipo, o charset e a collation lidos do `information_schema`, para mudar só a
nulidade.

O downgrade recusa (RuntimeError) quando já há processo sem caso, parte sem
triagem ou atendido com algum desses campos vazio: voltar a NOT NULL exigiria
apagar ou inventar dados, e isso é decisão humana.

Só MySQL: o SQLite dos testes usa `create_all` com o `tables.py`.
"""

import sqlalchemy as sa
from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None

COLUNAS_ATENDIDO = (
    "data_nascimento",
    "cpf",
    "celular",
    "email",
    "estado_civil",
    "como_conheceu",
    "procurou_outro_local",
    "pj_constituida",
)


def _definicoes_atendido(bind, nulo: bool) -> list[str]:
    """`MODIFY COLUMN` de cada coluna, com tipo, charset e collation atuais."""
    linhas = bind.execute(
        sa.text(
            "SELECT COLUMN_NAME, COLUMN_TYPE, CHARACTER_SET_NAME, COLLATION_NAME "
            "FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'atendidos' "
            "AND COLUMN_NAME IN :colunas"
        ).bindparams(sa.bindparam("colunas", expanding=True)),
        {"colunas": list(COLUNAS_ATENDIDO)},
    ).all()
    por_nome = {linha[0]: linha for linha in linhas}
    faltando = set(COLUNAS_ATENDIDO) - set(por_nome)
    if faltando:
        raise RuntimeError(f"atendidos sem as colunas esperadas: {sorted(faltando)}")
    definicoes = []
    for coluna in COLUNAS_ATENDIDO:
        _, tipo, charset, collation = por_nome[coluna]
        texto = f" CHARACTER SET {charset} COLLATE {collation}" if charset else ""
        definicoes.append(
            f"MODIFY COLUMN `{coluna}` {tipo}{texto} {'NULL' if nulo else 'NOT NULL'}"
        )
    return definicoes


def upgrade() -> None:
    bind = op.get_bind()

    # processos: unidade do caso, depois NOT NULL com FK composta.
    op.execute(
        "ALTER TABLE `processos` "
        "MODIFY COLUMN id_caso INT NULL, "
        "ADD COLUMN unidade_id INT NULL"
    )
    op.execute(
        "UPDATE `processos` p JOIN `casos` c "
        "ON c.id = p.id_caso AND c.tenant_id = p.tenant_id "
        "SET p.unidade_id = c.unidade_id"
    )
    sem_unidade = bind.execute(
        sa.text("SELECT COUNT(*) FROM processos WHERE unidade_id IS NULL")
    ).scalar()
    if sem_unidade:
        raise RuntimeError(
            f"{sem_unidade} processo(s) sem caso válido para herdar a unidade."
        )
    # Como na M2 e na do DJEN: a checagem de FK fica desligada durante o ALTER
    # para o MySQL criar a FK sem copiar a tabela. É seguro: os valores vêm do
    # caso, que já tem FK composta para a unidade do mesmo tenant.
    bind.execute(sa.text("SET SESSION foreign_key_checks = 0"))
    try:
        op.execute(
            "ALTER TABLE `processos` "
            "MODIFY COLUMN unidade_id INT NOT NULL, "
            "ADD INDEX `ix_processos_unidade_id` (unidade_id), "
            "ADD CONSTRAINT `fkt_processos_unidade_id` "
            "FOREIGN KEY (tenant_id, unidade_id) REFERENCES unidades (tenant_id, id)"
        )
    finally:
        bind.execute(sa.text("SET SESSION foreign_key_checks = 1"))

    op.execute(
        "ALTER TABLE `atendidos` "
        "ADD COLUMN sem_triagem TINYINT(1) NOT NULL DEFAULT 0, "
        + ", ".join(_definicoes_atendido(bind, nulo=True))
    )

    op.create_table(
        "processo_partes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("id_processo", sa.Integer, nullable=False),
        sa.Column("id_atendido", sa.Integer, nullable=False),
        sa.Column("polo", sa.String(10), nullable=True),
        sa.Column("tenant_id", sa.Integer, nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_processo_partes_tenant"
        ),
        sa.UniqueConstraint(
            "tenant_id", "id_processo", "id_atendido", name="uq_processo_partes_tenant_parte"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "id_processo"],
            ["processos.tenant_id", "processos.id"],
            name="fkt_processo_partes_id_processo",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "id_atendido"],
            ["atendidos.tenant_id", "atendidos.id"],
            name="fkt_processo_partes_id_atendido",
        ),
    )
    op.create_index("ix_processo_partes_tenant_id", "processo_partes", ["tenant_id"])

    op.create_table(
        "atendido_nomes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("id_atendido", sa.Integer, nullable=False),
        sa.Column("nome", sa.String(150), nullable=False),
        sa.Column("tenant_id", sa.Integer, nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_atendido_nomes_tenant"
        ),
        sa.UniqueConstraint(
            "tenant_id", "id_atendido", "nome", name="uq_atendido_nomes_tenant_nome"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "id_atendido"],
            ["atendidos.tenant_id", "atendidos.id"],
            name="fkt_atendido_nomes_id_atendido",
        ),
    )
    op.create_index("ix_atendido_nomes_tenant_id", "atendido_nomes", ["tenant_id"])


def downgrade() -> None:
    bind = op.get_bind()
    sem_caso = bind.execute(
        sa.text("SELECT COUNT(*) FROM processos WHERE id_caso IS NULL")
    ).scalar()
    vazios = " OR ".join(f"`{c}` IS NULL" for c in COLUNAS_ATENDIDO)
    simplificados = bind.execute(
        sa.text(f"SELECT COUNT(*) FROM atendidos WHERE sem_triagem = 1 OR {vazios}")
    ).scalar()
    if sem_caso or simplificados:
        raise RuntimeError(
            f"Há {sem_caso} processo(s) sem caso e {simplificados} atendido(s) do "
            "cadastro simplificado. Remova-os antes do downgrade."
        )
    op.drop_table("atendido_nomes")
    op.drop_table("processo_partes")
    op.execute(
        "ALTER TABLE `atendidos` DROP COLUMN sem_triagem, "
        + ", ".join(_definicoes_atendido(bind, nulo=False))
    )
    op.execute(
        "ALTER TABLE `processos` "
        "DROP FOREIGN KEY `fkt_processos_unidade_id`, "
        # Índice que o MySQL cria para a FK composta.
        "DROP INDEX `fkt_processos_unidade_id`, "
        "DROP INDEX `ix_processos_unidade_id`, "
        "DROP COLUMN unidade_id, "
        "MODIFY COLUMN id_caso INT NOT NULL"
    )
