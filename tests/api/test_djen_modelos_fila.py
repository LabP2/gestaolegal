# ruff: noqa: F811
"""Contrato assíncrono: fila persistente, GET sem ML e lotes limitados."""

from unittest.mock import Mock

from sqlalchemy import func, select
from gestaolegal.database.session import get_session
from gestaolegal.database.tables import djen_modelos
from gestaolegal.services.djen_contexto_service import DjenContextoService
from gestaolegal.utils.request_context import contexto_tenant
from .conftest import TENANT_DAJ, UNIDADE_BH, get_success_data
from .test_djen_contextos import criar
from .test_djen_contextos_treino import semear, cnj, relacoes_do_contexto
from .test_djen_exemplos import djen, transporte  # noqa: F401


def solicitar(client, headers, cid):
    r = client.post(f"/api/djen/contextos/{cid}/treinar", headers=headers, json={})
    assert r.status_code == 202, r.json
    return get_success_data(r)


def test_fila_idempotente_get_nao_preve_e_worker_limita_lote(
    app, client, auth_headers, djen, monkeypatch
):
    cid = criar(client, auth_headers)
    semear(app, cid, 240, lambda i: i % 2 == 0, lambda i: cnj(i // 4))
    pids = semear(app, cid, 205, lambda i: True, cnj, base=840000, rotular=False)
    pedido = solicitar(client, auth_headers, cid)
    assert pedido["treino_status"] == "na_fila"
    assert (
        solicitar(client, auth_headers, cid)["treino_token"] == pedido["treino_token"]
    )
    with app.test_request_context(), contexto_tenant(TENANT_DAJ):
        assert (
            get_session()
            .execute(
                select(func.count())
                .select_from(djen_modelos)
                .where(djen_modelos.c.tenant_id == TENANT_DAJ)
            )
            .scalar_one()
            == 0
        )
        s = DjenContextoService()
        assert s.executar_treino(cid, UNIDADE_BH, pedido["treino_token"])["id"] > 0
        assert s.obter(cid, UNIDADE_BH)["treino_status"] == "concluido"
        assert s.executar_treino(cid, UNIDADE_BH, pedido["treino_token"]) is None
    sem_ml = Mock(side_effect=AssertionError("GET não pode executar inferência"))
    with monkeypatch.context() as m:
        m.setattr(DjenContextoService, "prever", sem_ml)
        for filtro in ({}, {"sugestao": "relevante"}, {"sugestao": "sem_sugestao"}):
            response = client.get(
                "/api/djen/acervo",
                headers=auth_headers,
                query_string={"contexto_id": cid, **filtro},
            )
            assert response.status_code == 200, response.json
        sem_ml.assert_not_called()
    assert all(relacoes_do_contexto(app, cid)[pid]["modelo_id"] is None for pid in pids)
    with app.test_request_context(), contexto_tenant(TENANT_DAJ):
        assert DjenContextoService().processar_previsoes(cid, UNIDADE_BH) == 200
    rows = relacoes_do_contexto(app, cid)
    assert sum(rows[pid]["modelo_id"] is not None for pid in pids) == 200
    with app.test_request_context(), contexto_tenant(TENANT_DAJ):
        assert DjenContextoService().processar_previsoes(cid, UNIDADE_BH) == 5
        assert DjenContextoService().processar_previsoes(cid, UNIDADE_BH) == 0


def test_expiracao_impede_publicacao_e_permite_novo_pedido(
    app, client, auth_headers, djen
):
    cid = criar(client, auth_headers)
    semear(app, cid, 240, lambda i: i % 2 == 0, lambda i: cnj(i // 4))
    pedido = solicitar(client, auth_headers, cid)
    with app.test_request_context(), contexto_tenant(TENANT_DAJ):
        s = DjenContextoService()
        assert s.iniciar_treino(cid, pedido["treino_token"])
        s.falhar_treino(cid, pedido["treino_token"], "Tempo excedido")
        from gestaolegal.exceptions import ValidationException
        import pytest

        with pytest.raises(ValidationException, match="expirou"):
            s.treinar(cid, UNIDADE_BH, token=pedido["treino_token"])
        s.session.rollback()
        assert s.ultimo_modelo(cid) is None
    novo = solicitar(client, auth_headers, cid)
    assert novo["treino_token"] != pedido["treino_token"]
    with app.test_request_context(), contexto_tenant(TENANT_DAJ):
        s = DjenContextoService()
        s.falhar_treino(cid, pedido["treino_token"], "Falha de execução antiga")
        assert s.obter(cid, UNIDADE_BH)["treino_status"] == "na_fila"


def test_previsao_tardia_nao_sobrescreve_rotulo_manual(app, client, auth_headers, djen):
    cid = criar(client, auth_headers)
    semear(app, cid, 240, lambda i: i % 2 == 0, lambda i: cnj(i // 4))
    [pid] = semear(app, cid, 1, lambda i: True, cnj, base=850000, rotular=False)
    pedido = solicitar(client, auth_headers, cid)
    with app.test_request_context(), contexto_tenant(TENANT_DAJ):
        s = DjenContextoService()
        mid = s.executar_treino(cid, UNIDADE_BH, pedido["treino_token"])["id"]
        [alvo] = s.lote_previsoes(cid, mid)
        s.rotular(pid, cid, "irrelevante", "classificacao", None)
        s.session.commit()
        # Resultado calculado antes de o usuário terminar a avaliação.
        s.salvar_previsao(
            alvo["id"], dict(modelo_id=mid, sugestao="relevante", probabilidade="0.9")
        )
        s.session.commit()
    row = relacoes_do_contexto(app, cid)[pid]
    assert row["rotulo"] == "irrelevante" and row["origem"] == "classificacao"
    assert row["sugestao"] is None


def test_worker_recupera_execucao_abandonada_e_registra_timeout(
    app, client, auth_headers, djen
):
    from datetime import datetime, timedelta
    from sqlalchemy import update
    from gestaolegal.database.tables import djen_contextos
    from scripts.processar_djen_modelos import ciclo
    from subprocess import TimeoutExpired

    cid = criar(client, auth_headers)

    def estado(status, iniciado):
        with app.test_request_context(), contexto_tenant(TENANT_DAJ):
            session = get_session()
            session.execute(
                update(djen_contextos)
                .where(
                    djen_contextos.c.tenant_id == TENANT_DAJ, djen_contextos.c.id == cid
                )
                .values(
                    treino_status=status,
                    treino_token="teste-timeout",
                    treino_iniciado_em=iniciado,
                )
            )
            session.commit()

    estado("executando", datetime.now() - timedelta(minutes=16))
    runner = Mock()
    ciclo(app, executar=runner)
    runner.assert_not_called()
    with app.test_request_context(), contexto_tenant(TENANT_DAJ):
        assert DjenContextoService().obter(cid, UNIDADE_BH)["treino_status"] == "erro"
    estado("na_fila", None)
    runner.side_effect = TimeoutExpired("treino", 600)
    ciclo(app, executar=runner)
    runner.assert_called_once()
    assert runner.call_args.kwargs["timeout"] == 600
    with app.test_request_context(), contexto_tenant(TENANT_DAJ):
        ctx = DjenContextoService().obter(cid, UNIDADE_BH)
        assert ctx["treino_status"] == "erro"
        assert "10 minutos" in ctx["treino_erro"]
