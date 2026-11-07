from sqlalchemy import select

from gestaolegal.database.tables import tenants
from gestaolegal.repositories.repository import BaseRepository


class TenantRepository(BaseRepository):
    """Leitura da tabela global `tenants` (não tem tenant_id)."""

    def ativo(self, tenant_id: int) -> bool:
        stmt = select(tenants.c.ativo).where(tenants.c.id == tenant_id)
        return bool(self.session.execute(stmt).scalar_one_or_none())
