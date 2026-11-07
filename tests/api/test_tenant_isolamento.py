"""Isolamento entre tenants (NPJs) nas rotas mais expostas.

O tenant 1 (DAJ) e o tenant 2 (outro NPJ) dividem o banco. Nenhum dos dois
pode ler, alterar ou descobrir dados do outro. A varredura completa de todas as
rotas entra no PR 6 do plano (docs/plano-multitenant.md, §10); aqui ficam os
casos que provam o mecanismo: login, leitura por id, listagem, busca global,
avisos gerais e unicidades.
"""

from datetime import date, datetime

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import text

from gestaolegal.database import session as db_session_module

from .conftest import (
    TENANT_OUTRO,
    UNIDADE_OUTRO,
    assert_error_response,
    criar_usuario,
    get_success_data,
    headers_para,
)

OUTRO_EMAIL = "admin@outro-npj.br"
OUTRO_SENHA = "outrasenha123"


@pytest.fixture
def headers_outro(client: FlaskClient, app: Flask) -> dict[str, str]:
    """Admin do tenant 2, na unidade dele."""
    with app.app_context():
        criar_usuario(
            OUTRO_EMAIL, OUTRO_SENHA, "admin", "Admin Outro NPJ", tenant_id=TENANT_OUTRO
        )
    return headers_para(client, OUTRO_EMAIL, OUTRO_SENHA, unidade=UNIDADE_OUTRO)


@pytest.fixture
def atendido_daj(client, auth_headers, sample_atendido_data) -> dict:
    response = client.post("/api/atendido/", json=sample_atendido_data, headers=auth_headers)
    assert response.status_code == 201, response.get_json()
    return get_success_data(response)


def _executar(sql: str, params: dict) -> None:
    session = db_session_module.get_session()
    try:
        session.execute(text(sql), params)
        session.commit()
    finally:
        session.close()


class TestLogin:
    def test_login_leva_cada_conta_ao_seu_tenant(self, client, headers_outro, auth_headers):
        resposta_outro = client.get("/api/user/me", headers=headers_outro)
        resposta_daj = client.get("/api/user/me", headers=auth_headers)
        assert get_success_data(resposta_outro)["email"] == OUTRO_EMAIL
        assert get_success_data(resposta_daj)["email"] != OUTRO_EMAIL

    def test_unidade_de_outro_tenant_e_recusada(self, client, headers_outro):
        headers = {**headers_outro, "X-Unidade-Id": "1"}
        response = client.get("/api/atendido/", headers=headers)
        assert response.status_code == 403

    def test_tenant_inativo_bloqueia_login_e_token(self, client, headers_outro):
        _executar("UPDATE tenants SET ativo = 0 WHERE id = :id", {"id": TENANT_OUTRO})
        try:
            login = client.post(
                "/api/auth/login", json={"email": OUTRO_EMAIL, "password": OUTRO_SENHA}
            )
            assert login.status_code == 401
            # O token emitido antes da desativação também deixa de valer.
            assert client.get("/api/user/me", headers=headers_outro).status_code == 401
        finally:
            _executar("UPDATE tenants SET ativo = 1 WHERE id = :id", {"id": TENANT_OUTRO})


class TestLeitura:
    def test_atendido_de_outro_tenant_nao_aparece(
        self, client, headers_outro, atendido_daj
    ):
        response = client.get(f"/api/atendido/{atendido_daj['id']}", headers=headers_outro)
        assert response.status_code == 404

        lista = get_success_data(client.get("/api/atendido/", headers=headers_outro))
        assert atendido_daj["id"] not in {item["id"] for item in lista["items"]}

    def test_atendido_de_outro_tenant_nao_e_alterado(
        self, client, headers_outro, auth_headers, atendido_daj
    ):
        response = client.put(
            f"/api/atendido/{atendido_daj['id']}",
            json={"nome": "Alterado pelo outro NPJ"},
            headers=headers_outro,
        )
        assert response.status_code in (400, 404)
        depois = get_success_data(
            client.get(f"/api/atendido/{atendido_daj['id']}", headers=auth_headers)
        )
        assert depois["nome"] == atendido_daj["nome"]

    def test_usuarios_de_outro_tenant_nao_aparecem(self, client, headers_outro, auth_headers):
        lista = get_success_data(client.get("/api/user/", headers=headers_outro))
        emails = {item["email"] for item in lista["items"]}
        assert emails == {OUTRO_EMAIL}

        opcoes = get_success_data(client.get("/api/user/opcoes", headers=headers_outro))
        assert {item["nome"] for item in opcoes["items"]} == {"Admin Outro NPJ"}

    def test_busca_global_fica_no_tenant(self, client, headers_outro, atendido_daj):
        termo = atendido_daj["nome"][:4]
        dados = get_success_data(
            client.get(f"/api/search/?q={termo}", headers=headers_outro)
        )
        assert dados["results"]["atendidos"] == {"items": [], "total": 0}
        usuarios = dados["results"]["usuarios"]["items"]
        assert all(u["email"] == OUTRO_EMAIL for u in usuarios), usuarios

    def test_aviso_geral_de_outro_tenant_nao_aparece(self, client, headers_outro):
        _executar(
            """
            INSERT INTO notificacao (tenant_id, acao, data, tipo, lida, data_criacao)
            VALUES (1, 'Aviso geral da DAJ', :data, 'plantao', 0, :agora)
            """,
            {"data": date.today(), "agora": datetime.now()},
        )
        lista = get_success_data(client.get("/api/notificacao/", headers=headers_outro))
        assert all(item["acao"] != "Aviso geral da DAJ" for item in lista["items"])


class TestUnicidade:
    def test_email_de_outro_tenant_nao_pode_ser_reusado(
        self, client, headers_outro, sample_user_data
    ):
        payload = {**sample_user_data, "email": OUTRO_EMAIL, "unidade_ids": [1]}
        from .conftest import TEST_ADMIN_EMAIL, TEST_ADMIN_PASSWORD

        headers_daj = headers_para(client, TEST_ADMIN_EMAIL, TEST_ADMIN_PASSWORD)
        response = client.post("/api/user/", json=payload, headers=headers_daj)
        assert response.status_code == 400
        erro = assert_error_response(response)
        # A mensagem não revela em qual NPJ a conta existe.
        assert "outro" not in str(erro).lower()
