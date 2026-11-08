"""O token carrega o NPJ, e só ele decide o tenant depois do login.

docs/plano-multitenant.md, §5: o tenant sai do e-mail no login e, a partir daí,
do JWT. Token sem tenant (anterior ao multitenant), de outro público, ou de um
NPJ ao qual a conta não pertence, é recusado.
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from flask import Flask
from flask.testing import FlaskClient

from gestaolegal.utils.jwt_auth import AUD_TENANT

from .conftest import (
    TENANT_DAJ,
    TENANT_OUTRO,
    TEST_ADMIN_EMAIL,
    TEST_ADMIN_PASSWORD,
    get_success_data,
)


def _login(client: FlaskClient) -> str:
    response = client.post(
        "/api/auth/login",
        json={"email": TEST_ADMIN_EMAIL, "password": TEST_ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    return get_success_data(response)["token"]


def _claims(token: str) -> dict:
    return jwt.decode(token, options={"verify_signature": False})


def _assinar(app: Flask, payload: dict) -> str:
    return jwt.encode(payload, key=app.config["JWT_SECRET_KEY"], algorithm="HS256")


def _me(client: FlaskClient, token: str) -> int:
    headers = {"Authorization": f"Bearer {token}"}
    return client.get("/api/user/me", headers=headers).status_code


def test_login_emite_token_com_tenant_e_publico(
    client: FlaskClient, create_admin_user: None
) -> None:
    claims = _claims(_login(client))
    assert claims["tenant_id"] == TENANT_DAJ
    assert claims["aud"] == AUD_TENANT


def test_token_valido_e_aceito(
    client: FlaskClient, app: Flask, create_admin_user: None
) -> None:
    # Controle dos casos abaixo: o mesmo payload, reassinado, ainda vale.
    claims = _claims(_login(client))
    assert _me(client, _assinar(app, claims)) == 200


@pytest.mark.parametrize(
    "alteracao",
    [
        pytest.param({"tenant_id": None}, id="sem-tenant"),
        pytest.param({"aud": None}, id="sem-publico"),
        pytest.param({"aud": "plataforma"}, id="publico-da-plataforma"),
        pytest.param({"tenant_id": TENANT_OUTRO}, id="npj-de-que-a-conta-nao-e"),
        pytest.param({"tenant_id": 999}, id="npj-inexistente"),
        pytest.param({"tenant_id": True}, id="tenant-booleano"),
        pytest.param({"tenant_id": "1"}, id="tenant-texto"),
        pytest.param({"tenant_id": 0}, id="tenant-zero"),
    ],
)
def test_token_adulterado_e_recusado(
    client: FlaskClient, app: Flask, create_admin_user: None, alteracao: dict
) -> None:
    claims = _claims(_login(client))
    for chave, valor in alteracao.items():
        if valor is None:
            claims.pop(chave)
        else:
            claims[chave] = valor
    assert _me(client, _assinar(app, claims)) == 401


def test_token_anterior_ao_multitenant_e_recusado(
    client: FlaskClient, app: Flask, create_admin_user: None
) -> None:
    # Formato exato do token emitido antes do PR 4: sem tenant_id e sem aud.
    antigo = _claims(_login(client))
    agora = datetime.now(UTC)
    token = _assinar(
        app,
        {
            "user_id": antigo["user_id"],
            "email": antigo["email"],
            "urole": antigo["urole"],
            "exp": agora + timedelta(hours=12),
            "iat": agora,
        },
    )
    assert _me(client, token) == 401


def test_me_devolve_o_npj_da_conta(client: FlaskClient, auth_headers: dict) -> None:
    dados = get_success_data(client.get("/api/user/me", headers=auth_headers))
    assert dados["tenant"] == {
        "nome": "Divisão de Assistência Judiciária",
        "sigla": "DAJ",
    }
