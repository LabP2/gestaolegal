from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from flask import current_app

from gestaolegal.models.user import UserInfo
from gestaolegal.services.usuario_service import UsuarioService

# Público do token de quem trabalha num NPJ. O admin da plataforma (PR 7 do
# plano multitenant) terá outro público, e um token não serve no lugar do outro.
AUD_TENANT = "tenant"


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
        if not all(
            isinstance(v, int) and not isinstance(v, bool) and v > 0
            for v in (user_id, tenant_id)
        ):
            return None

        user_service = UsuarioService()
        # O tenant vem só do token, a única autoridade depois do login. O
        # usuário é lido já dentro dele: conta de outro NPJ não é encontrada.
        if not user_service.entrar_no_tenant(tenant_id):
            return None
        return user_service.find_by_id(user_id)
