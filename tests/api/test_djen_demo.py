"""DJEN fictício do ambiente de demonstração (DEMO_MODE).

O conftest troca o transporte padrão por um que falha ao acessar a rede: se
algum caminho da demo escapasse para a API real, estes testes quebrariam.
"""

import itertools
import json
from datetime import date, timedelta

import pytest
from flask import Flask
from sqlalchemy import select

from gestaolegal.database import session as db_session_module
from gestaolegal.database.tables import djen_comunicacoes, eventos, tenants
from gestaolegal.integrations.djen_client import DJENClient
from gestaolegal.integrations.djen_demo import (
    BASE_ID,
    cnj_de_demonstracao,
    publicacoes_da_oab,
    publicacoes_do_processo,
    transporte_demo,
)
from gestaolegal.services.djen_service import DJENService, link_certidao
from gestaolegal.utils.request_context import sem_tenant

from .conftest import TENANT_DAJ, get_success_data
from .test_djen_api import (  # noqa: F401  (fixtures)
    _linhas,
    criar_caso,
    criar_processo,
    djen,
    mascara,
    numero_cnj_novo,
)

_seq = itertools.count(1)


def cnj_demo() -> str:
    """CNJ com segmento de justiça 0, como os do seed de demonstração."""
    n = next(_seq)
    return f"{8000000 + n:07d}112026013{n:04d}"


@pytest.fixture
def demo_mode(app: Flask):
    anterior = app.config.get("DEMO_MODE")
    app.config["DEMO_MODE"] = True
    yield
    app.config["DEMO_MODE"] = anterior


# --------------------------------------------------------------------------- #
# Transporte fictício
# --------------------------------------------------------------------------- #


def _corpo(url: str) -> dict:
    resposta = transporte_demo(url, 30)
    assert resposta.status == 200
    return json.loads(resposta.corpo)


def test_cnj_de_demonstracao_e_o_do_segmento_zero():
    assert cnj_de_demonstracao(cnj_demo())
    assert not cnj_de_demonstracao(numero_cnj_novo())  # segmento 8 (estadual)
    assert not cnj_de_demonstracao("123")


def test_processo_de_demonstracao_tem_historico_ate_a_sentenca():
    numero = cnj_demo()
    hoje = date(2026, 11, 22)
    itens = publicacoes_do_processo(numero, hoje)
    assert [i["tipoDocumento"] for i in itens] == ["Despacho", "Decisão", "Sentença"]
    assert all(i["numero_processo"] == numero for i in itens)
    assert all(i["id"] >= BASE_ID for i in itens)
    assert "JULGO PROCEDENTE" in itens[-1]["texto"]
    assert "fictício" in itens[-1]["texto"]
    assert itens[-1]["data_disponibilizacao"] == (hoje - timedelta(days=4)).isoformat()
    # Ids estáveis: repetir a busca não duplica publicações.
    assert [i["id"] for i in publicacoes_do_processo(numero)] == [i["id"] for i in itens]


def test_consultas_reais_voltam_vazias_sem_erro():
    real = numero_cnj_novo()
    assert _corpo(f"https://x/api/v1/comunicacao?numeroProcesso={real}&pagina=1")["items"] == []
    assert _corpo(
        "https://x/api/v1/comunicacao?numeroOab=123456&ufOab=MG"
        "&dataDisponibilizacaoInicio=2026-11-01&dataDisponibilizacaoFim=2026-11-22&pagina=1"
    )["items"] == []
    assert _corpo(
        "https://x/api/v1/comunicacao?nomeParte=Maria+da+Silva"
        "&dataDisponibilizacaoInicio=2026-11-01&dataDisponibilizacaoFim=2026-11-22&pagina=1"
    )["items"] == []


def test_oab_de_demonstracao_traz_publicacoes_da_janela_de_processo_nao_cadastrado():
    fim = date(2026, 11, 22)
    itens = publicacoes_da_oab("990002", "mg", fim - timedelta(days=7), fim)
    assert len(itens) == 2
    assert all(fim - timedelta(days=7) <= date.fromisoformat(i["data_disponibilizacao"]) <= fim for i in itens)
    assert all(cnj_de_demonstracao(i["numero_processo"]) for i in itens)
    advogado = itens[0]["destinatarioadvogados"][0]["advogado"]
    assert (advogado["numero_oab"], advogado["uf_oab"]) == ("990002", "MG")
    # Janela curta corta o que ficou fora dela.
    assert len(publicacoes_da_oab("990002", "MG", fim - timedelta(days=2), fim)) == 1


def test_cliente_com_transporte_demo_converte_as_publicacoes():
    numero = cnj_demo()
    cliente = DJENClient(transporte=transporte_demo)
    itens = cliente.buscar_por_processo(numero)
    assert [c.tipo_documento for c in itens] == ["Despacho", "Decisão", "Sentença"]
    assert cliente.requisicoes == 1
    assert link_certidao(itens[0].hash) is None


# --------------------------------------------------------------------------- #
# Escolha do cliente pelo DEMO_MODE
# --------------------------------------------------------------------------- #


def test_sem_demo_o_servico_usa_o_transporte_padrao(app: Flask):
    with app.test_request_context():
        assert DJENService().client._transporte is None


def test_com_demo_o_servico_usa_o_djen_ficticio(app: Flask, demo_mode):
    with app.test_request_context():
        assert DJENService().client._transporte is transporte_demo


def test_busca_do_processo_na_demo_cria_eventos_sem_acessar_a_rede(
    client, auth_headers, djen, demo_mode
):
    caso = criar_caso(client, auth_headers)
    p = criar_processo(client, auth_headers, caso, numero=mascara(cnj_demo()))
    r = client.post(f"/api/processos/{p['id']}/djen/buscar", headers=auth_headers)
    assert r.status_code == 200, r.get_json()
    assert get_success_data(r)["novas"] == 3

    evs = [e for e in _linhas(eventos, id_caso=caso) if e["origem"] == "djen"]
    assert len(evs) == 3
    # De novo: mesmas publicações, nada duplicado.
    r = client.post(f"/api/processos/{p['id']}/djen/buscar", headers=auth_headers)
    assert get_success_data(r)["novas"] == 0
    assert len([e for e in _linhas(eventos, id_caso=caso) if e["origem"] == "djen"]) == 3


def test_busca_de_processo_real_na_demo_responde_vazio(client, auth_headers, djen, demo_mode):
    caso = criar_caso(client, auth_headers)
    p = criar_processo(client, auth_headers, caso)
    r = client.post(f"/api/processos/{p['id']}/djen/buscar", headers=auth_headers)
    assert r.status_code == 200, r.get_json()
    assert get_success_data(r)["novas"] == 0


def test_fora_da_demo_a_busca_continua_indo_ao_transporte_padrao(client, auth_headers, djen):
    # O transporte padrão dos testes recusa a rede: sem DEMO_MODE, a busca
    # tenta a API real e falha, como antes desta mudança.
    caso = criar_caso(client, auth_headers)
    p = criar_processo(client, auth_headers, caso, numero=mascara(cnj_demo()))
    r = client.post(f"/api/processos/{p['id']}/djen/buscar", headers=auth_headers)
    assert r.status_code != 200


# --------------------------------------------------------------------------- #
# flask djen semear-demo
# --------------------------------------------------------------------------- #


def _djen_ativo(tenant_id: int) -> bool:
    session = db_session_module.get_session()
    try:
        with sem_tenant("teste: chave do DJEN"):
            return bool(
                session.execute(select(tenants.c.djen_ativo).where(tenants.c.id == tenant_id)).scalar_one()
            )
    finally:
        session.close()


def test_semear_fora_da_demo_nao_faz_nada(app: Flask, djen):
    from gestaolegal.cli import semear_djen_demo
    from .djen_fixtures import ligar_djen

    with app.app_context():
        ligar_djen(TENANT_DAJ, False)
        mensagens = []
        assert semear_djen_demo("daj-ufmg", echo=mensagens.append) is None
        assert mensagens == ["DEMO_MODE desligado: nada a fazer."]
        assert not _djen_ativo(TENANT_DAJ)


def test_semear_na_demo_liga_o_djen_e_captura(app: Flask, client, auth_headers, djen, demo_mode):
    from gestaolegal.cli import semear_djen_demo
    from .djen_fixtures import ligar_djen

    caso = criar_caso(client, auth_headers)
    numero = cnj_demo()
    criar_processo(client, auth_headers, caso, numero=mascara(numero))
    with app.app_context():
        ligar_djen(TENANT_DAJ, False)
        registro = semear_djen_demo("daj-ufmg", echo=lambda *_: None)
        assert _djen_ativo(TENANT_DAJ)
    assert registro is not None
    assert registro["novas"] >= 3
    capturadas = [c for c in _linhas(djen_comunicacoes) if c["numero_processo"] == numero]
    assert len(capturadas) == 3
    assert {c["situacao"] for c in capturadas} == {"vinculada"}
    assert len([e for e in _linhas(eventos, id_caso=caso) if e["origem"] == "djen"]) == 3


def test_dados_do_seed_sao_reconhecidos_pelo_djen_ficticio():
    # O seed e o DJEN fictício precisam combinar: CNJ com segmento 0 e OAB 9900*.
    from scripts.seed_database import TENANTS_DEMO, cnj_demonstracao

    numero = "".join(c for c in cnj_demonstracao(3001, 2026, 3) if c.isdigit())
    assert cnj_de_demonstracao(numero)
    assert len(publicacoes_do_processo(numero)) == 3
    for tenant in TENANTS_DEMO.values():
        assert publicacoes_da_oab(tenant.oab_orientador, "MG", None, None)
