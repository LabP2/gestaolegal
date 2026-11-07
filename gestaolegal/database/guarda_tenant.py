"""Guarda de execução da multitenancy (docs/plano-multitenant.md, §2.3).

Os repositórios filtram pelo tenant (`BaseRepository.escopo/valores`). A guarda
confere, no momento da execução, que nenhum statement escapou disso: um
listener `before_execute` no `Engine` inspeciona a árvore do statement e recusa
com `TenantLeakError` o que tocar uma tabela de tenant sem o critério
`tabela.c.tenant_id == <tenant ativo>`.

Regras:

- SELECT, UPDATE e DELETE: cada tabela de tenant (ou alias dela) que aparece no
  statement, inclusive em JOIN, subquery e EXISTS, precisa de uma comparação de
  igualdade entre a sua coluna `tenant_id` e um valor igual ao tenant ativo.
  Comparar `tenant_id` com outra coluna não conta. A verificação é por
  presença: um critério dentro de um `OR` passaria (limite conhecido, coberto
  pela revisão e pelos testes de vazamento).
- INSERT: precisa trazer `tenant_id` igual ao tenant ativo em todas as linhas.
  O plano previa preencher o valor quando faltasse; a guarda recusa, porque
  `BaseRepository.valores()` já preenche, e um INSERT sem tenant é sinal de
  código que não passou por ele.
- UPDATE não pode mudar `tenant_id` para outro tenant.
- Sem tenant ativo, recusa qualquer SELECT/INSERT/UPDATE/DELETE, mesmo de
  tabela global. A saída explícita é `sem_tenant(motivo)`, dentro do qual tudo
  é permitido (CRUD da plataforma, descoberta do tenant no login).
- `text()` é recusado. O app não usa SQL textual; os testes, cujas fixtures
  gravam com `text()`, instalam a guarda com `permitir_texto=True`.

Em produção a guarda também recusa, e não só registra: um 500 é melhor que um
vazamento.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

from sqlalchemy import Table, event
from sqlalchemy.engine import Engine
from sqlalchemy.sql import operators
from sqlalchemy.sql.dml import Delete, Insert, Update
from sqlalchemy.sql.elements import BinaryExpression, BindParameter, ClauseElement, TextClause
from sqlalchemy.sql.schema import Column
from sqlalchemy.sql.selectable import Alias, Select

from gestaolegal.database.tables import TABELAS_GLOBAIS
from gestaolegal.utils.request_context import RequestContext

logger = logging.getLogger(__name__)

_DML = (Select, Insert, Update, Delete)


class TenantLeakError(RuntimeError):
    """Statement que tocaria dados fora do tenant ativo."""


def _eh_tabela_de_tenant(origem: Any) -> bool:
    tabela = origem.element if isinstance(origem, Alias) else origem
    return (
        isinstance(tabela, Table)
        and tabela.name not in TABELAS_GLOBAIS
        and "tenant_id" in tabela.c
    )


def _percorrer(elemento: ClauseElement) -> Iterator[ClauseElement]:
    """Todos os nós do statement, sem descer na tabela base de um alias.

    `find_tables` devolve a tabela por trás de um alias como se ela também
    estivesse no FROM; aqui o alias é a origem, e o critério tem de estar nele.
    """
    vistos: set[int] = set()
    pilha = [elemento]
    while pilha:
        atual = pilha.pop()
        if id(atual) in vistos:
            continue
        vistos.add(id(atual))
        yield atual
        if isinstance(atual, Alias) and isinstance(atual.element, Table):
            continue
        pilha.extend(atual.get_children())


def _valor(bind: BindParameter) -> Any:
    return bind.effective_value


def _origens_e_cobertas(stmt: ClauseElement, tenant_id: int) -> tuple[set, set]:
    origens: set = set()
    cobertas: set = set()
    for no in _percorrer(stmt):
        if isinstance(no, (Table, Alias)) and _eh_tabela_de_tenant(no):
            origens.add(no)
        elif isinstance(no, BinaryExpression) and no.operator is operators.eq:
            for coluna, outro in ((no.left, no.right), (no.right, no.left)):
                if (
                    isinstance(coluna, Column)
                    and coluna.name == "tenant_id"
                    and isinstance(outro, BindParameter)
                ):
                    if _valor(outro) != tenant_id:
                        raise TenantLeakError(
                            f"Critério de tenant {_valor(outro)!r} em "
                            f"{coluna.table.name}, mas o tenant ativo é {tenant_id}"
                        )
                    cobertas.add(coluna.table)
    return origens, cobertas


def _linhas_do_insert(stmt: Insert, multiparams: Any, params: Any) -> list[dict]:
    """Valores de cada linha do INSERT, juntando statement e parâmetros."""

    def _chaves(valores: dict) -> dict:
        return {getattr(k, "key", k): v for k, v in valores.items()}

    base = _chaves(stmt._values) if stmt._values else {}
    linhas: list[dict] = []
    if stmt._multi_values:
        for lote in stmt._multi_values:
            linhas.extend({**base, **_chaves(linha)} for linha in lote)

    extras: list[dict] = []
    for fonte in (multiparams, params):
        if isinstance(fonte, dict) and fonte:
            extras.append(fonte)
        elif isinstance(fonte, (list, tuple)):
            for item in fonte:
                if isinstance(item, dict):
                    extras.append(item)
                elif isinstance(item, (list, tuple)):
                    extras.extend(i for i in item if isinstance(i, dict))
    if extras:
        linhas = [{**base, **e} for e in extras] if not linhas else linhas
    if not linhas:
        linhas = [base]
    return linhas


def _valor_bruto(valor: Any) -> Any:
    return _valor(valor) if isinstance(valor, BindParameter) else valor


def _conferir_insert(stmt: Insert, multiparams: Any, params: Any, tenant_id: int) -> None:
    if not _eh_tabela_de_tenant(stmt.table):
        return
    if stmt.select is not None:
        raise TenantLeakError(f"INSERT ... SELECT em {stmt.table.name} não é suportado")
    for linha in _linhas_do_insert(stmt, multiparams, params):
        if "tenant_id" not in linha:
            raise TenantLeakError(f"INSERT em {stmt.table.name} sem tenant_id")
        valor = _valor_bruto(linha["tenant_id"])
        if valor != tenant_id:
            raise TenantLeakError(
                f"INSERT em {stmt.table.name} com tenant_id {valor!r}, "
                f"mas o tenant ativo é {tenant_id}"
            )


def conferir(stmt: Any, multiparams: Any = None, params: Any = None) -> None:
    """Levanta `TenantLeakError` se o statement escapar do tenant ativo."""
    if RequestContext.motivo_sem_tenant() is not None:
        return
    if not isinstance(stmt, _DML):
        return
    tenant_id = RequestContext.get_tenant_ou_none()
    if tenant_id is None:
        raise TenantLeakError(
            "Consulta sem tenant ativo. Use contexto_tenant() ou, para uma "
            "consulta global, sem_tenant(motivo)."
        )

    if isinstance(stmt, Insert):
        _conferir_insert(stmt, multiparams, params, tenant_id)
        return

    if isinstance(stmt, Update) and stmt._values:
        for chave, valor in stmt._values.items():
            if getattr(chave, "key", chave) == "tenant_id" and _valor_bruto(valor) != tenant_id:
                raise TenantLeakError(f"UPDATE muda tenant_id em {stmt.table.name}")

    origens, cobertas = _origens_e_cobertas(stmt, tenant_id)
    faltando = origens - cobertas
    if faltando:
        nomes = sorted(getattr(o, "name", str(o)) for o in faltando)
        raise TenantLeakError(f"{type(stmt).__name__} sem critério de tenant em {nomes}")


def instalar_guarda(engine: Engine, *, permitir_texto: bool = False) -> None:
    """Liga a guarda num engine. Idempotente."""
    if getattr(engine, "_guarda_tenant", None) is not None:
        return

    def _antes(conn, clauseelement, multiparams, params, execution_options):
        if isinstance(clauseelement, TextClause):
            if permitir_texto:
                return
            erro = TenantLeakError("SQL textual (text()) não passa pela guarda de tenant")
        else:
            try:
                conferir(clauseelement, multiparams, params)
                return
            except TenantLeakError as e:
                erro = e
        logger.error("Guarda de tenant recusou statement: %s", erro)
        raise erro

    event.listen(engine, "before_execute", _antes)
    engine._guarda_tenant = _antes  # type: ignore[attr-defined]


def remover_guarda(engine: Engine) -> None:
    funcao = getattr(engine, "_guarda_tenant", None)
    if funcao is not None:
        event.remove(engine, "before_execute", funcao)
        engine._guarda_tenant = None  # type: ignore[attr-defined]
