"""FKs compostas com o tenant (multitenant, M3).

Terceiro passo de docs/plano-multitenant.md (§2.1 e §7). Toda FK entre duas
tabelas de NPJ passa a incluir o tenant:

    FOREIGN KEY (tenant_id, x_id) REFERENCES pai (tenant_id, id)

Sem RLS no MySQL, é a única garantia de banco de que um caso do NPJ A não
aponta para usuário, atendido ou unidade do NPJ B. Cada tabela-pai ganha
`UNIQUE (tenant_id, id)`, que é o alvo dessas FKs.

Antes de mexer em qualquer coisa, a migration procura registros cuja FK aponte
para um pai inexistente ou de outro tenant, e aborta com o relatório: corrigir
os dados é decisão humana, nunca da migration.

Os nomes das FKs simples antigas são lidos do banco: a baseline criou várias
sem nome explícito (`casos_ibfk_N` no MySQL). O downgrade recria as simples
com nome escolhido pelo MySQL, como na baseline.

Só MySQL: o SQLite dos testes usa `create_all` com o `tables.py`.
"""

import sqlalchemy as sa
from alembic import op

revision = "c2d3e4f5a6b7"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None

# Lista literal, e não o metadata vivo: uma FK criada depois não pode mudar o
# que esta migration faz. (tabela, coluna, pai, ondelete, nome da composta)
PAIS = (
    "assistencias_judiciarias",
    "assistidos",
    "atendidos",
    "casos",
    "enderecos",
    "eventos",
    "orientacao_juridica",
    "plantao",
    "unidades",
    "usuarios",
)

FKS = (
    ("assistencias_judiciarias", "endereco_id", "enderecos", None, "fkt_assistencias_judiciarias_endereco_id"),
    ("assistencias_judiciarias", "unidade_id", "unidades", None, "fkt_assistencias_judiciarias_unidade_id"),
    ("atendidos", "endereco_id", "enderecos", None, "fkt_atendidos_endereco_id"),
    ("atendidos", "unidade_id", "unidades", None, "fkt_atendidos_unidade_id"),
    ("plantao", "unidade_id", "unidades", None, "fkt_plantao_unidade_id"),
    ("usuarios", "endereco_id", "enderecos", None, "fkt_usuarios_endereco_id"),
    ("arquivos", "id_criado_por", "usuarios", None, "fkt_arquivos_id_criado_por"),
    ("assistidos", "id_atendido", "atendidos", None, "fkt_assistidos_id_atendido"),
    ("casos", "id_colaborador", "usuarios", None, "fkt_casos_id_colaborador"),
    ("casos", "id_criado_por", "usuarios", None, "fkt_casos_id_criado_por"),
    ("casos", "id_estagiario", "usuarios", None, "fkt_casos_id_estagiario"),
    ("casos", "id_modificado_por", "usuarios", None, "fkt_casos_id_modificado_por"),
    ("casos", "id_orientador", "usuarios", None, "fkt_casos_id_orientador"),
    ("casos", "id_usuario_responsavel", "usuarios", None, "fkt_casos_id_usuario_responsavel"),
    ("casos", "unidade_id", "unidades", None, "fkt_casos_unidade_id"),
    ("dias_marcados_plantao", "id_usuario", "usuarios", None, "fkt_dias_marcados_plantao_id_usuario"),
    ("dias_marcados_plantao", "plantao_id", "plantao", None, "fkt_dias_marcados_plantao_plantao_id"),
    ("dias_marcados_plantao", "unidade_id", "unidades", None, "fkt_dias_marcados_plantao_unidade_id"),
    ("dias_plantao", "plantao_id", "plantao", None, "fkt_dias_plantao_plantao_id"),
    ("dias_plantao", "unidade_id", "unidades", None, "fkt_dias_plantao_unidade_id"),
    ("fila_atendimentos", "id_atendido", "atendidos", None, "fkt_fila_atendimentos_id_atendido"),
    ("fila_atendimentos", "unidade_id", "unidades", None, "fkt_fila_atendimentos_unidade_id"),
    ("notificacao", "id_executor_acao", "usuarios", None, "fkt_notificacao_id_executor_acao"),
    ("notificacao", "id_usu_notificar", "usuarios", None, "fkt_notificacao_id_usu_notificar"),
    ("orientacao_juridica", "id_usuario", "usuarios", None, "fkt_orientacao_juridica_id_usuario"),
    ("orientacao_juridica", "unidade_id", "unidades", None, "fkt_orientacao_juridica_unidade_id"),
    ("password_reset_tokens", "usuario_id", "usuarios", None, "fkt_password_reset_tokens_usuario_id"),
    ("registro_entrada", "id_usuario", "usuarios", None, "fkt_registro_entrada_id_usuario"),
    ("registro_entrada", "unidade_id", "unidades", None, "fkt_registro_entrada_unidade_id"),
    ("usuarios_unidades", "unidade_id", "unidades", None, "fkt_usuarios_unidades_unidade_id"),
    ("usuarios_unidades", "usuario_id", "usuarios", None, "fkt_usuarios_unidades_usuario_id"),
    ("arquivosCaso", "id_caso", "casos", "CASCADE", "fkt_arquivosCaso_id_caso"),
    ("assistenciasJudiciarias_xOrientacao_juridica", "id_assistenciaJudiciaria", "assistencias_judiciarias", None, "fkt_assistenciasJudiciarias_xOrientacao_juridica_id_ass_584e6581"),
    ("assistenciasJudiciarias_xOrientacao_juridica", "id_orientacaoJuridica", "orientacao_juridica", None, "fkt_assistenciasJudiciarias_xOrientacao_juridica_id_ori_8abe5e39"),
    ("assistidos_pessoa_juridica", "id_assistido", "assistidos", None, "fkt_assistidos_pessoa_juridica_id_assistido"),
    ("atendido_xOrientacaoJuridica", "id_atendido", "atendidos", None, "fkt_atendido_xOrientacaoJuridica_id_atendido"),
    ("atendido_xOrientacaoJuridica", "id_orientacaoJuridica", "orientacao_juridica", None, "fkt_atendido_xOrientacaoJuridica_id_orientacaoJuridica"),
    ("casos_atendidos", "id_atendido", "atendidos", None, "fkt_casos_atendidos_id_atendido"),
    ("casos_atendidos", "id_caso", "casos", None, "fkt_casos_atendidos_id_caso"),
    ("eventos", "id_caso", "casos", None, "fkt_eventos_id_caso"),
    ("eventos", "id_criado_por", "usuarios", None, "fkt_eventos_id_criado_por"),
    ("eventos", "id_usuario_responsavel", "usuarios", None, "fkt_eventos_id_usuario_responsavel"),
    ("eventos", "unidade_id", "unidades", None, "fkt_eventos_unidade_id"),
    ("historicos", "id_caso", "casos", None, "fkt_historicos_id_caso"),
    ("historicos", "id_usuario", "usuarios", None, "fkt_historicos_id_usuario"),
    ("lembretes", "id_caso", "casos", None, "fkt_lembretes_id_caso"),
    ("lembretes", "id_do_criador", "usuarios", None, "fkt_lembretes_id_do_criador"),
    ("lembretes", "id_usuario", "usuarios", None, "fkt_lembretes_id_usuario"),
    ("lembretes", "unidade_id", "unidades", None, "fkt_lembretes_unidade_id"),
    ("processos", "id_caso", "casos", None, "fkt_processos_id_caso"),
    ("processos", "id_criado_por", "usuarios", None, "fkt_processos_id_criado_por"),
    ("arquivosEvento", "id_caso", "casos", "CASCADE", "fkt_arquivosEvento_id_caso"),
    ("arquivosEvento", "id_evento", "eventos", "CASCADE", "fkt_arquivosEvento_id_evento"),
)


def _nome_unica(tabela: str) -> str:
    return f"uq_{tabela}_tenant_id_id"


def _fk(insp, tabela: str, colunas: list[str], pai: str) -> dict | None:
    for fk in insp.get_foreign_keys(tabela):
        if fk["constrained_columns"] == colunas and fk["referred_table"] == pai:
            return fk
    return None


def _ondelete(fk: dict) -> str | None:
    return (fk.get("options") or {}).get("ondelete")


def _violacoes(bind) -> list[str]:
    """FKs que apontam para pai inexistente ou de outro tenant."""
    problemas = []
    for tabela, coluna, pai, _, _ in FKS:
        total = bind.execute(
            sa.text(
                f"SELECT COUNT(*) FROM `{tabela}` c WHERE c.`{coluna}` IS NOT NULL "
                f"AND NOT EXISTS (SELECT 1 FROM `{pai}` p "
                f"WHERE p.id = c.`{coluna}` AND p.tenant_id = c.tenant_id)"
            )
        ).scalar()
        if total:
            problemas.append(f"{tabela}.{coluna} -> {pai}: {total} registro(s)")
    return problemas


def upgrade() -> None:
    bind = op.get_bind()
    problemas = _violacoes(bind)
    if problemas:
        raise RuntimeError(
            "FKs apontando para registro inexistente ou de outro NPJ. "
            "Corrija os dados antes da M3:\n  " + "\n  ".join(problemas)
        )

    for pai in PAIS:
        op.create_unique_constraint(_nome_unica(pai), pai, ["tenant_id", "id"])

    insp = sa.inspect(bind)
    for tabela, coluna, pai, ondelete, nome in FKS:
        antiga = _fk(insp, tabela, [coluna], pai)
        if antiga is None:
            # Bancos herdados da 2.0 podem não ter a FK simples. A composta
            # entra do mesmo jeito; os dados já foram conferidos acima.
            print(f"M3: {tabela}.{coluna} não tinha FK simples para {pai}")
        else:
            # O ON DELETE do banco vale mais que a lista: a composta herda o
            # comportamento que a produção já tem.
            ondelete = _ondelete(antiga)
            op.drop_constraint(antiga["name"], tabela, type_="foreignkey")
        op.create_foreign_key(
            nome,
            tabela,
            pai,
            ["tenant_id", coluna],
            ["tenant_id", "id"],
            ondelete=ondelete,
        )


def downgrade() -> None:
    bind = op.get_bind()
    for tabela, coluna, pai, ondelete, nome in reversed(FKS):
        composta = _fk(sa.inspect(bind), tabela, ["tenant_id", coluna], pai)
        if composta is not None:
            ondelete = _ondelete(composta)
        op.drop_constraint(nome, tabela, type_="foreignkey")
        # O MySQL cria um índice com o nome da FK quando não há outro que
        # sirva. Sem a FK composta, ele só ocupa espaço.
        indices = {ix["name"] for ix in sa.inspect(bind).get_indexes(tabela)}
        if nome in indices:
            op.drop_index(nome, table_name=tabela)
        # Nomes explícitos das FKs legadas: o MySQL pode descartar o índice
        # simples redundante ao criar a composta. Recriá-lo sem nome muda o
        # esquema no próximo upgrade. Preserve os nomes da cadeia histórica.
        nomes_legados = {
            ("arquivos", "id_criado_por"): "fk_arquivos_criado_por",
            ("orientacao_juridica", "id_usuario"): "fk_orientacao_juridica_usuario",
            ("password_reset_tokens", "usuario_id"): "fk_password_reset_usuario",
            ("usuarios_unidades", "unidade_id"): "fk_usuarios_unidades_unidade",
        }
        op.create_foreign_key(
            nomes_legados.get((tabela, coluna)), tabela, pai, [coluna], ["id"], ondelete=ondelete
        )

    for pai in reversed(PAIS):
        op.drop_constraint(_nome_unica(pai), pai, type_="unique")
