# ruff: noqa: F811
"""Contextos DJEN: portas do treino, holdout por CNJ, versões e sugestões."""

from datetime import date, datetime

import pytest
from sqlalchemy import func, select

from gestaolegal.database.session import get_session
from gestaolegal.database.tables import (
    djen_modelos,
    djen_publicacao_contextos,
    djen_publicacoes,
)
from gestaolegal.repositories.djen_acervo_repository import DjenAcervoRepository
from gestaolegal.services.djen_contexto_service import DjenContextoService
from gestaolegal.utils.request_context import contexto_tenant

from .conftest import TENANT_DAJ, UNIDADE_BH, get_success_data
from .test_djen_contextos import criar
from .test_djen_exemplos import djen, transporte  # noqa: F401

TEXTO_RELEVANTE = "assistencia estudantil bolsa permanencia"
TEXTO_IRRELEVANTE = "licitacao contrato fornecedor"


def cnj(n):
    return f"{n:020d}"


def semear(app, cid, total, relevante, processo, texto=None, base=800000, rotular=True):
    """Grava publicações sintéticas no contexto; devolve os IDs do acervo.

    `relevante(i)`, `processo(i)` e `texto(i)` definem classe, CNJ e texto.
    """
    pids = []
    with app.test_request_context(), contexto_tenant(TENANT_DAJ):
        for i in range(total):
            positivo = relevante(i)
            padrao = TEXTO_RELEVANTE if positivo else TEXTO_IRRELEVANTE
            pid = DjenAcervoRepository().guardar(
                {
                    "id_djen": base + i,
                    "numero_processo": processo(i),
                    "data_disponibilizacao": date(2026, 11, 1),
                    "texto_plano": texto(i) if texto else padrao,
                    "destinatarios": [{"nome": "Fulana de Tal"}],
                    "sigla_tribunal": "TJMG",
                    "capturada_em": datetime.now(),
                    "ativo": True,
                }
            )
            DjenAcervoRepository().dar_acesso(pid, UNIDADE_BH, "parte")
            if rotular:
                DjenContextoService().rotular(
                    pid,
                    cid,
                    "relevante" if positivo else "irrelevante",
                    "classificacao",
                    None,
                )
            pids.append(pid)
        get_session().commit()
    return pids


def treinar(client, headers, cid):
    response = client.post(
        f"/api/djen/contextos/{cid}/treinar", headers=headers, json={}
    )
    assert response.status_code == 202, response.json
    token = get_success_data(response)["treino_token"]
    with client.application.test_request_context(), contexto_tenant(TENANT_DAJ):
        service = DjenContextoService()
        resultado = service.executar_treino(cid, UNIDADE_BH, token)
        while service.processar_previsoes(cid, UNIDADE_BH):
            pass
        return resultado


def acervo(client, headers, **filtros):
    resp = client.get("/api/djen/acervo", headers=headers, query_string=filtros)
    assert resp.status_code == 200, resp.json
    return get_success_data(resp)


def total_de_modelos(app):
    with app.test_request_context(), contexto_tenant(TENANT_DAJ):
        return (
            get_session()
            .execute(
                select(func.count())
                .select_from(djen_modelos)
                .where(djen_modelos.c.tenant_id == TENANT_DAJ)
            )
            .scalar_one()
        )


def relacoes_do_contexto(app, cid):
    t = djen_publicacao_contextos
    with app.test_request_context(), contexto_tenant(TENANT_DAJ):
        linhas = get_session().execute(
            select(t).where(t.c.tenant_id == TENANT_DAJ, t.c.contexto_id == cid)
        )
        return {x["id_publicacao"]: dict(x) for x in linhas.mappings()}


@pytest.mark.parametrize(
    "relevante, processo, texto",
    [
        # Só 40 exemplos de uma das classes.
        (lambda i: i < 40, cnj, None),
        # Menos de 10 processos distintos.
        (lambda i: i % 2 == 0, lambda i: cnj(i % 9), None),
        # Uma classe inteira num único processo: a divisão fica sem as duas.
        (lambda i: i >= 60, lambda i: cnj(0 if i < 60 else 1 + i % 20), None),
        # Rótulos suficientes, mas sem texto para aprender.
        (lambda i: i % 2 == 0, lambda i: cnj(i // 4), lambda i: ""),
    ],
    ids=["classe_minoritaria", "poucos_processos", "divisao_sem_classes", "sem_texto"],
)
def test_treino_recusado_nao_grava_modelo(
    app, client, auth_headers, djen, relevante, processo, texto
):
    cid = criar(client, auth_headers)
    semear(app, cid, 220, relevante, processo, texto)
    resp = client.post(
        f"/api/djen/contextos/{cid}/treinar", headers=auth_headers, json={}
    )
    if (
        min(sum(relevante(i) == classe for i in range(220)) for classe in (True, False))
        < 50
    ):  # recusa antes da fila
        assert resp.status_code == 400, resp.json
    else:
        assert resp.status_code == 202, resp.json
        with app.test_request_context(), contexto_tenant(TENANT_DAJ):
            servico = DjenContextoService()
            assert (
                servico.executar_treino(
                    cid, UNIDADE_BH, get_success_data(resp)["treino_token"]
                )
                is None
            )
            estado = servico.obter(cid, UNIDADE_BH)
            assert estado["treino_status"] == "erro"
            assert estado["treino_erro"]
    assert total_de_modelos(app) == 0


def test_holdout_separa_por_processo(app, client, auth_headers, djen):
    cid = criar(client, auth_headers)
    pids = semear(app, cid, 240, lambda i: i % 2 == 0, lambda i: cnj(i // 4))
    metricas = treinar(client, auth_headers, cid)["metricas"]
    assert metricas["treino"] + metricas["teste"] == metricas["total"] == 240
    assert len(metricas["amostra"]) == 240
    with app.test_request_context(), contexto_tenant(TENANT_DAJ):
        processos = dict(
            get_session()
            .execute(
                select(djen_publicacoes.c.id, djen_publicacoes.c.numero_processo).where(
                    djen_publicacoes.c.tenant_id == TENANT_DAJ
                )
            )
            .all()
        )
    no_teste = {processos[i] for i in metricas["ids_teste"]}
    no_treino = {processos[i] for i in pids if i not in metricas["ids_teste"]}
    assert no_teste and no_treino
    assert not no_teste & no_treino


def test_retreino_preserva_versao_e_texto_vazio_fica_sem_sugestao(
    app, client, auth_headers, djen
):
    cid = criar(client, auth_headers)
    rotuladas = semear(app, cid, 240, lambda i: i % 2 == 0, lambda i: cnj(i // 4))
    com_texto, sem_texto = semear(
        app,
        cid,
        2,
        lambda i: True,
        lambda i: cnj(900 + i),
        texto=lambda i: "" if i else "bolsa permanencia",
        base=810000,
        rotular=False,
    )
    primeiro = treinar(client, auth_headers, cid)
    acervo(client, auth_headers, contexto_id=cid, rotulo="nao_classificado")
    relacoes = relacoes_do_contexto(app, cid)
    assert relacoes[com_texto]["sugestao"] == "relevante"
    assert relacoes[com_texto]["modelo_id"] == primeiro["id"]
    assert relacoes[com_texto]["rotulo"] == "nao_classificado"
    assert relacoes[sem_texto]["sugestao"] is None
    assert relacoes[sem_texto]["modelo_id"] == primeiro["id"]
    # Publicação já avaliada não recebe sugestão.
    assert all(relacoes[p]["sugestao"] is None for p in rotuladas)

    segundo = treinar(client, auth_headers, cid)
    assert segundo["id"] != primeiro["id"]
    assert total_de_modelos(app) == 2
    sem_sugestao = acervo(
        client,
        auth_headers,
        contexto_id=cid,
        rotulo="nao_classificado",
        sugestao="sem_sugestao",
    )
    assert [x["id"] for x in sem_sugestao["items"]] == [sem_texto]
    assert relacoes_do_contexto(app, cid)[com_texto]["modelo_id"] == segundo["id"]
    listado = client.get("/api/djen/contextos", headers=auth_headers).json["data"][0]
    assert listado["modelo"]["id"] == segundo["id"]
    assert not {"amostra", "ids_teste"} & set(listado["modelo"]["metricas"])


def test_sugestoes_divergentes_em_uma_unica_linha(app, client, auth_headers, djen):
    a = criar(client, auth_headers, "Contexto A")
    b = criar(client, auth_headers, "Contexto B")
    semear(app, a, 240, lambda i: i % 2 == 0, lambda i: cnj(i // 4))
    # O contexto B recebe as avaliações opostas às do A.
    with app.test_request_context(), contexto_tenant(TENANT_DAJ):
        for pid, relacao in relacoes_do_contexto(app, a).items():
            oposto = "irrelevante" if relacao["rotulo"] == "relevante" else "relevante"
            DjenContextoService().rotular(pid, b, oposto, "classificacao", None)
        get_session().commit()
    (nova,) = semear(
        app, a, 1, lambda i: True, lambda i: cnj(950), base=820000, rotular=False
    )
    assert treinar(client, auth_headers, a)["id"] > 0
    assert treinar(client, auth_headers, b)["id"] > 0

    itens = acervo(client, auth_headers, rotulo="nao_classificado", per_page=100)[
        "items"
    ]
    linhas = [x for x in itens if x["id"] == nova]
    assert len(linhas) == 1
    assert {c["nome"]: c["sugestao"] for c in linhas[0]["contextos"]} == {
        "Contexto A": "relevante",
        "Contexto B": "irrelevante",
    }
    assert all(c["rotulo"] == "nao_classificado" for c in linhas[0]["contextos"])
    # Sem contexto selecionado, a publicação atende aos dois filtros de sugestão.
    for sugestao in ("relevante", "irrelevante"):
        filtrado = acervo(client, auth_headers, sugestao=sugestao, per_page=100)
        assert nova in [x["id"] for x in filtrado["items"]], sugestao
