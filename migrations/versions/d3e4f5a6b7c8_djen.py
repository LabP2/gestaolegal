"""Integração com o DJEN (docs/plano-djen.md, §3).

- `tenants.djen_ativo`: chave do DJEN por NPJ, desligada para todos.
- `processos`: `numero_cnj` (só os 20 dígitos do número, quando seguir o
  padrão CNJ), `djen_pendente` e `djen_consultado_em`, mais
  `UNIQUE (tenant_id, id)`, alvo da FK composta das publicações.
- Tabelas novas `djen_comunicacoes` e `djen_sincronizacoes`, com `tenant_id`
  e FKs compostas, como as da M3.
- `eventos`: `origem` (`manual` | `djen`), `id_djen_comunicacao` (FK composta,
  no máximo um evento por publicação) e `id_criado_por` passa a aceitar nulo
  (só para o evento criado pela rotina, que roda sem usuário).

Os ALTERs em tabelas com dados (`tenants`, `processos`, `eventos`) juntam todas as
operações num único `ALTER TABLE` por tabela, como a M2: uma reconstrução em
vez de uma por operação.

`numero_cnj` é calculado aqui para os processos existentes. Os números fora do
padrão CNJ ficam nulos e não são casados; a migration informa quantos são.
Os processos existentes **não** são marcados como pendentes: o histórico deles
só é buscado pelo botão da tela do processo ou depois de uma alteração do
número (escolha conservadora, registrada no plano).

Só MySQL: o SQLite dos testes usa `create_all` com o `tables.py`.
"""

import logging

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "d3e4f5a6b7c8"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")


def _texto_longo():
    return sa.Text().with_variant(mysql.MEDIUMTEXT(), "mysql")


def _criar_comunicacoes() -> None:
    op.create_table(
        "djen_comunicacoes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("id_djen", sa.BigInteger, nullable=False),
        sa.Column("hash", sa.String(100), nullable=True),
        sa.Column("numero_processo", sa.String(20), nullable=False),
        sa.Column("numero_processo_mascara", sa.String(30), nullable=True),
        sa.Column("data_disponibilizacao", sa.Date, nullable=False),
        sa.Column("sigla_tribunal", sa.String(30), nullable=True),
        sa.Column("nome_orgao", sa.String(300), nullable=True),
        sa.Column("tipo_comunicacao", sa.String(100), nullable=True),
        sa.Column("tipo_documento", sa.String(100), nullable=True),
        sa.Column("nome_classe", sa.String(300), nullable=True),
        sa.Column("texto_html", _texto_longo(), nullable=True),
        sa.Column("texto_plano", _texto_longo(), nullable=True),
        sa.Column("link", sa.String(1000), nullable=True),
        sa.Column("destinatarios", sa.JSON, nullable=True),
        sa.Column("advogados", sa.JSON, nullable=True),
        sa.Column("ativo", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("motivo_cancelamento", sa.Text, nullable=True),
        sa.Column("id_processo", sa.Integer, nullable=True),
        sa.Column("id_caso", sa.Integer, nullable=True),
        sa.Column("situacao", sa.String(12), nullable=False),
        sa.Column("data_situacao", sa.DateTime, nullable=True),
        sa.Column("oab_origem", sa.String(12), nullable=True),
        sa.Column("capturada_em", sa.DateTime, nullable=False),
        sa.Column("atualizada_em", sa.DateTime, nullable=True),
        sa.Column("id_vinculado_por", sa.Integer, nullable=True),
        sa.Column("unidade_id", sa.Integer, nullable=False),
        sa.Column("tenant_id", sa.Integer, nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_djen_comunicacoes_tenant"
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_djen_comunicacoes_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id", "id_djen", name="uq_djen_comunicacoes_tenant_id_djen"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "id_processo"],
            ["processos.tenant_id", "processos.id"],
            name="fkt_djen_comunicacoes_id_processo",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "id_caso"],
            ["casos.tenant_id", "casos.id"],
            name="fkt_djen_comunicacoes_id_caso",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "id_vinculado_por"],
            ["usuarios.tenant_id", "usuarios.id"],
            name="fkt_djen_comunicacoes_id_vinculado_por",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "unidade_id"],
            ["unidades.tenant_id", "unidades.id"],
            name="fkt_djen_comunicacoes_unidade_id",
        ),
    )
    op.create_index("ix_djen_comunicacoes_tenant_id", "djen_comunicacoes", ["tenant_id"])
    op.create_index("ix_djen_comunicacoes_unidade_id", "djen_comunicacoes", ["unidade_id"])
    op.create_index(
        "ix_djen_comunicacoes_numero_processo", "djen_comunicacoes", ["numero_processo"]
    )
    op.create_index(
        "ix_djen_comunicacoes_data_disponibilizacao",
        "djen_comunicacoes",
        ["data_disponibilizacao"],
    )
    op.create_index(
        "ix_djen_comunicacoes_tenant_situacao",
        "djen_comunicacoes",
        ["tenant_id", "situacao"],
    )


def _criar_sincronizacoes() -> None:
    op.create_table(
        "djen_sincronizacoes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("inicio", sa.DateTime, nullable=False),
        sa.Column("fim", sa.DateTime, nullable=True),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("parametros", sa.JSON, nullable=True),
        sa.Column("novas", sa.Integer, nullable=False),
        sa.Column("atualizadas", sa.Integer, nullable=False),
        sa.Column("vinculadas", sa.Integer, nullable=False),
        sa.Column("mensagem", sa.Text, nullable=True),
        sa.Column("tenant_id", sa.Integer, nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_djen_sincronizacoes_tenant"
        ),
    )
    op.create_index(
        "ix_djen_sincronizacoes_tenant_id", "djen_sincronizacoes", ["tenant_id"]
    )


def upgrade() -> None:
    bind = op.get_bind()
    op.execute(
        "ALTER TABLE `tenants` ADD COLUMN djen_ativo TINYINT(1) NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE `processos` "
        "ADD COLUMN numero_cnj VARCHAR(20) NULL, "
        "ADD COLUMN djen_pendente TINYINT(1) NOT NULL DEFAULT 0, "
        "ADD COLUMN djen_consultado_em DATETIME NULL, "
        "ADD CONSTRAINT `uq_processos_tenant_id_id` UNIQUE (tenant_id, id), "
        "ADD INDEX `ix_processos_tenant_numero_cnj` (tenant_id, numero_cnj)"
    )
    op.execute(
        "UPDATE `processos` "
        "SET numero_cnj = REGEXP_REPLACE(numero, '[^0-9]', '') "
        "WHERE numero IS NOT NULL "
        "AND CHAR_LENGTH(REGEXP_REPLACE(numero, '[^0-9]', '')) = 20"
    )
    fora = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM processos "
            "WHERE numero IS NOT NULL AND TRIM(numero) <> '' AND numero_cnj IS NULL"
        )
    ).scalar()
    logger.info(
        "DJEN: %s processo(s) com número fora do padrão CNJ ficaram sem numero_cnj "
        "e não serão casados com publicações.",
        fora,
    )

    _criar_comunicacoes()
    _criar_sincronizacoes()

    # Como na M2: a checagem de FK fica desligada durante o ALTER para o MySQL
    # criar a FK sem copiar a tabela. É seguro: a coluna nova nasce nula.
    bind.execute(sa.text("SET SESSION foreign_key_checks = 0"))
    try:
        op.execute(
            "ALTER TABLE `eventos` "
            "MODIFY COLUMN id_criado_por INT NULL, "
            "ADD COLUMN origem VARCHAR(10) NOT NULL DEFAULT 'manual', "
            "ADD COLUMN id_djen_comunicacao INT NULL, "
            "ADD CONSTRAINT `uq_eventos_tenant_djen_comunicacao` "
            "UNIQUE (tenant_id, id_djen_comunicacao), "
            "ADD CONSTRAINT `fkt_eventos_id_djen_comunicacao` "
            "FOREIGN KEY (tenant_id, id_djen_comunicacao) "
            "REFERENCES djen_comunicacoes (tenant_id, id)"
        )
    finally:
        bind.execute(sa.text("SET SESSION foreign_key_checks = 1"))


def downgrade() -> None:
    # Sem a coluna de origem, um evento do DJEN viraria um evento manual sem
    # autor, e id_criado_por não poderia voltar a NOT NULL. Apagar eventos é
    # decisão humana, não da migration.
    bind = op.get_bind()
    do_djen = bind.execute(
        sa.text("SELECT COUNT(*) FROM eventos WHERE origem <> 'manual' OR id_criado_por IS NULL")
    ).scalar()
    if do_djen:
        raise RuntimeError(
            f"Há {do_djen} evento(s) criados pelo DJEN. Remova-os antes do downgrade."
        )
    op.execute(
        "ALTER TABLE `eventos` "
        "DROP FOREIGN KEY `fkt_eventos_id_djen_comunicacao`, "
        "DROP INDEX `uq_eventos_tenant_djen_comunicacao`, "
        "DROP COLUMN id_djen_comunicacao, "
        "DROP COLUMN origem, "
        "MODIFY COLUMN id_criado_por INT NOT NULL"
    )
    op.drop_table("djen_sincronizacoes")
    op.drop_table("djen_comunicacoes")
    op.execute(
        "ALTER TABLE `processos` "
        "DROP INDEX `ix_processos_tenant_numero_cnj`, "
        "DROP INDEX `uq_processos_tenant_id_id`, "
        "DROP COLUMN djen_consultado_em, "
        "DROP COLUMN djen_pendente, "
        "DROP COLUMN numero_cnj"
    )
    op.execute("ALTER TABLE `tenants` DROP COLUMN djen_ativo")
