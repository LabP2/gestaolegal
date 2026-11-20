"""API do administrador da plataforma (docs/plano-multitenant.md §6.2).

Montada em `/api/plataforma`. Só o login é público; o resto exige
`@plataforma_admin`, que recusa token de NPJ.
"""

import logging

from flask import Blueprint, request

from gestaolegal.exceptions import UnauthorizedException, ValidationException
from gestaolegal.services.plataforma_service import (
    PlataformaService,
    admin_publico,
    tenant_publico,
)
from gestaolegal.utils.api_decorators import plataforma_admin
from gestaolegal.utils.api_response import success_response
from gestaolegal.utils.jwt_auth import JWTAuth
from gestaolegal.utils.request_context import RequestContext

logger = logging.getLogger(__name__)

plataforma_controller = Blueprint("plataforma_api", __name__)


def _json() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationException("Corpo JSON obrigatório")
    return data


@plataforma_controller.route("/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = data.get("email")
    senha = data.get("password")
    if not isinstance(email, str) or not isinstance(senha, str) or not email or not senha:
        raise ValidationException("Email e senha são obrigatórios")

    admin = PlataformaService().autenticar(email, senha)
    if admin is None:
        raise UnauthorizedException("Email ou senha inválidos")

    logger.info(f"Login na plataforma: {admin.email}")
    return success_response(
        data={
            "token": JWTAuth.generate_plataforma_token(admin.id),
            "admin": admin_publico(admin),
        }
    )


@plataforma_controller.route("/auth/me", methods=["GET"])
@plataforma_admin
def me():
    admin = PlataformaService().obter_admin(RequestContext.get_plataforma_admin())
    return success_response(data=admin_publico(admin))


@plataforma_controller.route("/tenants", methods=["GET"])
@plataforma_admin
def listar():
    ativo_param = request.args.get("ativo")
    ativo = {"true": True, "false": False}.get((ativo_param or "").lower())
    q = request.args.get("q", default="", type=str)
    tenants = PlataformaService().listar(ativo=ativo, q=q)
    return success_response(data={"items": [tenant_publico(t) for t in tenants]})


@plataforma_controller.route("/tenants", methods=["POST"])
@plataforma_admin
def criar():
    resultado = PlataformaService().criar(
        _json(), admin_id=RequestContext.get_plataforma_admin()
    )
    return success_response(data=resultado, status_code=201)


@plataforma_controller.route("/tenants/<int:tenant_id>", methods=["GET"])
@plataforma_admin
def detalhe(tenant_id: int):
    return success_response(data=tenant_publico(PlataformaService().obter(tenant_id)))


@plataforma_controller.route("/tenants/<int:tenant_id>", methods=["PUT"])
@plataforma_admin
def atualizar(tenant_id: int):
    tenant = PlataformaService().atualizar(tenant_id, _json())
    return success_response(data=tenant_publico(tenant))


@plataforma_controller.route("/tenants/<int:tenant_id>/ativo", methods=["PATCH"])
@plataforma_admin
def definir_ativo(tenant_id: int):
    tenant = PlataformaService().definir_ativo(tenant_id, _json().get("ativo"))
    return success_response(data=tenant_publico(tenant))
