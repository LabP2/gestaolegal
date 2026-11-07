import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from gestaolegal.models.user import UserInfo

logger = logging.getLogger(__name__)

_current_user: ContextVar[UserInfo | None] = ContextVar("current_user", default=None)
_unidade_ativa: ContextVar[int | None] = ContextVar("unidade_ativa", default=None)
_tenant_ativo: ContextVar[int | None] = ContextVar("tenant_ativo", default=None)
# Motivo declarado de um trecho que roda de propósito sem tenant (CRUD da
# plataforma, busca do e-mail no login, reset de demo). None = fora desse trecho.
_sem_tenant: ContextVar[str | None] = ContextVar("sem_tenant", default=None)
# Administrador da plataforma autenticado (id). Nunca convive com tenant ativo.
_plataforma_admin: ContextVar[int | None] = ContextVar("plataforma_admin", default=None)


def _validar_tenant_id(tenant_id: int) -> int:
    # bool é subclasse de int: True passaria como tenant 1.
    if isinstance(tenant_id, bool) or not isinstance(tenant_id, int) or tenant_id < 1:
        raise ValueError(f"tenant_id inválido: {tenant_id!r}")
    return tenant_id


class RequestContext:
    @staticmethod
    def set_current_user(user: UserInfo) -> None:
        _current_user.set(user)

    @staticmethod
    def get_current_user() -> UserInfo:
        user = _current_user.get()
        if user is None:
            raise RuntimeError("No authenticated user in current request context")
        return user

    @staticmethod
    def set_unidade_ativa(unidade_id: int) -> None:
        _unidade_ativa.set(unidade_id)

    @staticmethod
    def get_unidade_ativa() -> int:
        unidade_id = _unidade_ativa.get()
        if unidade_id is None:
            raise RuntimeError("No active unidade in current request context")
        return unidade_id

    @staticmethod
    def set_tenant(tenant_id: int) -> None:
        """Define o tenant da requisição. Fora de request, use `contexto_tenant`."""
        if _sem_tenant.get() is not None:
            raise RuntimeError("set_tenant dentro de sem_tenant")
        _tenant_ativo.set(_validar_tenant_id(tenant_id))

    @staticmethod
    def get_tenant() -> int:
        """Tenant ativo. Não há fallback: sem tenant, levanta RuntimeError."""
        tenant_id = _tenant_ativo.get()
        if tenant_id is None:
            raise RuntimeError("No active tenant in current context")
        return tenant_id

    @staticmethod
    def get_tenant_ou_none() -> int | None:
        """Para quem precisa decidir (a guarda), nunca para filtrar consultas."""
        return _tenant_ativo.get()

    @staticmethod
    def motivo_sem_tenant() -> str | None:
        """Motivo do `sem_tenant` em curso, ou None fora dele."""
        return _sem_tenant.get()

    @staticmethod
    def set_plataforma_admin(admin_id: int) -> None:
        _plataforma_admin.set(admin_id)

    @staticmethod
    def get_plataforma_admin() -> int:
        admin_id = _plataforma_admin.get()
        if admin_id is None:
            raise RuntimeError("No platform admin in current request context")
        return admin_id

    @staticmethod
    def clear() -> None:
        _plataforma_admin.set(None)
        _current_user.set(None)
        _unidade_ativa.set(None)
        _tenant_ativo.set(None)
        _sem_tenant.set(None)


@contextmanager
def contexto_tenant(tenant_id: int) -> Iterator[int]:
    """Executa um trecho dentro de um tenant e restaura o estado anterior ao sair.

    Para scripts, CLI e rotinas agendadas, que não passam pelo login. Não pode
    ficar dentro de `sem_tenant` nem trocar de tenant no meio de outro: cada
    tenant roda no seu próprio bloco.
    """
    tenant_id = _validar_tenant_id(tenant_id)
    if _sem_tenant.get() is not None:
        raise RuntimeError("contexto_tenant dentro de sem_tenant")
    atual = _tenant_ativo.get()
    if atual is not None and atual != tenant_id:
        raise RuntimeError(f"contexto_tenant({tenant_id}) dentro do tenant {atual}")
    token = _tenant_ativo.set(tenant_id)
    try:
        yield tenant_id
    finally:
        _tenant_ativo.reset(token)


@contextmanager
def sem_tenant(motivo: str) -> Iterator[None]:
    """Trecho que roda de propósito sem tenant, com motivo obrigatório e logado.

    Dentro dele não há tenant ativo, mesmo que houvesse um fora; ao sair, o
    estado anterior volta. Serve à plataforma e às poucas consultas que precisam
    descobrir o tenant (a busca do e-mail no login).
    """
    if not isinstance(motivo, str) or not motivo.strip():
        raise ValueError("sem_tenant exige um motivo")
    logger.info("Trecho sem tenant: %s", motivo)
    token_motivo = _sem_tenant.set(motivo)
    token_tenant = _tenant_ativo.set(None)
    try:
        yield
    finally:
        _tenant_ativo.reset(token_tenant)
        _sem_tenant.reset(token_motivo)
