"""GET /api/ambiente: rota pública que diz ao front se o ambiente é de demonstração."""

from collections.abc import Generator

import pytest
from flask import Flask
from flask.testing import FlaskClient

from tests.api.conftest import get_success_data


@pytest.fixture
def demo_mode(app: Flask) -> Generator[None, None, None]:
    anterior = app.config.get("DEMO_MODE")
    app.config["DEMO_MODE"] = True
    yield
    app.config["DEMO_MODE"] = anterior


def test_ambiente_padrao_nao_e_demo(client: FlaskClient) -> None:
    resposta = client.get("/api/ambiente")
    assert resposta.status_code == 200
    assert get_success_data(resposta) == {"demo": False}


def test_ambiente_demo_ligado(client: FlaskClient, demo_mode: None) -> None:
    resposta = client.get("/api/ambiente")
    assert resposta.status_code == 200
    assert get_success_data(resposta) == {"demo": True}


def test_ambiente_dispensa_login(client: FlaskClient, demo_mode: None) -> None:
    # Sem Authorization e sem cookie: a tela de login consulta antes de autenticar.
    resposta = client.get("/api/ambiente", headers={})
    assert resposta.status_code == 200
