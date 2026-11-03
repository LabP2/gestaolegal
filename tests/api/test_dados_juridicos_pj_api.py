"""Requisitos da issue #114 e isolamento dos dados jurídicos de PJ."""

import json

import pytest
from sqlalchemy import select, update

from tests.api.conftest import get_success_data


@pytest.fixture(autouse=True)
def limpar_fichas_criadas():
    # A suíte compartilha o SQLite; remover só os registros criados por este teste
    # evita deixar fichas órfãs quando outros testes recriam os IDs dos atendidos.
    from gestaolegal.database.session import get_session
    from gestaolegal.database.tables import (
        assistidos,
        assistidos_pessoa_juridica,
        atendidos,
        enderecos,
    )

    tabelas = (assistidos_pessoa_juridica, assistidos, atendidos, enderecos)
    session = get_session()
    try:
        anteriores = {
            t.name: list(session.execute(select(t.c.id)).scalars()) for t in tabelas
        }
    finally:
        session.close()
    yield
    session = get_session()
    try:
        for tabela in tabelas:
            session.execute(
                tabela.delete().where(tabela.c.id.not_in(anteriores[tabela.name]))
            )
        session.commit()
    finally:
        session.close()


def criar_assistido(client, headers, atendido_data, assistido_data, pj):
    atendido = get_success_data(
        client.post(
            "/api/atendido/",
            json={**atendido_data, "pj_constituida": "sim"},
            headers=headers,
        )
    )
    response = client.post(
        f"/api/atendido/{atendido['id']}/tornar-assistido",
        json={**assistido_data, "assistido_pessoa_juridica": pj},
        headers=headers,
    )
    return atendido["id"], response


def test_pj_conversao_edicao_e_consulta(
    client, auth_headers, sample_atendido_data, sample_assistido_data
):
    pj = {
        "enquadramento": "microempresa",
        "socios": [" Ana ", "João"],
        "situacao_receita": "Ativa",
    }
    aid, response = criar_assistido(
        client, auth_headers, sample_atendido_data, sample_assistido_data, pj
    )
    assert response.status_code == 200
    dados = get_success_data(response)["assistido"]["assistido_pessoa_juridica"]
    assert dados["socios"] == ["Ana", "João"]
    assert dados["situacao_receita"] == "Ativa"
    response = client.put(
        f"/api/atendido/{aid}/assistido",
        headers=auth_headers,
        json={
            "assistido_pessoa_juridica": {
                "enquadramento": "outros",
                "socios": ["Maria"],
                "especificacao_enquadramento": " Associação ",
            }
        },
    )
    assert response.status_code == 200
    dados = get_success_data(client.get(f"/api/atendido/{aid}", headers=auth_headers))[
        "assistido"
    ]["assistido_pessoa_juridica"]
    assert dados["enquadramento"] == "outros"
    assert dados["especificacao_enquadramento"] == "Associação"
    assert dados["socios"] == ["Maria"]
    # Atualização comum não apaga os dados de PJ existentes.
    response = client.put(
        f"/api/atendido/{aid}/assistido",
        headers=auth_headers,
        json={"profissao": "Advogada"},
    )
    assert response.status_code == 200
    assert get_success_data(response)["assistido"]["assistido_pessoa_juridica"] == dados


def test_mudar_para_mei_limpa_socios_e_especificacao_no_banco(
    client, auth_headers, sample_atendido_data, sample_assistido_data
):
    from gestaolegal.database.session import get_session
    from gestaolegal.database.tables import assistidos_pessoa_juridica

    aid, response = criar_assistido(
        client,
        auth_headers,
        sample_atendido_data,
        sample_assistido_data,
        {
            "enquadramento": "outros",
            "socios": ["Ana"],
            "especificacao_enquadramento": "Associação",
        },
    )
    assert response.status_code == 200
    response = client.put(
        f"/api/atendido/{aid}/assistido",
        headers=auth_headers,
        json={
            "assistido_pessoa_juridica": {
                "enquadramento": "mei",
                "socios": ["Ana"],
                "especificacao_enquadramento": "Associação",
            }
        },
    )
    assert response.status_code == 200
    pj = get_success_data(response)["assistido"]["assistido_pessoa_juridica"]
    assert pj["socios"] == []
    assert pj["especificacao_enquadramento"] is None
    session = get_session()
    try:
        row = (
            session.execute(
                select(assistidos_pessoa_juridica).where(
                    assistidos_pessoa_juridica.c.id == pj["id"]
                )
            )
            .mappings()
            .one()
        )
        assert json.loads(row["socios"]) == []
        assert row["especificacao_enquadramento"] is None
    finally:
        session.close()
    # Ao sair de MEI, os nomes precisam ser informados novamente.
    response = client.put(
        f"/api/atendido/{aid}/assistido",
        headers=auth_headers,
        json={
            "assistido_pessoa_juridica": {"enquadramento": "microempresa", "socios": []}
        },
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "pj",
    [
        {"enquadramento": "outros", "socios": ["Ana"]},
        {
            "enquadramento": "outros",
            "especificacao_enquadramento": "   ",
            "socios": ["Ana"],
        },
        {"enquadramento": "microempresa", "socios": ["  "]},
        {"enquadramento": "microempresa", "socios": []},
        {"enquadramento": "pequeno_porte", "socios": ["A" * 81]},
        {"enquadramento": "microempresa", "socios": ["Ana"] * 21},
        {"enquadramento": "microempresa", "socios": ["A" * 80] * 20},
        {"enquadramento": "nao_se_aplica", "socios": ["Ana"]},
    ],
)
def test_pj_rejeita_dados_invalidos(
    client, auth_headers, sample_atendido_data, sample_assistido_data, pj
):
    aid, response = criar_assistido(
        client, auth_headers, sample_atendido_data, sample_assistido_data, pj
    )
    assert response.status_code == 400
    assert (
        get_success_data(client.get(f"/api/atendido/{aid}", headers=auth_headers))[
            "assistido"
        ]
        is None
    )


def test_pj_impede_gravacao_em_pessoa_fisica(
    client, auth_headers, sample_atendido_data, sample_assistido_data
):
    atendido = get_success_data(
        client.post("/api/atendido/", json=sample_atendido_data, headers=auth_headers)
    )
    response = client.post(
        f"/api/atendido/{atendido['id']}/tornar-assistido",
        headers=auth_headers,
        json={
            **sample_assistido_data,
            "assistido_pessoa_juridica": {"enquadramento": "mei"},
        },
    )
    assert response.status_code == 400
    assert (
        get_success_data(
            client.get(f"/api/atendido/{atendido['id']}", headers=auth_headers)
        )["assistido"]
        is None
    )


def test_pj_nao_pode_ser_lida_ou_alterada_por_outra_unidade(
    client, auth_headers, auth_headers_nl, sample_atendido_data, sample_assistido_data
):
    aid, response = criar_assistido(
        client,
        auth_headers,
        sample_atendido_data,
        sample_assistido_data,
        {"enquadramento": "microempresa", "socios": ["Ana"]},
    )
    assert response.status_code == 200
    assert (
        client.get(f"/api/atendido/{aid}", headers=auth_headers_nl).status_code == 404
    )
    assert (
        client.put(
            f"/api/atendido/{aid}/assistido",
            headers=auth_headers_nl,
            json={"assistido_pessoa_juridica": {"enquadramento": "mei"}},
        ).status_code
        == 404
    )
    dados = get_success_data(client.get(f"/api/atendido/{aid}", headers=auth_headers))
    assert dados["assistido"]["assistido_pessoa_juridica"]["socios"] == ["Ana"]


def test_pj_preserva_texto_e_campos_legados(
    client, auth_headers, sample_atendido_data, sample_assistido_data
):
    from gestaolegal.database.session import get_session
    from gestaolegal.database.tables import assistidos_pessoa_juridica as tabela

    aid, response = criar_assistido(
        client,
        auth_headers,
        sample_atendido_data,
        sample_assistido_data,
        {"enquadramento": "microempresa", "socios": ["Ana"]},
    )
    assert response.status_code == 200
    pj_id = get_success_data(response)["assistido"]["assistido_pessoa_juridica"]["id"]
    session = get_session()
    try:
        session.execute(
            update(tabela)
            .where(tabela.c.id == pj_id)
            .values(socios="Ana; João", area_atuacao="Educação")
        )
        session.commit()
    finally:
        session.close()
    dados = get_success_data(client.get(f"/api/atendido/{aid}", headers=auth_headers))[
        "assistido"
    ]["assistido_pessoa_juridica"]
    assert dados["socios"] == ["Ana; João"]
    assert dados["area_atuacao"] == "Educação"
    response = client.put(
        f"/api/atendido/{aid}/assistido",
        headers=auth_headers,
        json={"assistido_pessoa_juridica": {"enquadramento": "mei"}},
    )
    assert response.status_code == 200
    assert (
        get_success_data(response)["assistido"]["assistido_pessoa_juridica"][
            "area_atuacao"
        ]
        == "Educação"
    )


def test_falha_ao_gravar_pj_desfaz_conversao(
    client, auth_headers, sample_atendido_data, sample_assistido_data, monkeypatch
):
    from gestaolegal.repositories.atendido_repository import AtendidoRepository

    def falhar(*args, **kwargs):
        raise RuntimeError("Falha sintética na persistência de PJ")

    monkeypatch.setattr(AtendidoRepository, "salvar_pessoa_juridica", falhar)
    aid, response = criar_assistido(
        client,
        auth_headers,
        sample_atendido_data,
        sample_assistido_data,
        {"enquadramento": "mei"},
    )
    assert response.status_code == 500
    assert (
        get_success_data(client.get(f"/api/atendido/{aid}", headers=auth_headers))[
            "assistido"
        ]
        is None
    )


def test_falha_ao_gravar_pj_desfaz_edicao(
    client, auth_headers, sample_atendido_data, sample_assistido_data, monkeypatch
):
    from gestaolegal.repositories.atendido_repository import AtendidoRepository

    aid, response = criar_assistido(
        client,
        auth_headers,
        sample_atendido_data,
        sample_assistido_data,
        {"enquadramento": "microempresa", "socios": ["Ana"]},
    )
    assert response.status_code == 200
    original = get_success_data(response)

    def falhar(*args, **kwargs):
        raise RuntimeError("Falha sintética na persistência de PJ")

    monkeypatch.setattr(AtendidoRepository, "salvar_pessoa_juridica", falhar)
    response = client.put(
        f"/api/atendido/{aid}/assistido",
        headers=auth_headers,
        json={
            "nome": "Nome que não deve persistir",
            "profissao": "Profissão que não deve persistir",
            "assistido_pessoa_juridica": {"enquadramento": "mei"},
        },
    )
    assert response.status_code == 500
    assert (
        get_success_data(client.get(f"/api/atendido/{aid}", headers=auth_headers))
        == original
    )
