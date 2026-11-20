"""Ids referenciados no corpo precisam existir no NPJ.

Um id inexistente e um id de outro NPJ recebem a mesma resposta 400, com o
campo apontado (a recusa do id de outro NPJ está em test_tenant_vazamento.py).
Sem a conferência, o service gravava a referência solta.
"""

from typing import Any

import pytest
from flask.testing import FlaskClient

from .conftest import assert_error_response, get_success_data

INEXISTENTE = 987654


def _recusado(response, campo: str, mensagem: str) -> None:
    assert response.status_code == 400, (response.status_code, response.get_json())
    erro = assert_error_response(response)["error"]
    assert erro["message"] == mensagem
    assert erro["details"] == {"field": campo}


def _total(client: FlaskClient, url: str, headers: dict[str, str]) -> int:
    return get_success_data(client.get(url, headers=headers))["total"]


@pytest.fixture
def eu(client: FlaskClient, auth_headers: dict[str, str]) -> int:
    return get_success_data(client.get("/api/user/me", headers=auth_headers))["id"]


@pytest.fixture
def atendido(client: FlaskClient, auth_headers, sample_atendido_data) -> int:
    response = client.post("/api/atendido/", json=sample_atendido_data, headers=auth_headers)
    assert response.status_code == 201, response.get_json()
    return get_success_data(response)["id"]


@pytest.fixture
def caso(client: FlaskClient, auth_headers, eu: int, atendido: int) -> int:
    corpo = {
        "id_usuario_responsavel": eu,
        "area_direito": "civel",
        "situacao_deferimento": "deferido",
        "ids_clientes": [atendido],
    }
    response = client.post("/api/caso/", json=corpo, headers=auth_headers)
    assert response.status_code == 201, response.get_json()
    return get_success_data(response)["id"]


CAMPOS_DE_USUARIO = ["id_usuario_responsavel", "id_orientador", "id_estagiario", "id_colaborador"]


class TestCaso:
    def _corpo(self, eu: int, atendido: int, **troca: Any) -> dict[str, Any]:
        return {
            "id_usuario_responsavel": eu,
            "area_direito": "civel",
            "situacao_deferimento": "deferido",
            "ids_clientes": [atendido],
            **troca,
        }

    def test_ids_existentes_sao_aceitos(self, client, auth_headers, eu, atendido):
        corpo = self._corpo(eu, atendido, id_orientador=eu, id_estagiario=eu, id_colaborador=eu)
        response = client.post("/api/caso/", json=corpo, headers=auth_headers)
        assert response.status_code == 201, response.get_json()

    @pytest.mark.parametrize("campo", CAMPOS_DE_USUARIO)
    def test_criar_com_usuario_inexistente(self, client, auth_headers, eu, atendido, campo):
        antes = _total(client, "/api/caso/", auth_headers)
        corpo = self._corpo(eu, atendido, **{campo: INEXISTENTE})
        response = client.post("/api/caso/", json=corpo, headers=auth_headers)
        _recusado(response, campo, "Usuário não encontrado")
        assert _total(client, "/api/caso/", auth_headers) == antes

    def test_criar_com_cliente_inexistente(self, client, auth_headers, eu, atendido):
        antes = _total(client, "/api/caso/", auth_headers)
        corpo = self._corpo(eu, atendido, ids_clientes=[atendido, INEXISTENTE])
        response = client.post("/api/caso/", json=corpo, headers=auth_headers)
        _recusado(response, "ids_clientes", "Atendido não encontrado")
        assert _total(client, "/api/caso/", auth_headers) == antes

    @pytest.mark.parametrize("campo", CAMPOS_DE_USUARIO)
    def test_editar_com_usuario_inexistente(self, client, auth_headers, caso, eu, campo):
        response = client.put(f"/api/caso/{caso}", json={campo: INEXISTENTE}, headers=auth_headers)
        _recusado(response, campo, "Usuário não encontrado")
        depois = get_success_data(client.get(f"/api/caso/{caso}", headers=auth_headers))
        assert depois[campo] in (None, eu)

    def test_editar_com_cliente_inexistente(self, client, auth_headers, caso, atendido):
        response = client.put(
            f"/api/caso/{caso}", json={"ids_clientes": [INEXISTENTE]}, headers=auth_headers
        )
        _recusado(response, "ids_clientes", "Atendido não encontrado")
        depois = get_success_data(client.get(f"/api/caso/{caso}", headers=auth_headers))
        assert [c["id"] for c in depois["clientes"]] == [atendido]


class TestOrientacao:
    def test_criar_com_atendido_inexistente(self, client, auth_headers, sample_orientacao_data, atendido):
        antes = _total(client, "/api/orientacao_juridica/", auth_headers)
        corpo = {**sample_orientacao_data, "atendidos_ids": [atendido, INEXISTENTE]}
        response = client.post("/api/orientacao_juridica/", json=corpo, headers=auth_headers)
        _recusado(response, "atendidos_ids", "Atendido não encontrado")
        assert _total(client, "/api/orientacao_juridica/", auth_headers) == antes

    def test_editar_com_atendido_inexistente(self, client, auth_headers, sample_orientacao_data, atendido):
        corpo = {**sample_orientacao_data, "atendidos_ids": [atendido]}
        criada = get_success_data(client.post("/api/orientacao_juridica/", json=corpo, headers=auth_headers))
        response = client.put(
            f"/api/orientacao_juridica/{criada['id']}",
            json={"atendidos_ids": [INEXISTENTE]},
            headers=auth_headers,
        )
        _recusado(response, "atendidos_ids", "Atendido não encontrado")


class TestFila:
    def test_criar_com_atendido_inexistente(self, client, auth_headers):
        response = client.post(
            "/api/fila_atendimento/",
            json={"id_atendido": INEXISTENTE, "prioridade": 0, "psicologia": False},
            headers=auth_headers,
        )
        _recusado(response, "id_atendido", "Atendido não encontrado")


class TestLembrete:
    def _corpo(self, id_usuario: int) -> dict[str, Any]:
        return {"id_usuario": id_usuario, "data_lembrete": "2026-09-15T00:00:00", "descricao": "Lembrete"}

    def test_criar_com_usuario_inexistente(self, client, auth_headers, caso):
        response = client.post(
            f"/api/caso/{caso}/lembretes", json=self._corpo(INEXISTENTE), headers=auth_headers
        )
        _recusado(response, "id_usuario", "Usuário não encontrado")
        lista = get_success_data(client.get(f"/api/caso/{caso}/lembretes", headers=auth_headers))
        assert lista == []

    def test_editar_com_usuario_inexistente(self, client, auth_headers, caso, eu):
        criado = client.post(f"/api/caso/{caso}/lembretes", json=self._corpo(eu), headers=auth_headers)
        assert criado.status_code == 201, criado.get_json()
        lembrete = get_success_data(criado)["id"]
        response = client.put(
            f"/api/caso/{caso}/lembretes/{lembrete}",
            json={"id_usuario": INEXISTENTE},
            headers=auth_headers,
        )
        _recusado(response, "id_usuario", "Usuário não encontrado")


class TestEvento:
    def _form(self, **extra: Any) -> dict[str, Any]:
        return {"tipo": "Audiência", "data_evento": "2026-06-20", "descricao": "Evento", **extra}

    def test_criar_com_responsavel_inexistente(self, client, auth_headers, caso):
        response = client.post(
            f"/api/caso/{caso}/eventos",
            data=self._form(id_usuario_responsavel=str(INEXISTENTE)),
            content_type="multipart/form-data",
            headers=auth_headers,
        )
        _recusado(response, "id_usuario_responsavel", "Usuário não encontrado")

    def test_editar_com_responsavel_inexistente(self, client, auth_headers, caso, eu):
        criado = client.post(
            f"/api/caso/{caso}/eventos",
            data=self._form(id_usuario_responsavel=str(eu)),
            content_type="multipart/form-data",
            headers=auth_headers,
        )
        assert criado.status_code == 201, criado.get_json()
        evento = get_success_data(criado)["id"]
        response = client.put(
            f"/api/caso/{caso}/eventos/{evento}",
            data={"id_usuario_responsavel": str(INEXISTENTE)},
            content_type="multipart/form-data",
            headers=auth_headers,
        )
        _recusado(response, "id_usuario_responsavel", "Usuário não encontrado")


class TestProcesso:
    def test_editar_movendo_para_caso_inexistente(self, client, auth_headers, caso):
        criado = client.post(
            f"/api/caso/{caso}/processos",
            json={"especie": "Ação", "numero": "7770001", "status": True},
            headers=auth_headers,
        )
        assert criado.status_code == 201, criado.get_json()
        processo = get_success_data(criado)["id"]
        response = client.put(
            f"/api/caso/{caso}/processos/{processo}",
            json={"id_caso": INEXISTENTE},
            headers=auth_headers,
        )
        _recusado(response, "id_caso", "Caso não encontrado")
        depois = get_success_data(
            client.get(f"/api/caso/{caso}/processos/{processo}", headers=auth_headers)
        )
        assert depois["id_caso"] == caso
