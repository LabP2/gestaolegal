import json
import logging
import re
import unicodedata
from typing import Any

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, insert, or_, select
from sqlalchemy import update as sql_update

from gestaolegal.common import PaginatedResult
from gestaolegal.database.tables import (
    assistidos,
    assistidos_pessoa_juridica,
    atendido_nomes,
    atendido_xOrientacaoJuridica,
    atendidos,
)
from gestaolegal.models.assistido import Assistido
from gestaolegal.models.assistido_pessoa_juridica import AssistidoPessoaJuridica
from gestaolegal.models.atendido import Atendido
from gestaolegal.repositories.repository import (
    BaseRepository,
    CountParams,
    GetParams,
    SearchParams,
)
from gestaolegal.utils.dataclass_utils import from_dict

logger = logging.getLogger(__name__)


class AtendidoRepository(BaseRepository):
    def __init__(self):
        super().__init__()

    def sugerir_por_nomes(
        self, nomes: list[str], unidade_id: int
    ) -> dict[str, list[dict]]:
        """Nomes e variações exatos; homônimos permanecem candidatos distintos."""

        def normalizar(nome):
            return " ".join(
                "".join(
                    c
                    for c in unicodedata.normalize("NFKD", nome or "")
                    if not unicodedata.combining(c)
                )
                .casefold()
                .split()
            )

        procurados = {normalizar(n) for n in nomes if normalizar(n)}
        encontrados = {n: {} for n in procurados}
        if not procurados:
            return {n: [] for n in nomes}
        stmt = self.escopo(
            select(
                atendidos.c.id,
                atendidos.c.nome,
                atendido_nomes.c.nome.label("variacao"),
            )
            .outerjoin(
                atendido_nomes,
                (
                    (atendido_nomes.c.id_atendido == atendidos.c.id)
                    & self.no_tenant(atendido_nomes)
                ),
            )
            .where(atendidos.c.unidade_id == unidade_id, atendidos.c.status == 1),
            atendidos,
        )
        for row in self.session.execute(stmt).mappings():
            for nome in (row["nome"], row["variacao"]):
                chave = normalizar(nome)
                if chave in encontrados:
                    encontrados[chave][row["id"]] = {
                        "id": row["id"],
                        "nome": row["nome"],
                    }
        return {
            n: sorted(
                encontrados.get(normalizar(n), {}).values(),
                key=lambda a: (a["nome"], a["id"]),
            )
            for n in nomes
        }

    def find_by_id(self, id: int, unidade_id: int | None = None) -> Atendido | None:
        stmt = self.escopo(select(atendidos).where(atendidos.c.id == id), atendidos)
        if unidade_id is not None:
            stmt = stmt.where(atendidos.c.unidade_id == unidade_id)
        result = self.session.execute(stmt).one_or_none()
        return from_dict(Atendido, dict(result._mapping)) if result else None

    def find_by_email(self, email: str) -> Atendido | None:
        stmt = self.escopo(
            select(atendidos).where(atendidos.c.email == email), atendidos
        )
        result = self.session.execute(stmt).one_or_none()
        return from_dict(Atendido, dict(result._mapping)) if result else None

    def get(self, params: GetParams) -> list[Atendido]:
        stmt = self.escopo(select(atendidos), atendidos)
        stmt = self._apply_where_clause(stmt, params.get("where"), atendidos)
        result = self.session.execute(stmt).all()
        return [from_dict(Atendido, dict(row._mapping)) for row in result]

    def get_by_ids(self, ids: list[int]) -> list[Atendido]:
        if not ids:
            return []
        stmt = self.escopo(select(atendidos).where(atendidos.c.id.in_(ids)), atendidos)
        results = self.session.execute(stmt).all()
        return [from_dict(Atendido, dict(row._mapping)) for row in results]

    # TODO: Avaliar se existe uma forma melhor de modelar este método (e o comportamento como um todo).
    #
    # Explicação:
    # Como as dependências (entidades relacionadas) neste caso são obtidas por meio de uma tabela auxiliar,
    # não é possível implementar a lógica de carregamento das dependências no service, como normalmente fazemos.
    # Por isso, este método retorna não apenas as entidades, mas também um mapa para relacionar cada orientação jurídica com seus atendidos.
    #
    # Observação:
    # Recebemos uma lista de IDs de orientação jurídica, em vez de um único ID, para evitar o problema de "N+1 queries".
    def get_related_with_orientacao_juridica(
        self, orientacao_juridica_ids: list[int]
    ) -> tuple[list[Atendido], dict[int, list[int]]]:
        stmt = select(
            atendidos, atendido_xOrientacaoJuridica.c.id_orientacaoJuridica
        ).join(
            atendido_xOrientacaoJuridica,
            atendido_xOrientacaoJuridica.c.id_atendido == atendidos.c.id,
        )
        stmt = stmt.where(
            atendido_xOrientacaoJuridica.c.id_orientacaoJuridica.in_(
                orientacao_juridica_ids
            )
        )
        stmt = self.escopo(stmt, atendidos, atendido_xOrientacaoJuridica)

        result = self.session.execute(stmt).mappings().all()

        orientacao_juridica_map: dict[int, list[int]] = {}
        atendidos_list = []

        for row in result:
            orientacao_id = row["id_orientacaoJuridica"]
            atendido_id = row["id"]

            if orientacao_id not in orientacao_juridica_map:
                orientacao_juridica_map[orientacao_id] = []
            orientacao_juridica_map[orientacao_id].append(atendido_id)

            atendidos_list.append(from_dict(Atendido, dict(row)))

        return atendidos_list, orientacao_juridica_map

    def search(
        self, params: SearchParams, tipo_busca: str = "todos", search: str = ""
    ) -> PaginatedResult[dict]:
        # EXISTS mantém uma pessoa por resultado mesmo quando o legado tem
        # mais de uma ficha de assistido para o mesmo atendido.
        tem_ficha = (
            select(assistidos.c.id)
            .where(
                assistidos.c.id_atendido == atendidos.c.id,
                self.no_tenant(assistidos),
            )
            .exists()
        )
        # Parte cadastrada sem triagem conta como assistido sem ter ficha.
        has_assistido = or_(tem_ficha, atendidos.c.sem_triagem.is_(True))
        stmt = select(
            atendidos.c.id,
            atendidos.c.nome,
            atendidos.c.cpf,
            atendidos.c.telefone,
            atendidos.c.celular,
            atendidos.c.email,
            atendidos.c.status,
            atendidos.c.data_nascimento,
            atendidos.c.endereco_id,
            atendidos.c.sem_triagem,
            func.count().over().label("total_count"),
            has_assistido.label("is_assistido"),
        )

        stmt = self.escopo(stmt, atendidos)
        stmt = self._apply_where_clause(stmt, params.get("where"), atendidos)

        term = search.strip()
        if term:
            conditions = [atendidos.c.nome.ilike(f"%{term}%")]
            digits = re.sub(r"[^0-9]", "", term)
            if digits and re.fullmatch(r"[0-9.\-\s]+", term):
                cpf = func.replace(
                    func.replace(func.replace(atendidos.c.cpf, ".", ""), "-", ""),
                    " ",
                    "",
                )
                conditions.append(cpf.like(f"%{digits}%"))
            stmt = stmt.where(or_(*conditions))

        if tipo_busca == "atendidos":
            stmt = stmt.where(~has_assistido)
        elif tipo_busca == "assistidos":
            stmt = stmt.where(has_assistido)

        stmt = stmt.order_by(atendidos.c.nome, atendidos.c.id)
        stmt = self._apply_pagination(stmt, params.get("page_params"))

        results = self.session.execute(stmt).mappings().all()
        total = results[0].total_count if results else 0

        items = [dict(row) for row in results]

        page_params = params.get("page_params")
        return PaginatedResult(
            items=items,
            total=total,
            page=page_params["page"] if page_params else 1,
            per_page=page_params["per_page"] if page_params else total,
        )

    def find_one(self, params: SearchParams) -> Atendido | None:
        stmt = self.escopo(select(atendidos), atendidos)
        stmt = self._apply_where_clause(stmt, params.get("where"), atendidos)
        result = self.session.execute(stmt).one_or_none()
        return from_dict(Atendido, dict(result._mapping)) if result else None

    def count(self, params: CountParams) -> int:
        stmt = self.escopo(select(func.count()).select_from(atendidos), atendidos)
        stmt = self._apply_where_clause(stmt, params.get("where"), atendidos)

        result = self.session.execute(stmt).scalar()
        return result or 0

    def create(self, data: dict[str, Any]) -> int:
        stmt = insert(atendidos).values(**self.valores(data))
        result = self.session.execute(stmt)
        self.session.flush()
        return result.lastrowid

    def update(self, id: int, data: dict[str, Any]) -> None:
        check_stmt = self.escopo(
            select(atendidos).where(atendidos.c.id == id), atendidos
        )
        existing = self.session.execute(check_stmt).first()

        if not existing:
            raise ValueError(f"Atendido with id {id} not found")

        stmt = self.escopo(
            sql_update(atendidos).where(atendidos.c.id == id), atendidos
        ).values(**data)
        self.session.execute(stmt)

    def delete(self, id: int) -> bool:
        stmt = self.escopo(
            sql_update(atendidos).where(atendidos.c.id == id), atendidos
        ).values(status=0)
        result = self.session.execute(stmt)
        return result.rowcount > 0

    def find_assistido_by_atendido_id(self, atendido_id: int) -> Assistido | None:
        stmt = self.escopo(
            select(assistidos).where(assistidos.c.id_atendido == atendido_id),
            assistidos,
        )
        result = self.session.execute(stmt).one_or_none()
        if not result:
            return None
        assistido = from_dict(Assistido, dict(result._mapping))
        pj = (
            self.session.execute(
                self.escopo(
                    select(assistidos_pessoa_juridica).where(
                        assistidos_pessoa_juridica.c.id_assistido == assistido.id
                    ),
                    assistidos_pessoa_juridica,
                )
                .order_by(assistidos_pessoa_juridica.c.id.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if pj:
            dados = dict(pj)
            texto = dados.pop("socios") or ""
            try:
                nomes = json.loads(texto)
            except (ValueError, TypeError):
                nomes = None
            # Texto livre legado é preservado como um único campo, sem adivinhar separadores.
            dados["socios"] = (
                nomes
                if isinstance(nomes, list) and all(isinstance(n, str) for n in nomes)
                else ([texto] if texto else [])
            )
            if dados["enquadramento"] == "mei":
                dados["socios"] = []
            assistido.assistido_pessoa_juridica = from_dict(
                AssistidoPessoaJuridica, dados
            )
        return assistido

    def get_assistidos_by_atendido_ids(
        self, atendido_ids: list[int]
    ) -> list[Assistido]:
        if not atendido_ids:
            return []
        stmt = self.escopo(
            select(assistidos).where(assistidos.c.id_atendido.in_(atendido_ids)),
            assistidos,
        )
        results = self.session.execute(stmt).all()
        return [from_dict(Assistido, dict(row._mapping)) for row in results]

    def create_assistido(self, data: dict[str, Any]) -> int:
        stmt = insert(assistidos).values(**self.valores(data))
        result = self.session.execute(stmt)
        self.session.flush()
        return result.lastrowid

    def update_assistido(self, id_atendido: int, data: dict[str, Any]) -> None:
        check_stmt = self.escopo(
            select(assistidos).where(assistidos.c.id_atendido == id_atendido),
            assistidos,
        )
        existing = self.session.execute(check_stmt).first()

        if not existing:
            raise ValueError(f"Assistido for atendido {id_atendido} not found")

        stmt = self.escopo(
            sql_update(assistidos).where(assistidos.c.id_atendido == id_atendido),
            assistidos,
        ).values(**data)
        self.session.execute(stmt)

    def salvar_pessoa_juridica(self, id_assistido: int, dados: dict[str, Any]) -> None:
        dados = dict(dados)
        dados["socios"] = json.dumps(dados["socios"], ensure_ascii=False)
        # Atualiza apenas os campos deste formulário, preservando o restante do legado.
        existente = self.session.execute(
            self.escopo(
                select(assistidos_pessoa_juridica.c.id).where(
                    assistidos_pessoa_juridica.c.id_assistido == id_assistido
                ),
                assistidos_pessoa_juridica,
            )
        ).first()
        if existente:
            self.session.execute(
                self.escopo(
                    sql_update(assistidos_pessoa_juridica).where(
                        assistidos_pessoa_juridica.c.id_assistido == id_assistido
                    ),
                    assistidos_pessoa_juridica,
                ).values(**dados)
            )
        else:
            self.session.execute(
                insert(assistidos_pessoa_juridica).values(
                    **self.valores({"id_assistido": id_assistido, **dados})
                )
            )
        self.session.flush()

    # --- variações do nome (busca no DJEN) -------------------------------------

    def nomes(self, id_atendido: int) -> list[dict[str, Any]]:
        stmt = self.escopo(
            select(atendido_nomes.c.id, atendido_nomes.c.nome)
            .where(atendido_nomes.c.id_atendido == id_atendido)
            .order_by(atendido_nomes.c.nome),
            atendido_nomes,
        )
        return [dict(r) for r in self.session.execute(stmt).mappings()]

    def nome_existe(self, id_atendido: int, nome: str) -> bool:
        stmt = self.escopo(
            select(atendido_nomes.c.id).where(
                atendido_nomes.c.id_atendido == id_atendido,
                func.lower(atendido_nomes.c.nome) == nome.lower(),
            ),
            atendido_nomes,
        )
        return self.session.execute(stmt).first() is not None

    def adicionar_nome(self, id_atendido: int, nome: str) -> int:
        result = self.session.execute(
            insert(atendido_nomes).values(
                **self.valores({"id_atendido": id_atendido, "nome": nome})
            )
        )
        self.session.flush()
        return result.lastrowid

    def remover_nome(self, id_atendido: int, nome_id: int) -> bool:
        result = self.session.execute(
            self.escopo(
                sql_delete(atendido_nomes).where(
                    atendido_nomes.c.id == nome_id,
                    atendido_nomes.c.id_atendido == id_atendido,
                ),
                atendido_nomes,
            )
        )
        return (result.rowcount or 0) > 0
