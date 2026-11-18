# ruff: noqa: F811
"""Contextos DJEN: permissão, validação, correspondência, prioridade manual e histórico."""

import pytest
from sqlalchemy import func, select

from gestaolegal.database.session import get_session
from gestaolegal.database.tables import djen_comunicacoes, djen_publicacoes
from gestaolegal.utils.request_context import contexto_tenant

from .conftest import TENANT_DAJ, UNIDADE_BH, get_success_data
from .test_djen_contextos import criar, listar, rotular
from .test_djen_exemplos import _linhas, buscar, djen, lote, transporte  # noqa: F401


def rotulo_de(client, headers, cid, id_djen=91001):
    return next(
        x for x in listar(client, headers, cid)["items"] if x["id_djen"] == id_djen
    )["rotulo"]


def test_estagiario_nao_acessa_contextos(
    client, auth_headers, estagiario_auth_headers, lote
):
    cid = criar(client, auth_headers)
    h = estagiario_auth_headers
    corpo = {"nome": "Contexto", "nomes": ["Fulana"], "tribunais": []}
    assert client.get("/api/djen/contextos", headers=h).status_code == 403
    assert client.post("/api/djen/contextos", headers=h, json=corpo).status_code == 403
    assert rotular(client, h, cid, "relevante").status_code == 403
    assert (
        client.post(
            f"/api/djen/contextos/{cid}/treinar", headers=h, json={}
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "corpo",
    [
        {"nome": "ab", "nomes": ["Fulana"], "tribunais": []},
        {"nome": "Nome ok", "nomes": [], "tribunais": []},
        {"nome": "Nome ok", "nomes": ["ab"], "tribunais": []},
        {"nome": "Nome ok", "nomes": "Fulana", "tribunais": []},
        {"nome": "Nome ok", "nomes": ["Fulana"], "tribunais": ["TJ MG; DROP"]},
        {"nome": "Nome ok", "nomes": ["Fulana"], "tribunais": "TJMG"},
    ],
)
def test_criacao_invalida_nao_grava(client, auth_headers, lote, corpo):
    resp = client.post("/api/djen/contextos", headers=auth_headers, json=corpo)
    assert resp.status_code == 400, resp.json
    assert client.get("/api/djen/contextos", headers=auth_headers).json["data"] == []


@pytest.mark.parametrize(
    "nomes, tribunais, total",
    [
        # Destinatário da fixture: "Fulana de Tal Fictícia", no TJMG.
        (["tal ficticia"], [], 2),
        (["FULÂNA DE TÁL"], [], 2),
        (["Fulana"], ["tjmg"], 2),
        (["Beltrano"], [], 0),
    ],
)
def test_correspondencia_ignora_acentos_e_caixa(
    client, auth_headers, lote, nomes, tribunais, total
):
    cid = criar(client, auth_headers, tribunais=tribunais, nomes=nomes)
    assert listar(client, auth_headers, cid)["total"] == total


def test_contexto_de_outra_unidade_no_corpo_recusa_o_lote(
    client, auth_headers, auth_headers_nl, lote
):
    a = criar(client, auth_headers)
    de_nova_lima = criar(client, auth_headers_nl, "Contexto de Nova Lima")
    resp = client.post(
        "/api/djen/acervo/descartar",
        headers=auth_headers,
        json={"ids": [91002], "contexto_ids": [a, de_nova_lima]},
    )
    assert resp.status_code == 404, resp.json
    assert rotulo_de(client, auth_headers, a, 91002) == "nao_classificado"
    with client.application.test_request_context(), contexto_tenant(TENANT_DAJ):
        descartadas = (
            get_session()
            .execute(
                select(func.count())
                .select_from(djen_comunicacoes)
                .where(
                    djen_comunicacoes.c.tenant_id == TENANT_DAJ,
                    djen_comunicacoes.c.situacao == "descartada",
                )
            )
            .scalar_one()
        )
    assert descartadas == 0


@pytest.mark.parametrize("contexto_ids", ["1", [True], ["1"], [1.5], {"a": 1}])
def test_contexto_ids_malformado(client, auth_headers, lote, contexto_ids):
    criar(client, auth_headers)
    resp = client.post(
        "/api/djen/acervo/descartar",
        headers=auth_headers,
        json={"ids": [91002], "contexto_ids": contexto_ids},
    )
    assert resp.status_code == 400, resp.json


def test_limpeza_manual_resiste_a_importacao(client, auth_headers, lote):
    a = criar(client, auth_headers)
    assert rotular(client, auth_headers, a, "relevante").status_code == 200
    assert rotular(client, auth_headers, a, "nao_classificado").status_code == 200
    resp = client.post(
        "/api/djen/busca-parte/importar",
        headers=auth_headers,
        json={"ids": [91001], "contexto_ids": [a]},
    )
    assert resp.status_code == 200, resp.json
    assert buscar(client, auth_headers).status_code == 200
    assert rotulo_de(client, auth_headers, a) == "nao_classificado"


def test_limpeza_manual_resiste_a_vinculo_automatico(client, auth_headers, lote):
    a = criar(client, auth_headers)
    assert rotular(client, auth_headers, a, "nao_classificado").status_code == 200
    # O processo da 91001 está cadastrado: a reconsulta vincula automaticamente.
    assert buscar(client, auth_headers).status_code == 200
    assert rotulo_de(client, auth_headers, a) == "nao_classificado"


def test_descarte_pela_rota_individual_nao_avalia_contextos(client, auth_headers, lote):
    a = criar(client, auth_headers)
    b = criar(client, auth_headers, "Segundo contexto")
    pid = _linhas(djen_publicacoes, id_djen=91002)[0]["id"]
    with client.application.test_request_context(), contexto_tenant(TENANT_DAJ):
        session = get_session()
        comunicacao = session.execute(
            djen_comunicacoes.insert().values(
                tenant_id=TENANT_DAJ,
                id_publicacao=pid,
                situacao="pendente",
                unidade_id=UNIDADE_BH,
            )
        ).lastrowid
        session.commit()
    resp = client.post(
        f"/api/djen/publicacoes/{comunicacao}/descartar", headers=auth_headers, json={}
    )
    assert resp.status_code == 200, resp.json
    assert _linhas(djen_comunicacoes, id=comunicacao)[0]["situacao"] == "descartada"
    for cid in (a, b):
        assert rotulo_de(client, auth_headers, cid, 91002) == "nao_classificado"


def test_historico_separado_por_contexto(client, auth_headers, lote):
    a = criar(client, auth_headers, "Contexto A")
    b = criar(client, auth_headers, "Contexto B")
    assert rotular(client, auth_headers, a, "relevante").status_code == 200
    assert rotular(client, auth_headers, b, "irrelevante").status_code == 200
    # Repetir a mesma avaliação não gera nova entrada.
    assert rotular(client, auth_headers, a, "relevante").status_code == 200
    pid = _linhas(djen_publicacoes, id_djen=91001)[0]["id"]
    detalhe = get_success_data(
        client.get(f"/api/djen/acervo/{pid}", headers=auth_headers)
    )
    historico = [
        h for h in detalhe["historico"] if h["contexto_nome"] != "Legado (sem contexto)"
    ]
    assert sorted(
        (h["contexto_nome"], h["rotulo_anterior"], h["rotulo"], h["origem"])
        for h in historico
    ) == [
        ("Contexto A", "nao_classificado", "relevante", "classificacao"),
        ("Contexto B", "nao_classificado", "irrelevante", "classificacao"),
    ]
    assert all(h["id_rotulado_por"] for h in historico)
