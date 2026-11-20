import pytest
from flask.testing import FlaskClient

from tests.api.conftest import (
    assert_success_response,
    get_success_data,
)

from .conftest import TEST_ADMIN_EMAIL, TEST_ADMIN_PASSWORD


def test_login_success(client: FlaskClient, create_admin_user: None) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@gl.com", "password": "123456"},
    )

    assert response.status_code == 200
    data = get_success_data(response)
    assert data is not None
    assert "token" in data
    assert "user" in data


def test_login_devolve_unidades_do_usuario(
    client: FlaskClient, create_admin_user: None
) -> None:
    """O admin de teste pertence às duas unidades; o login precisa dizer isso."""
    response = client.post(
        "/api/auth/login",
        json={"email": TEST_ADMIN_EMAIL, "password": TEST_ADMIN_PASSWORD},
    )

    assert response.status_code == 200
    user = get_success_data(response)["user"]
    siglas = [unidade["sigla"] for unidade in user["unidades"]]
    assert siglas == ["BH", "NL"]


def test_login_wrong_password(client: FlaskClient, create_admin_user: None) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@gl.com", "password": "wrong_password"},
    )

    assert response.status_code == 401


def test_login_wrong_email(client: FlaskClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": "nonexistent@example.com", "password": "123456"},
    )

    assert response.status_code == 401


def test_login_missing_email(client: FlaskClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"password": "123456"},
    )

    assert response.status_code == 400


def test_login_missing_password(client: FlaskClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@gl.com"},
    )

    assert response.status_code == 400


def test_login_empty_payload(client: FlaskClient) -> None:
    response = client.post("/api/auth/login", json={})

    assert response.status_code == 400


def test_api_requires_authentication(client: FlaskClient) -> None:
    response = client.get("/api/atendido/")

    assert response.status_code == 401


def test_api_accepts_authenticated_request(
    client: FlaskClient, auth_headers: dict[str, str]
) -> None:
    response = client.get("/api/atendido/", headers=auth_headers)

    assert response.status_code == 200
    payload = assert_success_response(response)
    data = payload.get("data")
    assert data is not None
    assert isinstance(data, dict)


# O setup inicial saiu com o multitenant (D4 do plano): o primeiro admin de cada
# NPJ é criado pela plataforma. As rotas não podem voltar por engano.
@pytest.mark.parametrize(
    ("metodo", "rota"),
    [("get", "/api/auth/needs-setup"), ("post", "/api/auth/setup-admin")],
)
def test_rotas_de_setup_nao_existem_mais(
    client: FlaskClient, clean_db: None, metodo: str, rota: str
) -> None:
    payload = {
        "email": "newadmin@test.com",
        "password": "securepass123",
        "setup_token": "qualquer",
    }
    response = getattr(client, metodo)(rota, json=payload)
    assert response.status_code == 404

    # Mesmo com o banco sem usuários, nenhuma conta nasce por esse caminho.
    login = client.post(
        "/api/auth/login",
        json={"email": "newadmin@test.com", "password": "securepass123"},
    )
    assert login.status_code == 401
