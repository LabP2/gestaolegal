from datetime import datetime
from typing import Any

from sqlalchemy import func, insert, or_, select
from sqlalchemy import update as sql_update

from gestaolegal.database.tables import plataforma_admins, tenants
from gestaolegal.models.plataforma import PlataformaAdmin, Tenant
from gestaolegal.repositories.repository import BaseRepository


class TenantRepository(BaseRepository):
    """Tabela global `tenants` (não tem tenant_id).

    `ativo` e `identificacao` servem ao login e ao cabeçalho do NPJ. O resto é
    o CRUD da plataforma e só roda dentro de `sem_tenant(motivo)`.
    """

    def ativo(self, tenant_id: int) -> bool:
        stmt = select(tenants.c.ativo).where(tenants.c.id == tenant_id)
        return bool(self.session.execute(stmt).scalar_one_or_none())

    def identificacao(self, tenant_id: int) -> dict[str, str] | None:
        """Nome e sigla do NPJ, para o cabeçalho do front."""
        stmt = select(tenants.c.nome, tenants.c.sigla).where(tenants.c.id == tenant_id)
        row = self.session.execute(stmt).mappings().one_or_none()
        return dict(row) if row else None

    # --- plataforma -------------------------------------------------------

    def listar(self, ativo: bool | None = None, q: str = "") -> list[Tenant]:
        self.exigir_sem_tenant()
        stmt = select(tenants).order_by(tenants.c.nome)
        if ativo is not None:
            stmt = stmt.where(tenants.c.ativo.is_(ativo))
        if q:
            termo = f"%{q.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(tenants.c.nome).like(termo),
                    func.lower(tenants.c.sigla).like(termo),
                    func.lower(tenants.c.slug).like(termo),
                )
            )
        return [Tenant(**row) for row in self.session.execute(stmt).mappings()]

    def find(self, tenant_id: int) -> Tenant | None:
        self.exigir_sem_tenant()
        row = (
            self.session.execute(select(tenants).where(tenants.c.id == tenant_id))
            .mappings()
            .one_or_none()
        )
        return Tenant(**row) if row else None

    def em_uso(self, coluna: str, valor: str, ignorar_id: int | None = None) -> bool:
        """Se `slug` ou `sigla` já pertence a outro NPJ (comparação sem caixa)."""
        self.exigir_sem_tenant()
        col = tenants.c[coluna]
        stmt = select(tenants.c.id).where(func.lower(col) == valor.lower())
        if ignorar_id is not None:
            stmt = stmt.where(tenants.c.id != ignorar_id)
        return self.session.execute(stmt.limit(1)).first() is not None

    def criar(self, data: dict[str, Any]) -> int:
        self.exigir_sem_tenant()
        result = self.session.execute(insert(tenants).values(**data))
        self.session.flush()
        return result.lastrowid

    def atualizar(self, tenant_id: int, data: dict[str, Any]) -> None:
        self.exigir_sem_tenant()
        self.session.execute(
            sql_update(tenants).where(tenants.c.id == tenant_id).values(**data)
        )
        self.session.flush()


class PlataformaAdminRepository(BaseRepository):
    """Tabela global `plataforma_admins`. Só roda dentro de `sem_tenant`."""

    def find_by_email(self, email: str) -> PlataformaAdmin | None:
        self.exigir_sem_tenant()
        row = (
            self.session.execute(
                select(plataforma_admins).where(
                    func.lower(plataforma_admins.c.email) == email.strip().lower()
                )
            )
            .mappings()
            .one_or_none()
        )
        return PlataformaAdmin(**row) if row else None

    def find_by_id(self, admin_id: int) -> PlataformaAdmin | None:
        self.exigir_sem_tenant()
        row = (
            self.session.execute(
                select(plataforma_admins).where(plataforma_admins.c.id == admin_id)
            )
            .mappings()
            .one_or_none()
        )
        return PlataformaAdmin(**row) if row else None

    def criar(self, nome: str, email: str, senha_hash: str) -> int:
        self.exigir_sem_tenant()
        result = self.session.execute(
            insert(plataforma_admins).values(
                nome=nome,
                email=email,
                senha=senha_hash,
                ativo=True,
                criado_em=datetime.now(),
            )
        )
        self.session.flush()
        return result.lastrowid

    def registrar_login(self, admin_id: int) -> None:
        self.exigir_sem_tenant()
        self.session.execute(
            sql_update(plataforma_admins)
            .where(plataforma_admins.c.id == admin_id)
            .values(ultimo_login_em=datetime.now())
        )
