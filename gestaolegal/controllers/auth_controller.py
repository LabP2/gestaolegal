import logging
from dataclasses import asdict
from typing import cast

from flask import Blueprint, request

from gestaolegal.exceptions import UnauthorizedException, ValidationException
from gestaolegal.services.password_reset_service import PasswordResetService
from gestaolegal.services.usuario_service import UsuarioService
from gestaolegal.utils.api_response import success_response
from gestaolegal.utils.jwt_auth import JWTAuth
from gestaolegal.utils.request_context import RequestContext

logger = logging.getLogger(__name__)

auth_controller = Blueprint("auth_api", __name__)


@auth_controller.route("/login", methods=["POST"])
def login():
    logger.info("Login request received")
    data = cast(dict[str, str], request.get_json())

    if not data or "email" not in data or "password" not in data:
        raise ValidationException("Email e senha são obrigatórios")

    email = data["email"]
    password = data["password"]

    user_service = UsuarioService()
    user = user_service.authenticate(email, password)

    if not user:
        raise UnauthorizedException("Email ou senha inválidos")

    if not user.status:
        raise UnauthorizedException("Conta desativada")

    # authenticate() deixou ativo o NPJ da conta; ele vai no token.
    token = JWTAuth.generate_token(user, RequestContext.get_tenant())

    logger.info(f"User logged in successfully: {email}")
    return success_response(data={"token": token, "user": asdict(user)})


# Resposta única do pedido de recuperação: não revela se o e-mail tem conta,
# se ela está ativa ou se o limite de pedidos foi atingido.
MSG_PEDIDO_RECEBIDO = (
    "Se este e-mail estiver cadastrado, enviamos as instruções "
    "para redefinir a senha."
)


@auth_controller.route("/forgot-password", methods=["POST"])
def forgot_password():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    if not email:
        raise ValidationException("Informe o seu e-mail", field="email")

    PasswordResetService().solicitar(email)
    return success_response(message=MSG_PEDIDO_RECEBIDO)


@auth_controller.route("/reset-password/<token>/validate", methods=["GET"])
def validate_reset_token(token: str):
    PasswordResetService().validar(token)
    return success_response(data={"valid": True})


@auth_controller.route("/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json(silent=True) or {}
    token = (data.get("token") or "").strip()
    password = data.get("password") or ""
    if not token:
        raise ValidationException("Link de redefinição ausente", field="token")

    PasswordResetService().redefinir(token, password)
    return success_response(message="Senha redefinida com sucesso")
