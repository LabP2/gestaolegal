"""Administração da plataforma (docs/plano-multitenant.md §6).

O administrador da plataforma tem login e token próprios (aud="plataforma") e
só cadastra NPJs. Criar um NPJ cria, na mesma transação, a unidade inicial, o
primeiro admin e o link de primeiro acesso.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest import mock

import jwt
import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import text

from gestaolegal.database import session as db_session_module
from gestaolegal.services.usuario_service import UsuarioService

from .conftest import (
    TEST_ADMIN_EMAIL,
    assert_error_response,
    ensure_tenants,
    get_success_data,
)

PLAT_EMAIL = "raiz@plataforma.br"
PLAT_SENHA = "plataforma-senha-123"


def _consulta(sql: str, params: dict | None = None) -> list:
    session = db_session_module.get_session()
    try:
        return session.execute(text(sql), params or {}).fetchall()
    finally:
        session.close()


def _executar(sql: str, params: dict | None = None) -> None:
    session = db_session_module.get_session()
    try:
        session.execute(text(sql), params or {})
        session.commit()
    finally:
        session.close()


def _campo(response) -> str | None:
    return (assert_error_response(response)["error"].get("details") or {}).get("field")


@pytest.fixture(scope="module")
def admin_plataforma(app: Flask) -> None:
    """Criado pela CLI de bootstrap, como numa instalação de verdade."""
    with app.app_context():
        ensure_tenants()
    if _consulta("SELECT id FROM plataforma_admins WHERE email = :e", {"e": PLAT_EMAIL}):
        return
    resultado = app.test_cli_runner().invoke(
        args=[
            "plataforma",
            "criar-admin",
            "--email",
            PLAT_EMAIL,
            "--nome",
            "Raiz da Plataforma",
            "--senha",
            PLAT_SENHA,
        ]
    )
    assert resultado.exit_code == 0, resultado.output
    assert "criado" in resultado.output


@pytest.fixture
def plat_headers(client: FlaskClient, admin_plataforma: None) -> dict[str, str]:
    response = client.post(
        "/api/plataforma/auth/login",
        json={"email": PLAT_EMAIL, "password": PLAT_SENHA},
    )
    assert response.status_code == 200, response.get_json()
    return {"Authorization": f"Bearer {get_success_data(response)['token']}"}


def _novo_npj(**extra) -> dict:
    sufixo = uuid.uuid4().hex[:6]
    dados = {
        "nome": f"NPJ Teste {sufixo}",
        "sigla": f"T{sufixo}".upper(),
        "slug": f"npj-{sufixo}",
        "instituicao": "Universidade Teste",
        "unidade_nome": "Sede",
        "unidade_sigla": "SD",
        "admin_nome": "Primeira Admin",
        "admin_email": f"admin-{sufixo}@npj.br",
    }
    dados.update(extra)
    return dados


def _criar(client, plat_headers, **extra):
    dados = _novo_npj(**extra)
    return dados, client.post("/api/plataforma/tenants", json=dados, headers=plat_headers)


class TestLogin:
    def test_login_devolve_token_de_plataforma_sem_tenant(self, client, admin_plataforma, app):
        response = client.post(
            "/api/plataforma/auth/login",
            json={"email": PLAT_EMAIL, "password": PLAT_SENHA},
        )
        assert response.status_code == 200
        dados = get_success_data(response)
        assert "senha" not in dados["admin"]
        payload = jwt.decode(
            dados["token"],
            key=str(app.config["JWT_SECRET_KEY"]),
            algorithms=["HS256"],
            audience="plataforma",
        )
        assert "tenant_id" not in payload
        assert _consulta(
            "SELECT ultimo_login_em FROM plataforma_admins WHERE email = :e",
            {"e": PLAT_EMAIL},
        )[0][0] is not None

    @pytest.mark.parametrize(
        "corpo",
        [
            {"email": PLAT_EMAIL, "password": "errada"},
            {"email": "ninguem@plataforma.br", "password": PLAT_SENHA},
            # Conta de NPJ não entra na plataforma, nem com a senha certa.
            {"email": TEST_ADMIN_EMAIL, "password": "123456"},
        ],
    )
    def test_login_recusado(self, client, admin_plataforma, auth_headers, corpo):
        response = client.post("/api/plataforma/auth/login", json=corpo)
        assert response.status_code == 401

    def test_admin_desativado_nao_entra_e_perde_o_token(self, client, plat_headers):
        _executar("UPDATE plataforma_admins SET ativo = 0 WHERE email = :e", {"e": PLAT_EMAIL})
        try:
            login = client.post(
                "/api/plataforma/auth/login",
                json={"email": PLAT_EMAIL, "password": PLAT_SENHA},
            )
            assert login.status_code == 401
            assert client.get("/api/plataforma/tenants", headers=plat_headers).status_code == 401
        finally:
            _executar(
                "UPDATE plataforma_admins SET ativo = 1 WHERE email = :e", {"e": PLAT_EMAIL}
            )

    def test_me(self, client, plat_headers):
        dados = get_success_data(client.get("/api/plataforma/auth/me", headers=plat_headers))
        assert dados["email"] == PLAT_EMAIL
        assert "senha" not in dados


class TestAudiencias:
    def test_token_de_npj_nao_acessa_a_plataforma(self, client, auth_headers):
        assert client.get("/api/plataforma/tenants", headers=auth_headers).status_code == 401
        response = client.post(
            "/api/plataforma/tenants", json=_novo_npj(), headers=auth_headers
        )
        assert response.status_code == 401

    def test_token_da_plataforma_nao_acessa_o_npj(self, client, plat_headers):
        headers = {**plat_headers, "X-Unidade-Id": "1"}
        for rota in ("/api/user/me", "/api/atendido/", "/api/user/"):
            assert client.get(rota, headers=headers).status_code == 401, rota

    def test_sem_token(self, client):
        assert client.get("/api/plataforma/tenants").status_code == 401

    def test_token_de_plataforma_com_tenant_e_recusado(self, client, app, admin_plataforma):
        (admin_id,) = _consulta(
            "SELECT id FROM plataforma_admins WHERE email = :e", {"e": PLAT_EMAIL}
        )[0]
        agora = datetime.now(timezone.utc)
        token = jwt.encode(
            {
                "plataforma_admin_id": admin_id,
                "tenant_id": 1,
                "aud": "plataforma",
                "iat": agora,
                "exp": agora + timedelta(hours=1),
            },
            key=str(app.config["JWT_SECRET_KEY"]),
            algorithm="HS256",
        )
        response = client.get(
            "/api/plataforma/tenants", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 401


class TestCriacao:
    def test_cria_tenant_unidade_admin_e_link(self, client, plat_headers):
        dados, response = _criar(client, plat_headers)
        assert response.status_code == 201, response.get_json()
        corpo = get_success_data(response)
        tenant_id = corpo["tenant"]["id"]
        assert corpo["tenant"]["slug"] == dados["slug"]
        assert corpo["tenant"]["ativo"] is True
        assert corpo["tenant"]["id_criado_por"] is not None
        assert corpo["admin"]["email"] == dados["admin_email"]
        assert "/redefinir-senha/" in corpo["link_primeiro_acesso"]

        (unidade_id, unidade_nome) = _consulta(
            "SELECT id, nome FROM unidades WHERE tenant_id = :t", {"t": tenant_id}
        )[0]
        assert unidade_nome == "Sede"
        usuario = _consulta(
            "SELECT id, urole, tenant_id, criadopor FROM usuarios WHERE email = :e",
            {"e": dados["admin_email"]},
        )[0]
        assert usuario[1] == "admin" and usuario[2] == tenant_id
        assert usuario[3] == usuario[0]  # a conta se registra como autora
        assert _consulta(
            "SELECT unidade_id, tenant_id FROM usuarios_unidades WHERE usuario_id = :u",
            {"u": usuario[0]},
        ) == [(unidade_id, tenant_id)]

    def test_link_de_primeiro_acesso_define_a_senha_e_o_admin_entra(
        self, client, plat_headers
    ):
        dados, response = _criar(client, plat_headers)
        corpo = get_success_data(response)
        token = corpo["link_primeiro_acesso"].rsplit("/", 1)[1]

        # Antes de definir a senha, ninguém conhece a senha da conta.
        login = client.post(
            "/api/auth/login", json={"email": dados["admin_email"], "password": "123456"}
        )
        assert login.status_code == 401

        assert client.get(f"/api/auth/reset-password/{token}/validate").status_code == 200
        redefinir = client.post(
            "/api/auth/reset-password",
            json={"token": token, "password": "senha-nova-123"},
        )
        assert redefinir.status_code == 200, redefinir.get_json()

        login = client.post(
            "/api/auth/login",
            json={"email": dados["admin_email"], "password": "senha-nova-123"},
        )
        assert login.status_code == 200
        unidade_id = _consulta(
            "SELECT id FROM unidades WHERE tenant_id = :t", {"t": corpo["tenant"]["id"]}
        )[0][0]
        headers = {
            "Authorization": f"Bearer {get_success_data(login)['token']}",
            "X-Unidade-Id": str(unidade_id),
        }
        me = get_success_data(client.get("/api/user/me", headers=headers))
        assert me["tenant"]["sigla"] == dados["sigla"]
        # O NPJ começa vazio.
        atendidos = get_success_data(client.get("/api/atendido/", headers=headers))
        assert atendidos["items"] == []

    def test_falha_no_admin_desfaz_tenant_e_unidade(self, client, plat_headers):
        dados = _novo_npj()
        with mock.patch.object(
            UsuarioService, "create_admin", side_effect=RuntimeError("falha simulada")
        ):
            response = client.post(
                "/api/plataforma/tenants", json=dados, headers=plat_headers
            )
        # O erro vira 500 tratado; sem o rollback explícito, o teardown da
        # requisição gravaria o tenant e a unidade já inseridos.
        assert response.status_code == 500
        assert _consulta("SELECT id FROM tenants WHERE slug = :s", {"s": dados["slug"]}) == []
        assert _consulta(
            "SELECT id FROM unidades WHERE nome = 'Sede' AND tenant_id NOT IN "
            "(SELECT id FROM tenants)"
        ) == []

    def test_email_de_admin_ja_usado_em_qualquer_npj_desfaz_tudo(
        self, client, plat_headers, auth_headers
    ):
        dados, response = _criar(client, plat_headers, admin_email=TEST_ADMIN_EMAIL)
        assert response.status_code == 400
        assert _campo(response) == "admin_email"
        assert _consulta("SELECT id FROM tenants WHERE slug = :s", {"s": dados["slug"]}) == []

    @pytest.mark.parametrize("campo", ["slug", "sigla"])
    def test_slug_e_sigla_unicos(self, client, plat_headers, campo):
        primeiro, response = _criar(client, plat_headers)
        assert response.status_code == 201
        valor = primeiro[campo].upper() if campo == "slug" else primeiro[campo].lower()
        _, repetido = _criar(client, plat_headers, **{campo: valor})
        assert repetido.status_code == 400
        assert _campo(repetido) == campo

    @pytest.mark.parametrize(
        "extra, campo",
        [
            ({"slug": "Com Espaço"}, "slug"),
            ({"slug": "-comeca-com-hifen"}, "slug"),
            ({"nome": ""}, "nome"),
            ({"unidade_sigla": "X" * 11}, "unidade_sigla"),
            ({"admin_email": "sem-arroba"}, "admin_email"),
        ],
    )
    def test_validacao(self, client, plat_headers, extra, campo):
        _, response = _criar(client, plat_headers, **extra)
        assert response.status_code == 400
        assert _campo(response) == campo


class TestEdicao:
    def test_lista_detalhe_e_filtros(self, client, plat_headers):
        dados, response = _criar(client, plat_headers)
        tenant_id = get_success_data(response)["tenant"]["id"]

        lista = get_success_data(client.get("/api/plataforma/tenants", headers=plat_headers))
        assert {"daj-ufmg", dados["slug"]} <= {t["slug"] for t in lista["items"]}

        filtrada = get_success_data(
            client.get(f"/api/plataforma/tenants?q={dados['slug']}", headers=plat_headers)
        )
        assert [t["id"] for t in filtrada["items"]] == [tenant_id]

        detalhe = get_success_data(
            client.get(f"/api/plataforma/tenants/{tenant_id}", headers=plat_headers)
        )
        assert detalhe["nome"] == dados["nome"]
        assert client.get("/api/plataforma/tenants/999999", headers=plat_headers).status_code == 404

    def test_edita_nome_sigla_e_instituicao_mas_nao_o_slug(self, client, plat_headers):
        _, response = _criar(client, plat_headers)
        tenant_id = get_success_data(response)["tenant"]["id"]
        url = f"/api/plataforma/tenants/{tenant_id}"

        editado = client.put(
            url,
            json={"nome": "Nome Novo", "sigla": "NOVA" + uuid.uuid4().hex[:4], "instituicao": None},
            headers=plat_headers,
        )
        assert editado.status_code == 200, editado.get_json()
        assert get_success_data(editado)["nome"] == "Nome Novo"
        assert get_success_data(editado)["instituicao"] is None

        slug = client.put(url, json={"slug": "outro-slug"}, headers=plat_headers)
        assert slug.status_code == 400
        assert _campo(slug) == "slug"

        sigla_da_daj = client.put(url, json={"sigla": "daj"}, headers=plat_headers)
        assert sigla_da_daj.status_code == 400

    def test_desativar_bloqueia_os_usuarios_do_npj(self, client, plat_headers):
        dados, response = _criar(client, plat_headers)
        corpo = get_success_data(response)
        token = corpo["link_primeiro_acesso"].rsplit("/", 1)[1]
        client.post(
            "/api/auth/reset-password", json={"token": token, "password": "senha-nova-123"}
        )
        credenciais = {"email": dados["admin_email"], "password": "senha-nova-123"}
        login = client.post("/api/auth/login", json=credenciais)
        assert login.status_code == 200
        headers_npj = {"Authorization": f"Bearer {get_success_data(login)['token']}"}

        url = f"/api/plataforma/tenants/{corpo['tenant']['id']}/ativo"
        desativado = client.patch(url, json={"ativo": False}, headers=plat_headers)
        assert desativado.status_code == 200
        assert get_success_data(desativado)["ativo"] is False

        assert client.post("/api/auth/login", json=credenciais).status_code == 401
        assert client.get("/api/user/me", headers=headers_npj).status_code == 401

        reativado = client.patch(url, json={"ativo": True}, headers=plat_headers)
        assert get_success_data(reativado)["ativo"] is True
        assert client.post("/api/auth/login", json=credenciais).status_code == 200

    def test_ativo_exige_booleano(self, client, plat_headers):
        response = client.patch(
            "/api/plataforma/tenants/1/ativo", json={"ativo": "false"}, headers=plat_headers
        )
        assert response.status_code == 400

    def test_nao_ha_exclusao(self, client, plat_headers):
        response = client.delete("/api/plataforma/tenants/1", headers=plat_headers)
        assert response.status_code == 405


class TestCli:
    def test_email_repetido_falha_sem_criar(self, app, admin_plataforma):
        resultado = app.test_cli_runner().invoke(
            args=[
                "plataforma",
                "criar-admin",
                "--email",
                PLAT_EMAIL,
                "--nome",
                "Duplicado",
                "--senha",
                "outra-senha-123",
            ]
        )
        assert resultado.exit_code != 0
        assert "já está em uso" in resultado.output
        assert len(
            _consulta("SELECT id FROM plataforma_admins WHERE email = :e", {"e": PLAT_EMAIL})
        ) == 1

    def test_senha_curta_recusada(self, app):
        resultado = app.test_cli_runner().invoke(
            args=[
                "plataforma",
                "criar-admin",
                "--email",
                "curta@plataforma.br",
                "--nome",
                "Curta",
                "--senha",
                "123",
            ]
        )
        assert resultado.exit_code != 0
        assert _consulta(
            "SELECT id FROM plataforma_admins WHERE email = 'curta@plataforma.br'"
        ) == []
