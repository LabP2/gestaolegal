"""Administração da plataforma: login próprio e cadastro dos NPJs (tenants).

docs/plano-multitenant.md §6. O administrador da plataforma não lê dados dos
NPJs: tudo aqui toca só `tenants` e `plataforma_admins`, dentro de
`sem_tenant(motivo)`. A exceção é a criação de um NPJ, cujo primeiro admin e
unidade nascem dentro do tenant novo, em `contexto_tenant(novo_id)`.
"""

import logging
import re
from dataclasses import asdict
from datetime import datetime
from typing import Any

import bcrypt
from sqlalchemy.exc import IntegrityError

from gestaolegal.config import Config
from gestaolegal.database.session import get_session
from gestaolegal.exceptions import NotFoundException, ValidationException
from gestaolegal.models.plataforma import PlataformaAdmin, Tenant
from gestaolegal.repositories.tenant_repository import (
    PlataformaAdminRepository,
    TenantRepository,
)
from gestaolegal.repositories.unidade_repository import UnidadeRepository
from gestaolegal.services.password_reset_service import PasswordResetService
from gestaolegal.services.usuario_service import UsuarioService
from gestaolegal.utils.request_context import contexto_tenant, sem_tenant

logger = logging.getLogger(__name__)

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Tamanhos das colunas em tables.py.
LIMITES = {
    "nome": 150,
    "sigla": 20,
    "slug": 40,
    "instituicao": 150,
    "unidade_nome": 60,
    "unidade_sigla": 10,
    "admin_nome": 60,
    "admin_email": 80,
}


def tenant_publico(tenant: Tenant) -> dict[str, Any]:
    return asdict(tenant)


def admin_publico(admin: PlataformaAdmin) -> dict[str, Any]:
    dados = asdict(admin)
    dados.pop("senha")
    return dados


def _texto(data: dict[str, Any], campo: str, obrigatorio: bool = True) -> str | None:
    valor = data.get(campo)
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        if obrigatorio:
            raise ValidationException("Campo obrigatório", field=campo)
        return None
    if not isinstance(valor, str):
        raise ValidationException("Valor inválido", field=campo)
    valor = valor.strip()
    if len(valor) > LIMITES[campo]:
        raise ValidationException(
            f"Máximo de {LIMITES[campo]} caracteres", field=campo
        )
    return valor


class PlataformaService:
    def __init__(self):
        self.tenants = TenantRepository()
        self.admins = PlataformaAdminRepository()

    # --- administradores -----------------------------------------------------

    def autenticar(self, email: str, senha: str) -> PlataformaAdmin | None:
        with sem_tenant("plataforma: login do administrador"):
            admin = self.admins.find_by_email(email)
            if admin is None or not admin.ativo:
                return None
            if not bcrypt.checkpw(senha.encode("utf-8"), admin.senha.encode("utf-8")):
                return None
            self.admins.registrar_login(admin.id)
            return admin

    def admin_ativo(self, admin_id: int) -> bool:
        with sem_tenant("plataforma: conferir o administrador do token"):
            admin = self.admins.find_by_id(admin_id)
            return admin is not None and admin.ativo

    def obter_admin(self, admin_id: int) -> PlataformaAdmin:
        with sem_tenant("plataforma: dados do administrador"):
            admin = self.admins.find_by_id(admin_id)
        if admin is None:
            raise NotFoundException("Administrador", admin_id)
        return admin

    def criar_admin(self, nome: str, email: str, senha: str) -> int:
        """Administrador da plataforma (bootstrap pela CLI `criar-admin`)."""
        nome = (nome or "").strip()
        email = (email or "").strip().lower()
        if not nome or len(nome) > 60:
            raise ValidationException("Nome obrigatório (até 60 caracteres)", field="nome")
        if not EMAIL_RE.match(email) or len(email) > 80:
            raise ValidationException("E-mail inválido", field="email")
        if len(senha or "") < Config.PASSWORD_MIN_LENGTH:
            raise ValidationException(
                f"A senha deve ter pelo menos {Config.PASSWORD_MIN_LENGTH} caracteres",
                field="senha",
            )
        senha_hash = bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode()
        with sem_tenant("plataforma: criar administrador"):
            if self.admins.find_by_email(email):
                raise ValidationException("E-mail já está em uso", field="email")
            return self.admins.criar(nome, email, senha_hash)

    # --- tenants -------------------------------------------------------------

    def listar(self, ativo: bool | None = None, q: str = "") -> list[Tenant]:
        with sem_tenant("plataforma: listar NPJs"):
            return self.tenants.listar(ativo=ativo, q=q.strip())

    def obter(self, tenant_id: int) -> Tenant:
        with sem_tenant("plataforma: detalhe do NPJ"):
            tenant = self.tenants.find(tenant_id)
        if tenant is None:
            raise NotFoundException("NPJ", tenant_id)
        return tenant

    def _exigir_unicos(self, sigla: str | None, slug: str | None, ignorar_id=None):
        if sigla and self.tenants.em_uso("sigla", sigla, ignorar_id):
            raise ValidationException("Sigla já usada por outro NPJ", field="sigla")
        if slug and self.tenants.em_uso("slug", slug, ignorar_id):
            raise ValidationException("Identificador já usado por outro NPJ", field="slug")

    def criar(self, data: dict[str, Any], admin_id: int) -> dict[str, Any]:
        """Cria o NPJ, a unidade inicial, o primeiro admin e o link de senha.

        Tudo na mesma transação: qualquer falha desfaz o que já foi gravado,
        inclusive a linha em `tenants` (plano §6.3).
        """
        nome = _texto(data, "nome")
        sigla = _texto(data, "sigla")
        slug = (_texto(data, "slug") or "").lower()
        instituicao = _texto(data, "instituicao", obrigatorio=False)
        unidade_nome = _texto(data, "unidade_nome")
        unidade_sigla = _texto(data, "unidade_sigla")
        admin_nome = _texto(data, "admin_nome")
        admin_email = (_texto(data, "admin_email") or "").lower()
        if not SLUG_RE.match(slug):
            raise ValidationException(
                "Use letras minúsculas, números e hífens (ex.: npj-puc-minas)",
                field="slug",
            )
        if not EMAIL_RE.match(admin_email):
            raise ValidationException("E-mail inválido", field="admin_email")

        session = get_session()
        try:
            with sem_tenant("plataforma: criar NPJ"):
                self._exigir_unicos(sigla, slug)
                tenant_id = self.tenants.criar(
                    {
                        "nome": nome,
                        "sigla": sigla,
                        "slug": slug,
                        "instituicao": instituicao,
                        "ativo": True,
                        "criado_em": datetime.now(),
                        "id_criado_por": admin_id,
                    }
                )

            with contexto_tenant(tenant_id):
                unidade_id = UnidadeRepository().create(
                    {
                        "nome": unidade_nome,
                        "sigla": unidade_sigla,
                        "ativa": True,
                        "criado": datetime.now(),
                    }
                )
                try:
                    admin = UsuarioService().create_admin(
                        admin_email, admin_nome, unidade_id
                    )
                except ValidationException as e:
                    # O e-mail é único na plataforma; o campo do formulário é outro.
                    if e.details.get("field") == "email":
                        raise ValidationException(e.message, field="admin_email") from e
                    raise
                link = PasswordResetService().emitir_primeiro_acesso(admin.id)

            with sem_tenant("plataforma: ler o NPJ criado"):
                tenant = self.tenants.find(tenant_id)
            session.commit()
        except IntegrityError as e:
            # Corrida com outro cadastro: as checagens acima passaram, o banco não.
            session.rollback()
            logger.warning(f"Criação de NPJ recusada pelo banco: {e.orig}")
            raise ValidationException(
                "Sigla, identificador ou e-mail já estão em uso"
            ) from e
        except Exception:
            # Erro tratado pelo Flask não chega ao teardown como exceção, e o
            # teardown faria commit do que já foi gravado.
            session.rollback()
            raise

        logger.info(f"NPJ {slug} (id {tenant_id}) criado pelo admin da plataforma {admin_id}")
        assert tenant is not None
        return {
            "tenant": tenant_publico(tenant),
            "admin": {"id": admin.id, "nome": admin.nome, "email": admin.email},
            "link_primeiro_acesso": link,
        }

    def atualizar(self, tenant_id: int, data: dict[str, Any]) -> Tenant:
        """Nome, sigla e instituição. O slug não muda depois de criado."""
        if "slug" in data:
            raise ValidationException("O identificador não pode ser alterado", field="slug")
        valores: dict[str, Any] = {}
        if "nome" in data:
            valores["nome"] = _texto(data, "nome")
        if "sigla" in data:
            valores["sigla"] = _texto(data, "sigla")
        if "instituicao" in data:
            valores["instituicao"] = _texto(data, "instituicao", obrigatorio=False)

        with sem_tenant("plataforma: editar NPJ"):
            if self.tenants.find(tenant_id) is None:
                raise NotFoundException("NPJ", tenant_id)
            self._exigir_unicos(valores.get("sigla"), None, ignorar_id=tenant_id)
            if valores:
                self.tenants.atualizar(tenant_id, valores)
            tenant = self.tenants.find(tenant_id)
        assert tenant is not None
        return tenant

    def definir_ativo(self, tenant_id: int, ativo: Any) -> Tenant:
        """Ativa ou desativa. Desativado, o NPJ não entra e os tokens caem."""
        if not isinstance(ativo, bool):
            raise ValidationException("Informe true ou false", field="ativo")
        with sem_tenant("plataforma: ativar ou desativar NPJ"):
            if self.tenants.find(tenant_id) is None:
                raise NotFoundException("NPJ", tenant_id)
            self.tenants.atualizar(tenant_id, {"ativo": ativo})
            tenant = self.tenants.find(tenant_id)
        assert tenant is not None
        logger.info(f"NPJ {tenant_id} {'ativado' if ativo else 'desativado'}")
        return tenant
