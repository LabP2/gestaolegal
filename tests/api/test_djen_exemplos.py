"""Acervo e classificação: decisões persistentes, importação e isolamento."""

import json
from urllib.parse import parse_qs, urlparse

import pytest
from gestaolegal.database.tables import (
    djen_publicacoes,
    djen_classificacoes,
    djen_classificacao_historico,
    djen_consultas,
    djen_consulta_resultados,
    djen_comunicacoes,
    eventos,
)
from gestaolegal.integrations.djen_client import DJENError
from gestaolegal.utils.request_context import contexto_tenant
from .conftest import TENANT_DAJ, TENANT_OUTRO, get_success_data
from .djen_fixtures import item_djen, resposta, ligar_djen
from .test_djen_api import (  # noqa: F401 - fixtures compartilhadas
    _linhas,
    criar_caso,
    criar_processo,
    djen,
    headers_outro,
    numero_cnj_novo,
    transporte,
)

PERIODO = {"de": "2026-11-01", "ate": "2026-11-20"}


def buscar(client, headers, nome="Parte Teste"):
    return client.get(
        "/api/djen/busca-parte", query_string={"nome": nome, **PERIODO}, headers=headers
    )


def rotulos():
    pubs = {p["id"]: p["id_djen"] for p in _linhas(djen_publicacoes)}
    return {pubs[c["id_publicacao"]]: c["rotulo"] for c in _linhas(djen_classificacoes)}


def classificar(client, headers, ids, rotulo):
    return client.post(
        "/api/djen/acervo/classificar",
        json={"ids": ids, "rotulo": rotulo},
        headers=headers,
    )


@pytest.fixture
def lote(client, auth_headers, djen, transporte):
    # Captura anterior ao cadastro: o acervo fica disponível para trabalhar depois.
    numero = numero_cnj_novo()
    transporte.por_parte["Parte Teste"] = [
        item_djen(91001, numero),
        item_djen(91002, numero_cnj_novo()),
    ]
    r = buscar(client, auth_headers)
    assert r.status_code == 200, r.json
    return criar_processo(client, auth_headers, criar_caso(client, auth_headers), numero)


def test_busca_salva_tudo_sem_importar(client, auth_headers, lote):
    assert rotulos() == {91001: "nao_classificado", 91002: "nao_classificado"}
    assert len(_linhas(djen_publicacoes)) == 2
    assert _linhas(djen_comunicacoes) == []
    assert len(_linhas(djen_consulta_resultados)) == 2
    assert _linhas(djen_consultas)[0]["status"] == "ok"
    r = client.get("/api/djen/acervo", headers=auth_headers)
    assert r.status_code == 200, r.json
    dados = get_success_data(r)
    assert dados["total"] == 2
    assert all("texto_html" not in i and "texto_plano" not in i for i in dados["items"])


def test_classifica_sem_vincular_e_reconsulta_preserva(client, auth_headers, lote):
    assert classificar(client, auth_headers, [91001], "relevante").status_code == 200
    assert classificar(client, auth_headers, [91002], "irrelevante").status_code == 200
    historico = _linhas(djen_classificacao_historico)
    assert buscar(client, auth_headers).status_code == 200
    assert rotulos() == {91001: "relevante", 91002: "irrelevante"}
    assert len(_linhas(djen_publicacoes)) == 2
    assert len(_linhas(djen_comunicacoes)) == 1
    assert _linhas(djen_comunicacoes)[0]["situacao"] == "vinculada"
    assert _linhas(djen_classificacao_historico) == historico
    assert len(_linhas(djen_consultas)) == 2


def test_importar_salvo_sem_rede_classifica_so_selecionada(
    client, auth_headers, lote, transporte
):
    transporte.falhar.add("Parte Teste")
    chamadas = len(transporte.chamadas)
    r = client.post(
        "/api/djen/busca-parte/importar", json={"ids": [91001]}, headers=auth_headers
    )
    assert r.status_code == 200, r.json
    assert len(transporte.chamadas) == chamadas
    assert rotulos() == {91001: "relevante", 91002: "nao_classificado"}
    assert len(_linhas(djen_comunicacoes)) == 1
    operacional = _linhas(djen_comunicacoes)[0]
    pid = _linhas(djen_publicacoes, id_djen=91001)[0]["id"]
    detalhe = get_success_data(client.get(f"/api/djen/acervo/{pid}", headers=auth_headers))
    assert detalhe["situacao"] == "vinculada"
    assert detalhe["comunicacao_id"] == operacional["id"]
    assert detalhe["id_processo"] == operacional["id_processo"]
    assert detalhe["id_caso"] == operacional["id_caso"]
    assert len(_linhas(eventos, origem="djen")) == 1
    r = client.post(
        "/api/djen/busca-parte/importar", json={"ids": [91001]}, headers=auth_headers
    )
    assert r.status_code == 200, r.json
    assert len(_linhas(eventos, origem="djen")) == 1


def test_importacao_falha_nao_classifica(client, auth_headers, lote):
    r = client.post(
        "/api/djen/busca-parte/importar",
        json={"ids": [91001, 91002]},
        headers=auth_headers,
    )
    assert r.status_code == 400
    assert all(x == "nao_classificado" for x in rotulos().values())
    assert _linhas(djen_comunicacoes) == []


def test_descartar_preserva_apos_reconsulta_e_pode_importar(client, auth_headers, lote):
    r = client.post(
        "/api/djen/acervo/descartar", json={"ids": [91001]}, headers=auth_headers
    )
    assert r.status_code == 200, r.json
    assert rotulos()[91001] == "irrelevante"
    assert buscar(client, auth_headers).status_code == 200
    assert _linhas(djen_comunicacoes)[0]["situacao"] == "descartada"
    r = client.post(
        "/api/djen/busca-parte/importar", json={"ids": [91001]}, headers=auth_headers
    )
    assert r.status_code == 200, r.json
    assert rotulos()[91001] == "relevante"
    assert _linhas(djen_comunicacoes)[0]["situacao"] == "vinculada"


def test_treino_nao_desfaz_importacao(client, auth_headers, lote):
    assert (
        client.post(
            "/api/djen/busca-parte/importar",
            json={"ids": [91001]},
            headers=auth_headers,
        ).status_code
        == 200
    )
    assert classificar(client, auth_headers, [91001], "irrelevante").status_code == 200
    assert buscar(client, auth_headers).status_code == 200
    assert rotulos()[91001] == "irrelevante"
    assert _linhas(djen_comunicacoes)[0]["situacao"] == "vinculada"


def test_limpar_rotulo_mantem_historico(client, auth_headers, lote):
    assert classificar(client, auth_headers, [91001], "irrelevante").status_code == 200
    assert (
        classificar(client, auth_headers, [91001], "nao_classificado").status_code
        == 200
    )
    pid = _linhas(djen_publicacoes, id_djen=91001)[0]["id"]
    r = client.get(f"/api/djen/acervo/{pid}", headers=auth_headers)
    assert r.status_code == 200, r.json
    d = get_success_data(r)
    assert d["rotulo"] == "nao_classificado"
    assert d["situacao"] == "nao_importada"
    assert d["comunicacao_id"] is None
    assert d["id_processo"] is None
    assert d["id_caso"] is None
    assert len(d["historico"]) == 2
    assert "<script" not in d["texto_plano"]
    assert "texto_html" not in d
    assert d["link"] == "https://tribunal.exemplo.invalid/documento/91001"
    assert d["link_certidao"].endswith("/api/v1/comunicacao/hashficticio91001/certidao")


@pytest.mark.parametrize(
    "ids,rotulo",
    [
        ([], "relevante"),
        ([True], "relevante"),
        ([91001], "invalido"),
        ([91001, 99999], "relevante"),
    ],
)
def test_validacao_lote_atomico(client, auth_headers, lote, ids, rotulo):
    assert classificar(client, auth_headers, ids, rotulo).status_code == 400
    assert all(x == "nao_classificado" for x in rotulos().values())


def test_filtros_paginacao(client, auth_headers, lote):
    assert classificar(client, auth_headers, [91001], "relevante").status_code == 200
    r = client.get("/api/djen/acervo?rotulo=relevante&per_page=1", headers=auth_headers)
    assert r.status_code == 200, r.json
    assert get_success_data(r)["total"] == 1
    assert get_success_data(r)["items"][0]["id_djen"] == 91001
    r = client.get(
        "/api/djen/acervo?rotulo=relevante&page=2&per_page=1", headers=auth_headers
    )
    assert get_success_data(r)["total"] == 1 and get_success_data(r)["items"] == []


def test_isolamento_npjs(client, app, auth_headers, headers_outro, lote):
    with app.app_context():
        ligar_djen(TENANT_OUTRO)
    pid = _linhas(djen_publicacoes, id_djen=91001)[0]["id"]
    assert (
        client.get(f"/api/djen/acervo/{pid}", headers=headers_outro).status_code == 404
    )
    assert classificar(client, headers_outro, [91001], "relevante").status_code == 400
    assert (
        get_success_data(client.get("/api/djen/acervo", headers=headers_outro))["total"]
        == 0
    )
    assert buscar(client, headers_outro).status_code == 200
    assert len(_linhas(djen_publicacoes, id_djen=91001)) == 2
    assert classificar(client, headers_outro, [91001], "irrelevante").status_code == 200
    assert (
        get_success_data(client.get(f"/api/djen/acervo/{pid}", headers=auth_headers))[
            "rotulo"
        ]
        == "nao_classificado"
    )


def test_exportacao_so_classificados(client, auth_headers, lote):
    assert classificar(client, auth_headers, [91001], "irrelevante").status_code == 200
    r = client.get("/api/djen/exemplos/exportar", headers=auth_headers)
    assert r.status_code == 200, r.data
    linhas = [json.loads(x) for x in r.data.decode().splitlines()]
    assert len(linhas) == 1 and linhas[0]["rotulo"] == "irrelevante"
    assert linhas[0]["origem"] == "classificacao"


def test_retencao_preserva_acervo(client, app, auth_headers, lote):
    from gestaolegal.services.djen_service import DJENService

    with app.test_request_context(), contexto_tenant(TENANT_DAJ):
        assert DJENService()._aplicar_retencao() == 0
    assert len(_linhas(djen_publicacoes)) == 2


def test_falha_pagina_preserva_recebidas(client, auth_headers, djen, transporte):
    itens = [item_djen(92000 + i, numero_cnj_novo()) for i in range(100)]

    def responder(url, timeout):
        if parse_qs(urlparse(url).query)["pagina"] == ["1"]:
            return resposta(itens, count=200)
        raise DJENError("Falha sintética na segunda página")

    from gestaolegal.integrations import djen_client

    djen_client.definir_transporte(responder)
    r = buscar(client, auth_headers)
    assert r.status_code != 200
    assert len(_linhas(djen_publicacoes)) == 100
    assert len(_linhas(djen_consulta_resultados)) == 100
    assert _linhas(djen_consultas)[0]["status"] == "erro"
    transporte.por_parte["Parte Teste"] = itens
    djen_client.definir_transporte(transporte)
    assert buscar(client, auth_headers).status_code == 200
    assert len(_linhas(djen_publicacoes)) == 100


def test_unidade_nao_acessa_resultado_da_outra(client, auth_headers_nl, lote):
    pid = _linhas(djen_publicacoes, id_djen=91001)[0]["id"]
    assert (
        client.get(f"/api/djen/acervo/{pid}", headers=auth_headers_nl).status_code
        == 404
    )
    assert classificar(client, auth_headers_nl, [91001], "relevante").status_code == 400
    assert (
        get_success_data(client.get("/api/djen/acervo", headers=auth_headers_nl))[
            "total"
        ]
        == 0
    )


def test_descarte_em_lote_nao_altera_vinculada(client, auth_headers, lote):
    assert (
        client.post(
            "/api/djen/busca-parte/importar",
            json={"ids": [91001]},
            headers=auth_headers,
        ).status_code
        == 200
    )
    r = client.post(
        "/api/djen/acervo/descartar", json={"ids": [91001, 91002]}, headers=auth_headers
    )
    assert r.status_code == 400
    assert rotulos() == {91001: "relevante", 91002: "nao_classificado"}


def test_rotina_vincula_sem_alterar_classificacao_humana(
    client, app, auth_headers, lote, transporte
):
    assert classificar(client, auth_headers, [91001], "irrelevante").status_code == 200
    transporte.por_processo[lote["numero_cnj"]] = [item_djen(91001, lote["numero_cnj"])]
    r = client.post(f"/api/processos/{lote['id']}/djen/buscar", headers=auth_headers)
    assert r.status_code == 200, r.json
    assert get_success_data(r)["vinculadas"] == 1
    assert len(_linhas(djen_comunicacoes)) == 1
    assert _linhas(djen_comunicacoes)[0]["situacao"] == "vinculada"
    assert rotulos()[91001] == "irrelevante"


@pytest.mark.parametrize('filtros,ids', [
    ({'nome_parte': 'maria teste'}, [99101]),
    ({'nome_parte': 'nome só no texto'}, []),
    ({'nome_parte': '%'}, []),
    ({'oab': '123.456/MG'}, [99101]),
    ({'oab': '123456'}, [99101, 99102]),
    ({'oab': 'MG123456'}, [99101]),
    ({'oab': '123456/RJ'}, []),
    ({'numero_processo': '0000001-11.2026.8.13.0001'}, [99101]),
    ({'numero_processo': '00000011120268130001', 'oab': '123456/SP'}, []),
    ({'nome_parte': 'maria', 'oab': '123456/MG', 'numero_processo': '00000011120268130001'}, [99101]),
])
def test_filtros_identificacao_acervo(client, auth_headers, djen, transporte, filtros, ids):
    primeiro=item_djen(99101,'00000011120268130001',texto='Nome só no texto',oab=('123456','MG'))
    primeiro['destinatarios']=[{'nome':'MARIA TESTE','polo':'A'}]
    segundo=item_djen(99102,'00000021120268130001',oab=('123456','SP'))
    segundo['destinatarios']=[{'nome':'JOAO TESTE','polo':'A'}]
    # Número e UF precisam pertencer ao MESMO advogado.
    segundo['destinatarioadvogados'].append({'advogado':{'nome':'Outro advogado','numero_oab':'999999','uf_oab':'RJ'}})
    transporte.por_parte['Parte Teste']=[primeiro,segundo]
    assert buscar(client,auth_headers).status_code==200
    r=client.get('/api/djen/acervo',headers=auth_headers,query_string=filtros)
    assert r.status_code==200,r.json
    assert sorted(item['id_djen'] for item in r.json['data']['items'])==ids
    assert r.json['data']['total']==len(ids)
