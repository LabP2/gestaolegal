"""Acesso a `djen_comunicacoes`, `djen_sincronizacoes`, `djen_oabs` e
`djen_publicacoes`, sempre no tenant ativo."""

from contextlib import contextmanager
from datetime import date
from typing import Any

from sqlalchemy import func, insert, or_, select
from sqlalchemy import delete as sql_delete
from sqlalchemy import update as sql_update

from gestaolegal.common import PageParams, PaginatedResult
from gestaolegal.repositories.djen_filtros import filtrar_identificacao
from gestaolegal.database.tables import (
    casos,
    djen_comunicacoes,
    djen_publicacoes,
    djen_oabs,
    djen_sincronizacoes,
    unidades,
    usuarios,
    usuarios_unidades,
)
from gestaolegal.models.djen import (
    ComunicacaoDJEN,
    ComunicacaoListItem,
    OabMonitorada,
    SincronizacaoDJEN,
)
from gestaolegal.repositories.repository import BaseRepository
from gestaolegal.utils.dataclass_utils import from_dict

# Read model joining the canonical content with operational state.
_comunicacoes = djen_comunicacoes


def _dados(tenant_id=None):
    stmt = select(
        *_comunicacoes.c,
        *[col for col in djen_publicacoes.c if col.name not in ("id", "tenant_id")],
    ).select_from(
        _comunicacoes.join(
            djen_publicacoes,
            (_comunicacoes.c.id_publicacao == djen_publicacoes.c.id)
            & (_comunicacoes.c.tenant_id == djen_publicacoes.c.tenant_id),
        )
    )
    if tenant_id is not None:
        stmt = stmt.where(
            _comunicacoes.c.tenant_id == tenant_id,
            djen_publicacoes.c.tenant_id == tenant_id,
        )
    return stmt.subquery("djen_dados")


LIMITE_RESUMO = 240


class DjenComunicacaoRepository(BaseRepository):
    @property
    def dados(self):
        if not hasattr(self, "_dados_cache"):
            self._dados_cache = _dados(self.tenant_id())
        return self._dados_cache

    def find_by_id(self, id: int) -> ComunicacaoDJEN | None:
        stmt = self.escopo(
            select(self.dados).where(self.dados.c.id == id),
            self.dados,
        )
        row = self.session.execute(stmt).mappings().one_or_none()
        return from_dict(ComunicacaoDJEN, dict(row)) if row else None

    def vinculadas_ao_processo(self, processo_id: int) -> list[int]:
        stmt = self.escopo(
            select(_comunicacoes.c.id).where(
                _comunicacoes.c.id_processo == processo_id,
                _comunicacoes.c.situacao == "vinculada",
            ).with_for_update(), _comunicacoes,
        )
        return list(self.session.execute(stmt).scalars())

    def find_by_id_djen(self, id_djen: int) -> ComunicacaoDJEN | None:
        stmt = self.escopo(
            select(self.dados).where(self.dados.c.id_djen == id_djen),
            self.dados,
        )
        row = self.session.execute(stmt).mappings().one_or_none()
        return from_dict(ComunicacaoDJEN, dict(row)) if row else None

    def criar(self, data: dict[str, Any]) -> int:
        result = self.session.execute(
            insert(_comunicacoes).values(**self.valores(data))
        )
        self.session.flush()
        return result.lastrowid

    def atualizar(self, id: int, data: dict[str, Any]) -> None:
        publicacao = {k: v for k, v in data.items() if k in djen_publicacoes.c}
        operacional = {k: v for k, v in data.items() if k in _comunicacoes.c}
        if publicacao:
            pid = self.session.execute(
                self.escopo(
                    select(_comunicacoes.c.id_publicacao).where(
                        _comunicacoes.c.id == id
                    ),
                    _comunicacoes,
                )
            ).scalar_one()
            self.session.execute(
                self.escopo(
                    sql_update(djen_publicacoes).where(djen_publicacoes.c.id == pid),
                    djen_publicacoes,
                ).values(**publicacao)
            )
        if operacional:
            self.session.execute(
                self.escopo(
                    sql_update(_comunicacoes).where(_comunicacoes.c.id == id),
                    _comunicacoes,
                ).values(**operacional)
            )

    def ativos_por_ids(self, ids: set[int]) -> dict[int, bool]:
        """`ativo` de cada publicação (selo de cancelada nos eventos)."""
        if not ids:
            return {}
        stmt = self.escopo(
            select(self.dados.c.id, self.dados.c.ativo).where(self.dados.c.id.in_(ids)),
            self.dados,
        )
        return {row.id: bool(row.ativo) for row in self.session.execute(stmt)}

    def listar(
        self,
        page_params: PageParams,
        unidade_id: int,
        situacoes: tuple[str, ...],
        participante_id: int | None = None,
        inicio: date | None = None,
        fim: date | None = None,
        tribunal: str | None = None,
        tipo: str | None = None,
        oab: str | None = None,
        situacao: str | None = None,
        caso_id: int | None = None,
        q: str | None = None,
        processo_id: int | None = None,
        nome_parte: str | None = None,
        numero_processo: str | None = None,
    ) -> PaginatedResult[ComunicacaoListItem]:
        """Publicações da unidade.

        `situacoes` limita o que o papel pode ver; `participante_id` restringe
        aos casos de que o usuário participa (estagiário, colaborador externo).
        """
        t = self.dados
        stmt = select(
            *[
                t.c[n]
                for n in (
                    "id",
                    "data_disponibilizacao",
                    "numero_processo",
                    "numero_processo_mascara",
                    "situacao",
                    "ativo",
                    "sigla_tribunal",
                    "nome_orgao",
                    "tipo_comunicacao",
                    "tipo_documento",
                    "nome_classe",
                    "id_processo",
                    "id_caso",
                    "oab_origem",
                )
            ],
            func.substr(t.c.texto_plano, 1, LIMITE_RESUMO).label("resumo"),
            func.count().over().label("total_count"),
        )
        stmt = self.escopo(stmt, t).where(
            t.c.unidade_id == unidade_id, t.c.situacao.in_(situacoes)
        )
        if participante_id is not None:
            meus_casos = self.escopo(
                select(casos.c.id).where(
                    or_(
                        casos.c.id_orientador == participante_id,
                        casos.c.id_estagiario == participante_id,
                        casos.c.id_colaborador == participante_id,
                        casos.c.id_usuario_responsavel == participante_id,
                    )
                ),
                casos,
            )
            stmt = stmt.where(t.c.id_caso.in_(meus_casos))
        if inicio:
            stmt = stmt.where(t.c.data_disponibilizacao >= inicio)
        if fim:
            stmt = stmt.where(t.c.data_disponibilizacao <= fim)
        if tribunal:
            stmt = stmt.where(t.c.sigla_tribunal == tribunal)
        if tipo:
            stmt = stmt.where(t.c.tipo_comunicacao == tipo)
        stmt = filtrar_identificacao(stmt, t, self.session.get_bind().dialect.name,
            nome_parte, numero_processo, oab)
        if situacao:
            stmt = stmt.where(t.c.situacao == situacao)
        if caso_id is not None:
            stmt = stmt.where(t.c.id_caso == caso_id)
        if processo_id is not None:
            stmt = stmt.where(t.c.id_processo == processo_id)
        if q:
            termo = f"%{q.lower()}%"
            digitos = "".join(ch for ch in q if ch.isdigit())
            condicoes = [
                func.lower(t.c.texto_plano).like(termo),
                func.lower(t.c.nome_orgao).like(termo),
                func.lower(t.c.nome_classe).like(termo),
            ]
            if digitos:
                condicoes.append(t.c.numero_processo.like(f"%{digitos}%"))
            stmt = stmt.where(or_(*condicoes))
        stmt = stmt.order_by(t.c.data_disponibilizacao.desc(), t.c.id.desc())
        stmt = self._apply_pagination(stmt, page_params)
        rows = self.session.execute(stmt).mappings().all()
        total = rows[0]["total_count"] if rows else 0
        items = [
            from_dict(
                ComunicacaoListItem,
                {k: v for k, v in dict(r).items() if k != "total_count"},
            )
            for r in rows
        ]
        return PaginatedResult(
            items=items,
            total=total,
            page=page_params["page"],
            per_page=page_params["per_page"],
        )

    def valores_distintos(self, coluna: str, unidade_id: int) -> list[str]:
        """Tribunais ou tipos já capturados na unidade, para os filtros."""
        col = self.dados.c[coluna]
        stmt = self.escopo(
            select(col)
            .where(self.dados.c.unidade_id == unidade_id, col.is_not(None))
            .distinct()
            .order_by(col),
            self.dados,
        )
        return [v for v in self.session.execute(stmt).scalars() if v]

    def por_ids_djen(self, ids_djen: list[int]) -> dict[int, ComunicacaoDJEN]:
        """Publicações já gravadas no NPJ, pelo `id` da API (busca por parte)."""
        if not ids_djen:
            return {}
        stmt = self.escopo(
            select(self.dados).where(self.dados.c.id_djen.in_(ids_djen)),
            self.dados,
        )
        return {
            row["id_djen"]: from_dict(ComunicacaoDJEN, dict(row))
            for row in self.session.execute(stmt).mappings()
        }


class DjenSincronizacaoRepository(BaseRepository):
    def registrar(self, data: dict[str, Any]) -> int:
        result = self.session.execute(
            insert(djen_sincronizacoes).values(**self.valores(data))
        )
        self.session.flush()
        return result.lastrowid

    def ultima(self) -> SincronizacaoDJEN | None:
        stmt = self.escopo(
            select(djen_sincronizacoes)
            .order_by(
                djen_sincronizacoes.c.inicio.desc(), djen_sincronizacoes.c.id.desc()
            )
            .limit(1),
            djen_sincronizacoes,
        )
        row = self.session.execute(stmt).mappings().one_or_none()
        return from_dict(SincronizacaoDJEN, dict(row)) if row else None

    @contextmanager
    def trava_da_rotina(self):
        """Lock nomeado do MySQL por NPJ, numa conexão própria; rende False
        se outra execução já o detém.

        A conexão da sessão volta ao pool a cada commit da rotina e perderia o
        lock no caminho. No SQLite (testes) não há o que travar.
        """
        engine = self.session.get_bind()
        if engine.dialect.name != "mysql":
            yield True
            return
        nome = f"gestaolegal_djen_{self.tenant_id()}"
        with engine.connect() as conn:
            if conn.execute(select(func.get_lock(nome, 0))).scalar() != 1:
                yield False
                return
            try:
                yield True
            finally:
                conn.execute(select(func.release_lock(nome)))


class DjenOabRepository(BaseRepository):
    """OABs monitoradas. Os JOINs com usuário e unidade só dão o nome."""

    def _select(self):
        return self.escopo(
            select(
                djen_oabs,
                usuarios.c.nome.label("usuario_nome"),
                unidades.c.nome.label("unidade_nome"),
            ).select_from(
                djen_oabs.outerjoin(
                    usuarios,
                    (usuarios.c.id == djen_oabs.c.id_usuario)
                    & self.no_tenant(usuarios),
                ).outerjoin(
                    unidades,
                    (unidades.c.id == djen_oabs.c.unidade_id)
                    & self.no_tenant(unidades),
                )
            ),
            djen_oabs,
        )

    @staticmethod
    def _converter(row) -> OabMonitorada:
        return from_dict(OabMonitorada, dict(row))

    def listar(
        self, unidade_id: int | None = None, so_ativas: bool = False
    ) -> list[OabMonitorada]:
        stmt = self._select()
        if unidade_id is not None:
            stmt = stmt.where(djen_oabs.c.unidade_id == unidade_id)
        if so_ativas:
            stmt = stmt.where(djen_oabs.c.ativo.is_(True))
        stmt = stmt.order_by(djen_oabs.c.uf_oab, djen_oabs.c.numero_oab)
        return [self._converter(r) for r in self.session.execute(stmt).mappings()]

    def find_by_id(self, id: int) -> OabMonitorada | None:
        row = (
            self.session.execute(self._select().where(djen_oabs.c.id == id))
            .mappings()
            .one_or_none()
        )
        return self._converter(row) if row else None

    def existe(
        self, numero_oab: str, uf_oab: str, ignorar_id: int | None = None
    ) -> bool:
        stmt = self.escopo(
            select(djen_oabs.c.id).where(
                djen_oabs.c.numero_oab == numero_oab, djen_oabs.c.uf_oab == uf_oab
            ),
            djen_oabs,
        )
        if ignorar_id is not None:
            stmt = stmt.where(djen_oabs.c.id != ignorar_id)
        return self.session.execute(stmt).first() is not None

    def criar(self, data: dict[str, Any]) -> int:
        result = self.session.execute(insert(djen_oabs).values(**self.valores(data)))
        self.session.flush()
        return result.lastrowid

    def atualizar(self, id: int, data: dict[str, Any]) -> None:
        self.session.execute(
            self.escopo(
                sql_update(djen_oabs).where(djen_oabs.c.id == id), djen_oabs
            ).values(**data)
        )

    def apagar(self, id: int) -> None:
        self.session.execute(
            self.escopo(sql_delete(djen_oabs).where(djen_oabs.c.id == id), djen_oabs)
        )

    def usuarios_com_oab(
        self, unidade_id: int, papeis: tuple[str, ...]
    ) -> list[dict[str, Any]]:
        """Usuários ativos da unidade com `oab` preenchido: só sugestão."""
        stmt = self.escopo(
            select(usuarios.c.id, usuarios.c.nome, usuarios.c.oab, usuarios.c.urole)
            .join(usuarios_unidades, usuarios_unidades.c.usuario_id == usuarios.c.id)
            .where(
                usuarios_unidades.c.unidade_id == unidade_id,
                usuarios.c.status.is_(True),
                usuarios.c.urole.in_(papeis),
                usuarios.c.oab.is_not(None),
                usuarios.c.oab != "",
            )
            .order_by(usuarios.c.nome),
            usuarios,
            usuarios_unidades,
        )
        return [dict(r) for r in self.session.execute(stmt).mappings()]
