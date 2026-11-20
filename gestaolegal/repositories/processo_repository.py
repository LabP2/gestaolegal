from datetime import date
from typing import Any, NoReturn
import re

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, insert, or_, select
from sqlalchemy import update as sql_update
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from gestaolegal.common import PageParams, PaginatedResult
from gestaolegal.database.tables import (
    atendido_nomes,
    atendidos,
    casos,
    casos_atendidos,
    djen_comunicacoes,
    processo_partes,
    processos,
)
from gestaolegal.models.processo import ParteProcesso, Processo, ProcessoListItem
from gestaolegal.exceptions import ValidationException
from gestaolegal.repositories.repository import (
    BaseRepository,
    CountParams,
    SearchParams,
)
from gestaolegal.utils.dataclass_utils import from_dict


def _tratar_numero_duplicado(error: IntegrityError) -> NoReturn:
    """Traduz apenas a restrição do número; outros erros continuam técnicos."""
    message = str(error.orig)
    args = getattr(error.orig, "args", ())
    mysql_duplicate = (
        args and args[0] == 1062
        and re.search(
            r"for key ['`](?:processos\.)?uq_processos_tenant_numero['`]", message
        )
    )
    sqlite_duplicate = (
        message == "UNIQUE constraint failed: processos.tenant_id, processos.numero"
    )
    if mysql_duplicate or sqlite_duplicate:
        raise ValidationException(
            "Já existe um processo cadastrado com esse número.", field="numero"
        ) from error
    raise error


class ProcessoRepository(BaseRepository):
    session: Session

    def __init__(self):
        super().__init__()

    def find_by_id(self, id: int) -> Processo | None:
        stmt = self.escopo(select(processos).where(processos.c.id == id), processos)
        result = self.session.execute(stmt).one_or_none()
        return from_dict(Processo, dict(result._mapping)) if result else None

    def bloquear(self, id: int) -> Processo | None:
        """Lê o estado atual e serializa associação e captura na transação."""
        row = self.session.execute(self.escopo(
            select(processos).where(processos.c.id == id).with_for_update(),
            processos,
        )).one_or_none()
        return from_dict(Processo, dict(row._mapping)) if row else None

    def find_by_caso_id(self, caso_id: int) -> list[Processo]:
        stmt = self.escopo(
            select(processos).where(processos.c.id_caso == caso_id), processos
        )
        results = self.session.execute(stmt).all()
        return [from_dict(Processo, dict(row._mapping)) for row in results]

    def search(self, params: SearchParams) -> PaginatedResult[Processo]:
        stmt = self.escopo(
            select(processos, func.count().over().label("total_count")), processos
        )

        stmt = self._apply_where_clause(stmt, params.get("where"), processos)
        stmt = stmt.order_by(processos.c.id.desc())
        stmt = self._apply_pagination(stmt, params.get("page_params"))

        results = self.session.execute(stmt).all()
        total = results[0].total_count if results else 0

        items = [from_dict(Processo, dict(row._mapping)) for row in results]
        page_params = params.get("page_params")
        return PaginatedResult(
            items=items,
            total=total,
            page=page_params["page"] if page_params else 1,
            per_page=page_params["per_page"] if page_params else total,
        )

    def find_one(self, params: SearchParams) -> Processo | None:
        stmt = self.escopo(select(processos), processos)
        stmt = self._apply_where_clause(stmt, params.get("where"), processos)
        result = self.session.execute(stmt).one_or_none()
        return from_dict(Processo, dict(result._mapping)) if result else None

    def count(self, params: CountParams) -> int:
        stmt = self.escopo(select(func.count()).select_from(processos), processos)
        stmt = self._apply_where_clause(stmt, params.get("where"), processos)

        result = self.session.execute(stmt).scalar()
        return result or 0

    def find_by_numero_cnj(self, numero_cnj: str) -> list[Processo]:
        """Processos ativos do tenant com este número CNJ (casamento do DJEN)."""
        stmt = self.escopo(
            select(processos).where(
                processos.c.numero_cnj == numero_cnj, processos.c.status.is_(True)
            ),
            processos,
        )
        return [from_dict(Processo, dict(r._mapping)) for r in self.session.execute(stmt)]

    def pendentes_djen(self, limite: int) -> list[Processo]:
        """Processos marcados para a busca do histórico no DJEN."""
        stmt = self.escopo(
            select(processos)
            .where(
                processos.c.djen_pendente.is_(True),
                processos.c.numero_cnj.is_not(None),
                processos.c.status.is_(True),
            )
            .order_by(processos.c.id)
            .limit(limite),
            processos,
        )
        return [from_dict(Processo, dict(r._mapping)) for r in self.session.execute(stmt)]

    def create(self, data: dict[str, Any]) -> int:
        stmt = insert(processos).values(**self.valores(data))
        try:
            result = self.session.execute(stmt)
            self.session.flush()
        except IntegrityError as error:
            _tratar_numero_duplicado(error)
        return result.lastrowid

    def update(self, id: int, data: dict[str, Any]) -> None:
        stmt = self.escopo(
            sql_update(processos).where(processos.c.id == id), processos
        ).values(**data)
        try:
            self.session.execute(stmt)
        except IntegrityError as error:
            _tratar_numero_duplicado(error)

    def delete(self, id: int) -> bool:
        stmt = self.escopo(
            sql_update(processos).where(processos.c.id == id), processos
        ).values(status=False)
        result = self.session.execute(stmt)
        return result.rowcount > 0

    # --- processos sem caso e lista geral (docs/plano-processos-avulsos.md) ---

    def _casos_do_participante(self, usuario_id: int):
        return self.escopo(
            select(casos.c.id).where(
                or_(
                    casos.c.id_orientador == usuario_id,
                    casos.c.id_estagiario == usuario_id,
                    casos.c.id_colaborador == usuario_id,
                    casos.c.id_usuario_responsavel == usuario_id,
                )
            ),
            casos,
        )

    def participa_do_caso(self, caso_id: int, usuario_id: int) -> bool:
        stmt = self._casos_do_participante(usuario_id).where(casos.c.id == caso_id)
        return self.session.execute(stmt).first() is not None

    def _atendidos_com_nome(self, termo: str):
        """Ids dos atendidos cujo nome, ou uma variação do nome, contém o termo."""
        padrao = f"%{termo}%"
        variacoes = self.escopo(
            select(atendido_nomes.c.id_atendido).where(atendido_nomes.c.nome.ilike(padrao)),
            atendido_nomes,
        )
        return self.escopo(
            select(atendidos.c.id).where(
                or_(atendidos.c.nome.ilike(padrao), atendidos.c.id.in_(variacoes))
            ),
            atendidos,
        )

    def listar(
        self,
        page_params: PageParams,
        unidade_id: int,
        participante_id: int | None = None,
        parte: str | None = None,
        numero: str | None = None,
        distribuicao_de: date | None = None,
        distribuicao_ate: date | None = None,
        status: bool | None = True,
        com_caso: bool | None = None,
    ) -> PaginatedResult[ProcessoListItem]:
        """Processos da unidade, com os filtros da lista.

        `participante_id` restringe aos processos dos casos de que o usuário
        participa e tira os processos sem caso (estagiário, colaborador externo).
        """
        t = processos
        stmt = self.escopo(
            select(
                t.c.id,
                t.c.especie,
                t.c.status,
                t.c.unidade_id,
                t.c.id_caso,
                t.c.numero,
                t.c.numero_cnj,
                t.c.identificacao,
                t.c.vara,
                t.c.data_distribuicao,
                func.count().over().label("total_count"),
            ),
            t,
        ).where(t.c.unidade_id == unidade_id)
        if participante_id is not None:
            stmt = stmt.where(t.c.id_caso.in_(self._casos_do_participante(participante_id)))
        if status is not None:
            stmt = stmt.where(t.c.status.is_(status))
        if com_caso is True:
            stmt = stmt.where(t.c.id_caso.is_not(None))
        elif com_caso is False:
            stmt = stmt.where(t.c.id_caso.is_(None))
        if distribuicao_de:
            stmt = stmt.where(t.c.data_distribuicao >= distribuicao_de)
        if distribuicao_ate:
            stmt = stmt.where(t.c.data_distribuicao <= distribuicao_ate)
        if numero:
            digitos = "".join(c for c in numero if c.isdigit())
            condicoes = [t.c.numero.ilike(f"%{numero}%")]
            if digitos:
                condicoes.append(t.c.numero_cnj.like(f"%{digitos}%"))
            stmt = stmt.where(or_(*condicoes))
        if parte:
            com_nome = self._atendidos_com_nome(parte)
            das_partes = self.escopo(
                select(processo_partes.c.id_processo).where(
                    processo_partes.c.id_atendido.in_(com_nome)
                ),
                processo_partes,
            )
            dos_casos = self.escopo(
                select(casos_atendidos.c.id_caso).where(
                    casos_atendidos.c.id_atendido.in_(self._atendidos_com_nome(parte))
                ),
                casos_atendidos,
            )
            stmt = stmt.where(or_(t.c.id.in_(das_partes), t.c.id_caso.in_(dos_casos)))
        stmt = stmt.order_by(t.c.data_distribuicao.desc(), t.c.id.desc())
        stmt = self._apply_pagination(stmt, page_params)
        rows = self.session.execute(stmt).mappings().all()
        total = rows[0]["total_count"] if rows else 0
        items = [
            from_dict(ProcessoListItem, {k: v for k, v in dict(r).items() if k != "total_count"})
            for r in rows
        ]
        return PaginatedResult(
            items=items, total=total, page=page_params["page"], per_page=page_params["per_page"]
        )

    def nomes_das_partes(self, itens: list[tuple[int, int | None]]) -> dict[int, list[str]]:
        """{id do processo: nomes das partes}, para (id, id_caso) da página.

        Sem caso, as partes vêm de `processo_partes`; com caso, do caso.
        """
        nomes: dict[int, list[str]] = {pid: [] for pid, _ in itens}
        if not itens:
            return nomes
        stmt = self.escopo(
            select(processo_partes.c.id_processo, atendidos.c.nome)
            .join(
                atendidos,
                (atendidos.c.id == processo_partes.c.id_atendido)
                & self.no_tenant(atendidos),
            )
            .where(processo_partes.c.id_processo.in_(list(nomes)))
            .order_by(processo_partes.c.id),
            processo_partes,
        )
        for row in self.session.execute(stmt):
            nomes[row.id_processo].append(row.nome)
        por_caso: dict[int, list[int]] = {}
        for pid, caso_id in itens:
            if caso_id is not None:
                por_caso.setdefault(caso_id, []).append(pid)
        if por_caso:
            stmt = self.escopo(
                select(casos_atendidos.c.id_caso, atendidos.c.nome)
                .join(
                    atendidos,
                    (atendidos.c.id == casos_atendidos.c.id_atendido)
                    & self.no_tenant(atendidos),
                )
                .where(casos_atendidos.c.id_caso.in_(list(por_caso)))
                .order_by(atendidos.c.nome),
                casos_atendidos,
            )
            for row in self.session.execute(stmt):
                for pid in por_caso[row.id_caso]:
                    if row.nome not in nomes[pid]:
                        nomes[pid].append(row.nome)
        return nomes

    def total_publicacoes(self, ids: list[int]) -> dict[int, int]:
        """Publicações do DJEN vinculadas a cada processo."""
        if not ids:
            return {}
        stmt = self.escopo(
            select(djen_comunicacoes.c.id_processo, func.count().label("total"))
            .where(djen_comunicacoes.c.id_processo.in_(ids))
            .group_by(djen_comunicacoes.c.id_processo),
            djen_comunicacoes,
        )
        return {row.id_processo: row.total for row in self.session.execute(stmt)}

    def partes(self, processo: Processo) -> list[ParteProcesso]:
        stmt = self.escopo(
            select(
                processo_partes.c.id,
                processo_partes.c.id_atendido,
                processo_partes.c.polo,
                atendidos.c.nome,
                atendidos.c.sem_triagem,
            )
            .join(
                atendidos,
                (atendidos.c.id == processo_partes.c.id_atendido)
                & self.no_tenant(atendidos),
            )
            .where(processo_partes.c.id_processo == processo.id)
            .order_by(processo_partes.c.id),
            processo_partes,
        )
        resultado = [
            ParteProcesso(
                id=r.id,
                id_atendido=r.id_atendido,
                nome=r.nome,
                polo=r.polo,
                sem_triagem=bool(r.sem_triagem),
                origem="processo",
            )
            for r in self.session.execute(stmt)
        ]
        if processo.id_caso is not None:
            stmt = self.escopo(
                select(atendidos.c.id, atendidos.c.nome, atendidos.c.sem_triagem)
                .join(
                    casos_atendidos,
                    (casos_atendidos.c.id_atendido == atendidos.c.id)
                    & self.no_tenant(casos_atendidos),
                )
                .where(casos_atendidos.c.id_caso == processo.id_caso)
                .order_by(atendidos.c.nome),
                atendidos,
            )
            ja = {p.id_atendido for p in resultado}
            resultado += [
                ParteProcesso(
                    id_atendido=r.id,
                    nome=r.nome,
                    sem_triagem=bool(r.sem_triagem),
                    origem="caso",
                )
                for r in self.session.execute(stmt)
                if r.id not in ja
            ]
        return resultado

    def definir_partes(self, processo_id: int, partes: list[dict[str, Any]]) -> None:
        """Troca as partes do processo pelas informadas."""
        self.session.execute(
            self.escopo(
                sql_delete(processo_partes).where(processo_partes.c.id_processo == processo_id),
                processo_partes,
            )
        )
        for parte in partes:
            self.session.execute(
                insert(processo_partes).values(
                    **self.valores(
                        {
                            "id_processo": processo_id,
                            "id_atendido": parte["id_atendido"],
                            "polo": parte.get("polo"),
                        }
                    )
                )
            )
        self.session.flush()
