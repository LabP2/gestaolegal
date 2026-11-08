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
- UNION/UNION ALL são conferidos ramo a ramo, inclusive em subqueries.
  Os binds são resolvidos com os parâmetros efetivos de cada execução/lote.
  Construções sem suporte são recusadas; DDL é reservado à gestão do esquema.
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
from sqlalchemy.sql.ddl import DDLElement
from sqlalchemy.sql.elements import BinaryExpression, BindParameter, ClauseElement, TextClause
from sqlalchemy.sql.schema import Column
from sqlalchemy.sql.selectable import Alias, CompoundSelect, Select

from gestaolegal.database.tables import TABELAS_GLOBAIS
from gestaolegal.utils.request_context import RequestContext

logger = logging.getLogger(__name__)

_DML = (Select, CompoundSelect, Insert, Update, Delete)


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


def _valor(bind: BindParameter, params: dict, nomes: dict) -> Any:
    if bind.callable is not None:
        raise TenantLeakError("Bind callable de tenant não é suportado")
    nome = nomes.get(bind, bind.key)
    if nome in params:
        return params[nome]
    return bind.effective_value


def _origens_e_cobertas(stmt: ClauseElement, tenant_id: int, params: dict, nomes: dict) -> tuple[set, set]:
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
                    if _valor(outro, params, nomes) != tenant_id:
                        raise TenantLeakError(
                            f"Critério de tenant {_valor(outro, params, nomes)!r} em "
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


def _valor_bruto(valor: Any, params: dict, nomes: dict) -> Any:
    return _valor(valor, params, nomes) if isinstance(valor, BindParameter) else valor


def _conferir_insert(stmt: Insert, params: dict, tenant_id: int, nomes: dict) -> None:
    if stmt.select is not None:
        raise TenantLeakError(f"INSERT ... SELECT em {stmt.table.name} não é suportado")
    if not _eh_tabela_de_tenant(stmt.table):
        return
    if stmt._multi_values and params:
        raise TenantLeakError("INSERT em lote com parâmetros externos não é suportado")
    for linha in _linhas_do_insert(stmt, None, params):
        if "tenant_id" not in linha:
            raise TenantLeakError(f"INSERT em {stmt.table.name} sem tenant_id")
        valor = _valor_bruto(linha["tenant_id"], params, nomes)
        if valor != tenant_id:
            raise TenantLeakError(
                f"INSERT em {stmt.table.name} com tenant_id {valor!r}, "
                f"mas o tenant ativo é {tenant_id}"
            )


def conferir(stmt: Any, multiparams: Any = None, params: Any = None, *, dialect=None) -> None:
    """Levanta `TenantLeakError` se o statement escapar do tenant ativo."""
    if RequestContext.motivo_sem_tenant() is not None:
        return
    if isinstance(stmt, DDLElement):
        return
    if not isinstance(stmt, _DML):
        raise TenantLeakError(f"Statement não suportado: {type(stmt).__name__}")
    tenant_id = RequestContext.get_tenant_ou_none()
    if tenant_id is None:
        raise TenantLeakError(
            "Consulta sem tenant ativo. Use contexto_tenant() ou, para uma "
            "consulta global, sem_tenant(motivo)."
        )

    lotes = multiparams or [params or {}]
    # Valores passados a execute() substituem os do statement, e só a
    # compilação diz a que bind (inclusive anônimo, como tenant_id_1) cada
    # nome se refere. Compilar custa ~100 µs; sem parâmetros externos, que é o
    # caso dos repositórios, o valor efetivo de cada bind já é o que vai ao
    # banco e a compilação é dispensada.
    externos = any(valores for valores in lotes)
    nomes = stmt.compile(dialect=dialect).bind_names if externos else {}
    for valores in lotes:
        if not isinstance(valores, dict):
            raise TenantLeakError("Parâmetros posicionais não são suportados")
        _conferir_statement(stmt, valores, tenant_id, nomes)


def _conferir_statement(stmt, params: dict, tenant_id: int, nomes: dict) -> None:
    if isinstance(stmt, CompoundSelect):
        for ramo in stmt.selects:
            _conferir_statement(ramo, params, tenant_id, nomes)
        return
    if not isinstance(stmt, (Select, Insert, Update, Delete)):
        raise TenantLeakError(f"Statement não suportado: {type(stmt).__name__}")
    # Uma UNION dentro de subquery também precisa de proteção por ramo.
    for no in _percorrer(stmt):
        if isinstance(no, TextClause):
            raise TenantLeakError("SQL textual dentro de statement não é suportado")
        if isinstance(no, CompoundSelect):
            _conferir_statement(no, params, tenant_id, nomes)
    if isinstance(stmt, Insert):
        _conferir_insert(stmt, params, tenant_id, nomes)
        return

    if isinstance(stmt, Update):
        valores = dict(stmt._ordered_values or (stmt._values or {}).items())
        valores.update(params)
        for chave, valor in valores.items():
            if getattr(chave, "key", chave) == "tenant_id" and _valor_bruto(valor, params, nomes) != tenant_id:
                raise TenantLeakError(f"UPDATE muda tenant_id em {stmt.table.name}")

    origens, cobertas = _origens_e_cobertas(stmt, tenant_id, params, nomes)
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
                conferir(clauseelement, multiparams, params, dialect=conn.dialect)
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
