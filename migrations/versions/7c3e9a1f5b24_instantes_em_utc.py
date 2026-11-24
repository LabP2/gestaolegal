"""Padroniza em UTC os instantes que eram gravados no horário de Brasília.

O sistema grava instantes em UTC (ver `gestaolegal/utils/tempo.py`), mas alguns
pontos gravavam o horário de parede de Brasília. O JSON da API marcava esses
valores como GMT, e a tela mostrava três horas a menos.

Convertidos aqui (Brasília → UTC, respeitando o horário de verão de cada data):

- `registro_entrada.data_entrada/data_saida`: todos os registros. A hora é a
  digitada pelo usuário, em Brasília, tanto na 2.0 quanto na 3.0.
- `fila_atendimentos.data_criacao/data_saida`: só os criados pela 3.0, a partir
  de 03/11/2026 (entrada em produção). A 2.0 já gravava em UTC.
- `djen_sincronizacoes.inicio/fim`, `djen_consultas.inicio/fim` e
  `djen_monitoramentos.criado_em`: todos (só existem na 3.0).

Fica de fora `processos.djen_consultado_em`: a coluna recebia UTC de um caminho
e Brasília de outro, e não há como separar as linhas.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from alembic import op

revision = "7c3e9a1f5b24"
down_revision = "5a1c7e9d2b40"
branch_labels = None
depends_on = None

FUSO = ZoneInfo("America/Sao_Paulo")
# Primeira fila gravada pela 3.0 em produção (horário de Brasília).
INICIO_3_0 = datetime(2026, 11, 3)

# (tabela, colunas, filtro opcional sobre os valores ainda em Brasília)
ALVOS = (
    ("registro_entrada", ("data_entrada", "data_saida"), None),
    ("fila_atendimentos", ("data_criacao", "data_saida"), "data_criacao"),
    ("djen_sincronizacoes", ("inicio", "fim"), None),
    ("djen_consultas", ("inicio", "fim"), None),
    ("djen_monitoramentos", ("criado_em",), None),
)


def _para_utc(valor: datetime) -> datetime:
    return valor.replace(tzinfo=FUSO).astimezone(UTC).replace(tzinfo=None)


def _para_brasilia(valor: datetime) -> datetime:
    return valor.replace(tzinfo=UTC).astimezone(FUSO).replace(tzinfo=None)


def _converter(tabela: str, colunas: tuple[str, ...], corte: str | None, fn, limite) -> None:
    conn = op.get_bind()
    sql = f"SELECT id, {', '.join(colunas)} FROM {tabela}"
    params = {}
    if corte:
        sql += f" WHERE {corte} >= :limite"
        params["limite"] = limite
    linhas = conn.execute(sa.text(sql), params).mappings().all()
    atribuicoes = ", ".join(f"{c} = :{c}" for c in colunas)
    update = sa.text(f"UPDATE {tabela} SET {atribuicoes} WHERE id = :id")
    for linha in linhas:
        valores = {
            c: (fn(linha[c]) if isinstance(linha[c], datetime) else linha[c])
            for c in colunas
        }
        conn.execute(update, {"id": linha["id"], **valores})


def upgrade() -> None:
    for tabela, colunas, corte in ALVOS:
        _converter(tabela, colunas, corte, _para_utc, INICIO_3_0)


def downgrade() -> None:
    for tabela, colunas, corte in ALVOS:
        _converter(tabela, colunas, corte, _para_brasilia, _para_utc(INICIO_3_0))
