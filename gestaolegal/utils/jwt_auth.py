from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from flask import current_app

from gestaolegal.models.user import UserInfo
from gestaolegal.services.usuario_service import UsuarioService

# Público do token de quem trabalha num NPJ e do token do administrador da
# plataforma (docs/plano-multitenant.md §6.1). O `aud` é conferido na
# decodificação, então um token não serve no lugar do outro.
AUD_TENANT = "tenant"
AUD_PLATAFORMA = "plataforma"

# Sessão da plataforma mais curta que a do NPJ: ela cria e desativa NPJs.
PLATAFORMA_TOKEN_HORAS = 8


def _id_valido(valor: Any) -> bool:
    # bool é subclasse de int: True passaria como 1.
    return isinstance(valor, int) and not isinstance(valor, bool) and valor > 0


class JWTAuth:
    @staticmethod
    def generate_token(user: UserInfo, tenant_id: int) -> str:
        now = datetime.now(UTC)
        payload = {
            "user_id": user.id,
            "tenant_id": tenant_id,
            "aud": AUD_TENANT,
            "email": user.email,
            "urole": user.urole,
            "exp": now + timedelta(hours=12),
            "iat": now,
        }

        JWT_SECRET_KEY = str(current_app.config.get("JWT_SECRET_KEY"))

        return jwt.encode(payload, key=JWT_SECRET_KEY, algorithm="HS256")

    @staticmethod
    def verify_token(token: str) -> dict[str, Any] | None:
        """Payload de um token válido de NPJ, ou None.

        Token sem `tenant_id` ou sem `aud` (emitido antes do multitenant) é
        recusado: no deploy todos entram de novo, e o token dura só 12 h.
        """
        try:
            JWT_SECRET_KEY = str(current_app.config.get("JWT_SECRET_KEY"))
            payload: dict[str, Any] = jwt.decode(
                token,
                key=JWT_SECRET_KEY,
                algorithms=["HS256"],
                audience=AUD_TENANT,
                options={"require": ["exp", "iat", "aud", "user_id", "tenant_id"]},
            )

            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    @staticmethod
    def get_user_from_token(token: str) -> UserInfo | None:
        payload = JWTAuth.verify_token(token)
        if not payload:
            return None

        user_id = payload.get("user_id")
        tenant_id = payload.get("tenant_id")
        # bool é subclasse de int: True passaria como 1.
        if not all(_id_valido(v) for v in (user_id, tenant_id)):
            return None

        user_service = UsuarioService()
        # O tenant vem só do token, a única autoridade depois do login. O
        # usuário é lido já dentro dele: conta de outro NPJ não é encontrada.
        if not user_service.entrar_no_tenant(tenant_id):
            return None
        return user_service.find_by_id(user_id)

    @staticmethod
    def generate_plataforma_token(admin_id: int) -> str:
        """Token do administrador da plataforma: sem `tenant_id`, aud própria."""
        now = datetime.now(UTC)
        payload = {
            "plataforma_admin_id": admin_id,
            "aud": AUD_PLATAFORMA,
            "exp": now + timedelta(hours=PLATAFORMA_TOKEN_HORAS),
            "iat": now,
        }
        key = str(current_app.config.get("JWT_SECRET_KEY"))
        return jwt.encode(payload, key=key, algorithm="HS256")

    @staticmethod
    def plataforma_admin_id(token: str) -> int | None:
        """Id do admin da plataforma num token válido de plataforma, ou None.

        Um token que traga `tenant_id` é recusado mesmo com a aud certa: a
        plataforma não pertence a nenhum NPJ.
        """
        try:
            key = str(current_app.config.get("JWT_SECRET_KEY"))
            payload: dict[str, Any] = jwt.decode(
                token,
                key=key,
                algorithms=["HS256"],
                audience=AUD_PLATAFORMA,
                options={"require": ["exp", "iat", "aud", "plataforma_admin_id"]},
            )
        except jwt.InvalidTokenError:
            return None
        if "tenant_id" in payload:
            return None
        admin_id = payload.get("plataforma_admin_id")
        return admin_id if _id_valido(admin_id) else None
