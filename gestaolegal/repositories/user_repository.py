import logging
from typing import Any

from sqlalchemy import func, insert, select
from sqlalchemy import update as sql_update
from sqlalchemy.orm import Session

from gestaolegal.common import PaginatedResult
from gestaolegal.database.tables import usuarios
from gestaolegal.models.user import User
from gestaolegal.repositories.repository import (
    BaseRepository,
    CountParams,
    GetParams,
    SearchParams,
)
from gestaolegal.utils.dataclass_utils import from_dict

logger = logging.getLogger(__name__)


class UserRepository(BaseRepository):
    session: Session

    def __init__(self):
        super().__init__()

    def find_by_id(self, id: int) -> User | None:
        stmt = self.escopo(select(usuarios).where(usuarios.c.id == id), usuarios)
        result = self.session.execute(stmt).one_or_none()
        return from_dict(User, dict(result._mapping)) if result else None

    def find_by_email(self, email: str) -> User | None:
        stmt = self.escopo(select(usuarios).where(usuarios.c.email == email), usuarios)
        result = self.session.execute(stmt).one_or_none()
        return from_dict(User, dict(result._mapping)) if result else None

    # --- consultas globais (só dentro de sem_tenant) --------------------------
    # O e-mail é único na plataforma inteira: é ele que diz, no login, a qual
    # NPJ a pessoa pertence (docs/plano-multitenant.md, §5). Estas consultas
    # devolvem só ids, nunca o registro inteiro.

    def tenant_por_email(self, email: str) -> int | None:
        self.exigir_sem_tenant()
        stmt = select(usuarios.c.tenant_id).where(usuarios.c.email == email)
        return self.session.execute(stmt).scalar_one_or_none()

    def tenant_do_usuario(self, id: int) -> int | None:
        self.exigir_sem_tenant()
        stmt = select(usuarios.c.tenant_id).where(usuarios.c.id == id)
        return self.session.execute(stmt).scalar_one_or_none()

    def email_em_uso(self, email: str, ignorar_id: int | None = None) -> bool:
        self.exigir_sem_tenant()
        stmt = select(usuarios.c.id).where(usuarios.c.email == email)
        if ignorar_id is not None:
            stmt = stmt.where(usuarios.c.id != ignorar_id)
        return self.session.execute(stmt.limit(1)).first() is not None

    def existe_algum_usuario(self) -> bool:
        self.exigir_sem_tenant()
        return self.session.execute(select(usuarios.c.id).limit(1)).first() is not None

    def opcoes_ativos(self) -> list[dict[str, Any]]:
        """Usuários ativos (id, nome, urole) em ordem alfabética, para seletores."""
        stmt = (
            self.escopo(
                select(usuarios.c.id, usuarios.c.nome, usuarios.c.urole), usuarios
            )
            .where(usuarios.c.status.is_(True))
            .order_by(usuarios.c.nome.asc())
        )
        return [dict(row) for row in self.session.execute(stmt).mappings().all()]

    def get(self, params: GetParams) -> list[User]:
        stmt = self.escopo(select(usuarios), usuarios)
        stmt = self._apply_where_clause(stmt, params.get("where"), usuarios)
        result = self.session.execute(stmt).all()
        return [from_dict(User, dict(row._mapping)) for row in result]

    def get_by_ids(self, ids: list[int]) -> list[User]:
        if not ids:
            return []
        stmt = self.escopo(select(usuarios).where(usuarios.c.id.in_(ids)), usuarios)
        results = self.session.execute(stmt).all()
        return [from_dict(User, dict(row._mapping)) for row in results]

    def search(self, params: SearchParams) -> PaginatedResult[User]:
        stmt = self.escopo(
            select(usuarios, func.count().over().label("total_count")), usuarios
        )

        stmt = self._apply_where_clause(stmt, params.get("where"), usuarios)
        stmt = stmt.order_by(usuarios.c.nome)
        stmt = self._apply_pagination(stmt, params.get("page_params"))

        results = self.session.execute(stmt).all()
        total = results[0].total_count if results else 0

        items = [from_dict(User, dict(row._mapping)) for row in results]
        page_params = params.get("page_params")

        return PaginatedResult(
            items=items,
            total=total,
            page=page_params["page"] if page_params else 1,
            per_page=page_params["per_page"] if page_params else total,
        )

    def find_one(self, params: SearchParams) -> User | None:
        stmt = self.escopo(select(usuarios), usuarios)
        stmt = self._apply_where_clause(stmt, params.get("where"), usuarios)
        result = self.session.execute(stmt).one_or_none()
        return from_dict(User, dict(result._mapping)) if result else None

    def count(self, params: CountParams) -> int:
        stmt = self.escopo(select(func.count()).select_from(usuarios), usuarios)
        stmt = self._apply_where_clause(stmt, params.get("where"), usuarios)

        result = self.session.execute(stmt).scalar()
        return result or 0

    def create(self, data: dict[str, Any]) -> int:
        stmt = insert(usuarios).values(**self.valores(data))
        result = self.session.execute(stmt)
        self.session.flush()
        return result.lastrowid

    def update(self, id: int, data: dict[str, Any]) -> None:
        stmt = self.escopo(
            sql_update(usuarios).where(usuarios.c.id == id), usuarios
        ).values(**data)
        self.session.execute(stmt)

    def delete(self, id: int) -> bool:
        stmt = self.escopo(
            sql_update(usuarios).where(usuarios.c.id == id), usuarios
        ).values(status=False)
        result = self.session.execute(stmt)
        return result.rowcount > 0
