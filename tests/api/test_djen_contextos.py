# ruff: noqa: F811
"""Rótulos por contexto, escolhas operacionais e modelos isolados."""

from datetime import datetime, date
from gestaolegal.database.session import get_session
from gestaolegal.utils.request_context import contexto_tenant
from .conftest import TENANT_DAJ, get_success_data
from .test_djen_exemplos import lote, djen, transporte, headers_outro, buscar  # noqa: F401, F811


def criar(client, headers, nome="Parte teste", tribunais=None, nomes=None):
    resp = client.post(
        "/api/djen/contextos",
        headers=headers,
        json=dict(
            nome=nome, nomes=nomes or ["Fulana de Tal"], tribunais=tribunais or []
        ),
    )
    assert resp.status_code == 200, resp.json
    return get_success_data(resp)["id"]


def listar(client, headers, cid):
    resp = client.get(
        "/api/djen/acervo", headers=headers, query_string={"contexto_id": cid}
    )
    assert resp.status_code == 200, resp.json
    return get_success_data(resp)


def rotular(client, headers, cid, rotulo, ids=None):
    return client.post(
        f"/api/djen/contextos/{cid}/classificar",
        headers=headers,
        json={"ids": ids or [91001], "rotulo": rotulo},
    )


def test_contextos_independentes_e_filtros(client, auth_headers, lote):
    a = criar(client, auth_headers)
    b = criar(client, auth_headers, "Outra finalidade")
    c = criar(client, auth_headers, "Outro tribunal", ["TRF6"])
    assert listar(client, auth_headers, c)["total"] == 0
    assert listar(client, auth_headers, a)["total"] == 2
    assert rotular(client, auth_headers, a, "relevante").status_code == 200
    assert rotular(client, auth_headers, b, "irrelevante").status_code == 200
    assert {
        x["id_djen"]: x["rotulo"] for x in listar(client, auth_headers, a)["items"]
    } == {91001: "relevante", 91002: "nao_classificado"}
    labels = {
        x["id_djen"]: x["rotulo"] for x in listar(client, auth_headers, b)["items"]
    }
    assert labels[91001] == "irrelevante"
    assert rotular(client, auth_headers, c, "relevante").status_code == 400


def test_automatico_preserva_manual_e_contexto_criado_depois(
    client, auth_headers, lote
):
    a = criar(client, auth_headers)
    assert rotular(client, auth_headers, a, "irrelevante").status_code == 200
    assert (
        buscar(client, auth_headers).status_code == 200
    )  # processo existente: vínculo automático
    b = criar(client, auth_headers, "Contexto posterior")

    def label(cid):
        return next(
            x
            for x in listar(client, auth_headers, cid)["items"]
            if x["id_djen"] == 91001
        )["rotulo"]

    assert label(a) == "irrelevante"
    assert label(b) == "relevante"


def test_descarte_apenas_contextos_escolhidos(client, auth_headers, lote):
    a = criar(client, auth_headers)
    b = criar(client, auth_headers, "Outro contexto")
    body = {"ids": [91002]}
    assert (
        client.post(
            "/api/djen/acervo/descartar", headers=auth_headers, json=body
        ).status_code
        == 400
    )
    body["contexto_ids"] = [a]
    resp = client.post("/api/djen/acervo/descartar", headers=auth_headers, json=body)
    assert resp.status_code == 200, resp.json
    assert buscar(client, auth_headers).status_code == 200
    for cid, esperado in [(a, "irrelevante"), (b, "nao_classificado")]:
        assert (
            next(
                x
                for x in listar(client, auth_headers, cid)["items"]
                if x["id_djen"] == 91002
            )["rotulo"]
            == esperado
        )


def test_isolamento_e_minimo(client, auth_headers, headers_outro, lote):
    cid = criar(client, auth_headers)
    assert (
        client.post(
            f"/api/djen/contextos/{cid}/treinar", headers=auth_headers, json={}
        ).status_code
        == 400
    )
    assert rotular(client, headers_outro, cid, "relevante").status_code == 403
    assert (
        client.get(
            "/api/djen/acervo", headers=headers_outro, query_string={"contexto_id": cid}
        ).status_code
        == 403
    )


def test_modelo_real_e_predicao_nao_classifica(app, client, auth_headers, djen):
    cid = criar(client, auth_headers)
    with app.test_request_context(), contexto_tenant(TENANT_DAJ):
        sess = get_session()
        from gestaolegal.services.djen_contexto_service import DjenContextoService
        from gestaolegal.repositories.djen_acervo_repository import DjenAcervoRepository

        for i in range(240):
            positivo = i % 2 == 0
            pid = DjenAcervoRepository().guardar(
                dict(
                    id_djen=800000 + i,
                    numero_processo=f"{i // 4:020d}",
                    data_disponibilizacao=date(2026, 11, 1),
                    texto_plano=(
                        "assistencia estudantil bolsa permanencia"
                        if positivo
                        else "licitacao contrato fornecedor"
                    ),
                    destinatarios=[{"nome": "Fulana de Tal"}],
                    sigla_tribunal="TJMG",
                    capturada_em=datetime.now(),
                    ativo=True,
                )
            )
            DjenAcervoRepository().dar_acesso(pid, 1, "parte")
            if i < 239:
                DjenContextoService().rotular(
                    pid,
                    cid,
                    "relevante" if positivo else "irrelevante",
                    "classificacao",
                    None,
                )
        sess.commit()
    from .test_djen_contextos_treino import treinar

    model = treinar(client, auth_headers, cid)
    assert model["metricas"]["teste"] > 0
    resp = client.get(
        "/api/djen/acervo",
        headers=auth_headers,
        query_string={"contexto_id": cid, "rotulo": "nao_classificado"},
    )
    assert resp.status_code == 200, resp.json
    items = get_success_data(resp)["items"]
    assert len(items) == 1
    ctx = items[0]["contextos"][0]
    assert ctx["sugestao"] == "irrelevante"
    assert ctx["modelo_id"] == model["id"]
    assert ctx["rotulo"] == "nao_classificado"
    filtrado = client.get(
        "/api/djen/acervo",
        headers=auth_headers,
        query_string={
            "contexto_id": cid,
            "sugestao": "irrelevante",
            "rotulo": "nao_classificado",
        },
    )
    assert get_success_data(filtrado)["total"] == 1
    filtrado = client.get(
        "/api/djen/acervo",
        headers=auth_headers,
        query_string={
            "contexto_id": cid,
            "sugestao": "relevante",
            "rotulo": "nao_classificado",
        },
    )
    assert get_success_data(filtrado)["total"] == 0


def test_contexto_nao_cruza_unidade(client, auth_headers, auth_headers_nl, lote):
    cid = criar(client, auth_headers)
    assert client.get("/api/djen/contextos", headers=auth_headers_nl).json["data"] == []
    assert rotular(client, auth_headers_nl, cid, "relevante").status_code == 404
    assert (
        client.post(
            f"/api/djen/contextos/{cid}/treinar", headers=auth_headers_nl, json={}
        ).status_code
        == 404
    )


def test_lote_contexto_atomico(client, auth_headers, lote):
    cid = criar(client, auth_headers)
    assert (
        rotular(client, auth_headers, cid, "relevante", [91001, 999999]).status_code
        == 400
    )
    assert all(
        x["rotulo"] == "nao_classificado"
        for x in listar(client, auth_headers, cid)["items"]
    )


def test_importacao_escolhe_contexto_e_preserva_avaliacao_manual(
    client, auth_headers, lote
):
    a = criar(client, auth_headers, "Escolhido")
    b = criar(client, auth_headers, "Não escolhido")
    c = criar(client, auth_headers, "Avaliado manualmente")
    assert rotular(client, auth_headers, c, "irrelevante").status_code == 200
    resposta = client.post(
        "/api/djen/busca-parte/importar",
        headers=auth_headers,
        json={"ids": [91001], "contexto_ids": [a, c]},
    )
    assert resposta.status_code == 200, resposta.json
    assert buscar(client, auth_headers).status_code == 200
    for cid, esperado in [
        (a, "relevante"),
        (b, "nao_classificado"),
        (c, "irrelevante"),
    ]:
        item = next(
            x
            for x in listar(client, auth_headers, cid)["items"]
            if x["id_djen"] == 91001
        )
        assert item["rotulo"] == esperado
        assert item["situacao"] == "vinculada"


def test_contexto_posterior_herda_descarte_e_aceita_variacao(
    client, auth_headers, lote
):
    resposta = client.post(
        "/api/djen/acervo/descartar",
        headers=auth_headers,
        json={"ids": [91002], "contexto_ids": []},
    )
    assert resposta.status_code == 200, resposta.json
    cid = criar(client, auth_headers, nomes=["Nome ausente", "FULANA DE TAL FICTICIA"])
    assert (
        next(
            x
            for x in listar(client, auth_headers, cid)["items"]
            if x["id_djen"] == 91002
        )["rotulo"]
        == "irrelevante"
    )
