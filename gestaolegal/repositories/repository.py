from typing import Any, Literal, Protocol, TypedDict, TypeVar

from sqlalchemy import ColumnElement, Select, Table, and_, or_
from sqlalchemy.orm import Session

from gestaolegal.common import PageParams, PaginatedResult
from gestaolegal.database.session import get_session
from gestaolegal.models.base_model import BaseModel
from gestaolegal.utils.request_context import RequestContext

T = TypeVar("T", bound=BaseModel)


class WhereClause(TypedDict):
    column: str
    operator: str
    value: (
        str
        | int
        | float
        | bool
        | list[str]
        | list[int]
        | list[float]
        | list[bool]
        | None
    )


class ComplexWhereClause(TypedDict):
    clauses: list["WhereClause | ComplexWhereClause"]
    operator: Literal["and", "or"]


class GetParams(TypedDict):
    where: WhereClause | ComplexWhereClause | None


class SearchParams(TypedDict):
    where: WhereClause | ComplexWhereClause | None
    page_params: PageParams | None


class CountParams(TypedDict):
    where: WhereClause | ComplexWhereClause | None


Q = TypeVar("Q", bound=tuple[object, ...])


def and_clauses(
    *clauses: WhereClause | ComplexWhereClause,
) -> ComplexWhereClause:
    return ComplexWhereClause(clauses=list(clauses), operator="and")


def or_clauses(
    *clauses: WhereClause | ComplexWhereClause,
) -> ComplexWhereClause:
    return ComplexWhereClause(clauses=list(clauses), operator="or")


class BaseRepository:
    session: Session

    def __init__(self):
        self.session = get_session()

    # --- tenant ---------------------------------------------------------------
    # O tenant nunca é parâmetro: vem do contexto (RequestContext), que levanta
    # erro quando não há tenant. Assim, esquecer o tenant quebra em vez de
    # devolver dados de todos os NPJs, ao contrário do filtro opcional de
    # unidade (docs/plano-multitenant.md, §2.2).

    @staticmethod
    def tenant_id() -> int:
        return RequestContext.get_tenant()

    def no_tenant(self, tabela: Table) -> ColumnElement[bool]:
        """Critério do tenant para uma tabela.

        Use direto no ON de um OUTER JOIN: no WHERE, ele descartaria as linhas
        sem par e transformaria o OUTER JOIN em INNER JOIN.
        """
        return tabela.c.tenant_id == self.tenant_id()

    def escopo(self, stmt, *tabelas: Table):
        """Restringe SELECT, UPDATE ou DELETE ao tenant ativo.

        Passe todas as tabelas de tenant do FROM e dos JOINs internos.
        """
        if not tabelas:
            raise ValueError("escopo exige ao menos uma tabela")
        return stmt.where(*(self.no_tenant(tabela) for tabela in tabelas))

    @staticmethod
    def exigir_sem_tenant() -> None:
        """Para as poucas consultas globais (login, token de senha).

        Elas só rodam dentro de `sem_tenant(motivo)`, declarado por quem chama.
        Uma chamada fora dele é erro de programação, não um atalho.
        """
        if RequestContext.motivo_sem_tenant() is None:
            raise RuntimeError("Consulta global fora de sem_tenant()")

    def valores(self, data: dict[str, Any]) -> dict[str, Any]:
        """Dados de INSERT com o tenant ativo. Recusa tenant divergente."""
        tenant_id = self.tenant_id()
        if data.get("tenant_id", tenant_id) != tenant_id:
            raise ValueError("tenant_id diferente do tenant ativo")
        return {**data, "tenant_id": tenant_id}

    def _apply_where_clause(
        self,
        stmt: Select[Q],
        where: WhereClause | ComplexWhereClause | None,
        table: Table,
    ) -> Select[Q]:
        if not where:
            return stmt

        if "clauses" in where:
            complex_where = where
            conditions = [
                self._build_clause(clause, table) for clause in complex_where["clauses"]
            ]

            if not conditions:
                return stmt

            if complex_where["operator"] == "and":
                return stmt.where(and_(*conditions))
            else:
                return stmt.where(or_(*conditions))
        else:
            simple_where = where
            condition = self._build_condition(simple_where, table)
            return stmt.where(condition)

    def _build_clause(
        self, clause: WhereClause | ComplexWhereClause, table: Table
    ) -> ColumnElement[bool]:
        if "clauses" in clause:
            complex_clause = clause
            conditions = [
                self._build_clause(sub_clause, table)
                for sub_clause in complex_clause["clauses"]
            ]
            if complex_clause["operator"] == "and":
                return and_(*conditions)
            else:
                return or_(*conditions)
        else:
            return self._build_condition(clause, table)

    def _build_condition(
        self, clause: WhereClause, table: Table
    ) -> ColumnElement[bool]:
        column = table.c[clause["column"]]
        operator = clause["operator"]
        value = clause["value"]

        if operator == "==":
            return column == value
        elif operator == "!=":
            return column != value
        elif operator == ">":
            return column > value
        elif operator == ">=":
            return column >= value
        elif operator == "<":
            return column < value
        elif operator == "<=":
            return column <= value
        elif operator == "like":
            return column.like(value)
        elif operator == "ilike":
            return column.ilike(value)
        elif operator == "in" and isinstance(value, list):
            return column.in_(value)
        elif operator == "not_in" and isinstance(value, list):
            return column.not_in(value)
        elif operator == "is_null":
            return column.is_(None)
        elif operator == "is_not_null":
            return column.is_not(None)
        else:
            raise ValueError(f"Invalid operator: {operator}")

    def _apply_pagination(
        self, stmt: Select[Q], page_params: PageParams | None
    ) -> Select[Q]:
        if not page_params:
            return stmt

        offset = (page_params["page"] - 1) * page_params["per_page"]
        return stmt.offset(offset).limit(page_params["per_page"])


class Repository(Protocol[T]):
    def find_by_id(self, id: int) -> T | None: ...

    def find_by_email(self, email: str) -> T | None: ...

    def find_one(self, params: SearchParams) -> T | None: ...

    def search(self, params: SearchParams) -> PaginatedResult[T]: ...

    def count(self, params: CountParams) -> int: ...

    def create(self, data: dict) -> int: ...

    def update(self, id: int, data: dict) -> None: ...

    def delete(self, id: int) -> bool: ...
