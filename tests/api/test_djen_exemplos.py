"""Banco de exemplos rotulados do DJEN (docs/plano-processos-avulsos.md,
"Banco de exemplos"; docs/plano-djen.md, §8).

Sem rede: o DJEN responde pelo `TransporteFalso` (nomes e números inventados).
"""

import json
from datetime import datetime, timedelta

import pytest
from flask import Flask
from sqlalchemy import update

from gestaolegal.config import Config
from gestaolegal.database import session as db_session_module
from gestaolegal.database.tables import (
    djen_comunicacoes,
    djen_exemplos,
    eventos,
    processos,
)
from gestaolegal.utils.request_context import sem_tenant

from .conftest import TENANT_DAJ, TENANT_OUTRO, criar_usuario, get_success_data, headers_para
from .djen_fixtures import item_djen, ligar_djen
from .test_djen_api import (  # noqa: F401  (fixtures)
    _linhas,
    criar_caso,
    criar_processo,
    djen,
    headers_outro,
    numero_cnj_novo,
    rodar_rotina,
    sync_habilitado,
    transporte,
)
from .test_djen_eventos import registrar_pendente

SENHA = "senha12345"
PERIODO = {"de": "2026-11-01", "ate": "2026-11-20"}


@pytest.fixture
def papeis(client, app: Flask) -> dict[str, dict]:
    """Um usuário de cada papel, na unidade BH: {papel: {"id", "h"}}."""
    resultado = {}
    with app.app_context():
        for papel in ("prof", "orient", "colab_proj", "estag_direito", "colab_ext"):
            email = f"{papel}.exemplos@gl.com"
            uid = criar_usuario(email, SENHA, papel, f"Usuário {papel} exemplos")
            resultado[papel] = {"id": uid, "h": headers_para(client, email, SENHA)}
    return resultado


def _me(client, h) -> int:
    return get_success_data(client.get("/api/user/me", headers=h))["id"]


def _exemplo(id_djen: int, tenant: int = TENANT_DAJ) -> dict | None:
    linhas = _linhas(djen_exemplos, id_djen=id_djen, tenant_id=tenant)
    assert len(linhas) <= 1
    return linhas[0] if linhas else None


def _alterar_exemplo(id_djen: int, **valores) -> None:
    session = db_session_module.get_session()
    try:
        with sem_tenant("teste: datas do exemplo"):
            session.execute(
                update(djen_exemplos).where(djen_exemplos.c.id_djen == id_djen).values(**valores)
            )
            session.commit()
    finally:
        session.close()


def _contagens() -> tuple[int, int, int]:
    return len(_linhas(djen_comunicacoes)), len(_linhas(processos)), len(_linhas(eventos))


def _buscar(client, h, nome: str) -> dict:
    r = client.get("/api/djen/busca-parte", query_string={"nome": nome, **PERIODO}, headers=h)
    assert r.status_code == 200, r.get_json()
    return get_success_data(r)


def _nao_pertinentes(client, h, nome: str, ids: list[int]):
    return client.post(
        "/api/djen/busca-parte/nao-pertinentes", json={"nome": nome, **PERIODO, "ids": ids}, headers=h
    )


def _importar(client, h, nome: str, ids: list[int]):
    return client.post("/api/djen/busca-parte/importar", json={"nome": nome, **PERIODO, "ids": ids}, headers=h)


# --------------------------------------------------------------------------- #
# Busca por parte
# --------------------------------------------------------------------------- #


class TestBuscaParte:
    def test_nao_pertinentes_grava_exemplos_sem_publicacao_nem_processo(
        self, client, auth_headers, djen, transporte
    ):
        nome = "Universidade Fictícia Não Pertinente"
        transporte.por_parte[nome] = [
            item_djen(91001, numero_cnj_novo(), data="2026-11-05", tribunal="TRF6"),
            item_djen(91002, numero_cnj_novo(), data="2026-11-04"),
            item_djen(91003, numero_cnj_novo(), data="2026-11-03"),
        ]
        antes = _contagens()
        r = _nao_pertinentes(client, auth_headers, nome, [91001, 99999])
        assert r.status_code == 200, r.get_json()
        d = get_success_data(r)
        assert d == {"marcadas": 1, "nao_revisadas": 2, "nao_encontradas": [99999]}
        assert _contagens() == antes

        e = _exemplo(91001)
        assert (e["rotulo"], e["origem"], e["termo_busca"]) == ("nao_pertinente", "busca_parte", nome)
        assert e["id_rotulado_por"] == _me(client, auth_headers)
        assert e["rotulado_em"] is not None and e["texto_apagado_em"] is None
        assert e["sigla_tribunal"] == "TRF6" and str(e["data_disponibilizacao"]) == "2026-11-05"
        # Texto plano limpo, sem HTML nem script.
        assert "Prazo de 15 dias." in e["texto_plano"] and "<" not in e["texto_plano"]
        assert "alert" not in e["texto_plano"]
        assert [x["nome"] for x in e["destinatarios"]] == ["Fulana de Tal Fictícia", "Empresa Imaginária Ltda"]
        for id_djen in (91002, 91003):
            outro = _exemplo(id_djen)
            assert (outro["rotulo"], outro["origem"]) == ("nao_revisada", "busca_parte")
            assert outro["id_rotulado_por"] is None and outro["rotulado_em"] is None
            assert outro["termo_busca"] == nome and outro["texto_plano"]

    def test_busca_traz_o_rotulo_sem_gravar(self, client, auth_headers, djen, transporte):
        nome = "Parte Fictícia Rotulada"
        transporte.por_parte[nome] = [
            item_djen(91011, numero_cnj_novo(), data="2026-11-05"),
            item_djen(91012, numero_cnj_novo(), data="2026-11-04"),
        ]
        d = _buscar(client, auth_headers, nome)
        assert [i["rotulo"] for i in d["items"]] == [None, None]
        assert _linhas(djen_exemplos) == []  # a busca em si não grava
        _nao_pertinentes(client, auth_headers, nome, [91011])
        d = _buscar(client, auth_headers, nome)
        assert {i["id_djen"]: i["rotulo"] for i in d["items"]} == {
            91011: "nao_pertinente",
            91012: "nao_revisada",
        }
        # Não pertinente não entra no sistema: continua importável.
        assert all(i["ja_no_banco"] is False for i in d["items"])

    def test_importar_rotula_pertinente_e_o_resto_nao_revisada(
        self, client, auth_headers, djen, transporte
    ):
        caso = criar_caso(client, auth_headers)
        p = criar_processo(client, auth_headers, caso)
        nome = "Parte Fictícia Importada"
        transporte.por_parte[nome] = [
            item_djen(91021, p["numero_cnj"], data="2026-11-05"),
            item_djen(91022, numero_cnj_novo(), data="2026-11-04"),
        ]
        r = _importar(client, auth_headers, nome, [91021])
        assert r.status_code == 200, r.get_json()
        e = _exemplo(91021)
        assert (e["rotulo"], e["origem"], e["termo_busca"]) == ("pertinente", "busca_parte", nome)
        assert e["id_rotulado_por"] == _me(client, auth_headers)
        assert _exemplo(91022)["rotulo"] == "nao_revisada"
        # O vínculo da importação não grava um segundo exemplo "automático".
        assert len(_linhas(djen_exemplos, id_djen=91021)) == 1

    def test_mudar_de_ideia_o_mais_recente_vence(self, client, auth_headers, djen, transporte):
        caso = criar_caso(client, auth_headers)
        p = criar_processo(client, auth_headers, caso)
        nome = "Parte Fictícia Indecisa"
        transporte.por_parte[nome] = [item_djen(91031, p["numero_cnj"])]
        assert _nao_pertinentes(client, auth_headers, nome, [91031]).status_code == 200
        primeiro = _exemplo(91031)
        assert primeiro["rotulo"] == "nao_pertinente"
        # Item não pertinente continua importável; a importação o torna pertinente.
        assert _importar(client, auth_headers, nome, [91031]).status_code == 200
        segundo = _exemplo(91031)
        assert (segundo["rotulo"], segundo["origem"]) == ("pertinente", "busca_parte")
        assert segundo["id"] == primeiro["id"]
        assert segundo["criado_em"] == primeiro["criado_em"]
        assert segundo["rotulado_em"] >= primeiro["rotulado_em"]
        # E de volta: marcar como não pertinente sobrescreve o pertinente.
        assert _nao_pertinentes(client, auth_headers, nome, [91031]).status_code == 200
        assert _exemplo(91031)["rotulo"] == "nao_pertinente"

    def test_nao_revisada_nunca_rebaixa(self, client, auth_headers, djen, transporte):
        nome = "Parte Fictícia Estável"
        transporte.por_parte[nome] = [
            item_djen(91041, numero_cnj_novo(), data="2026-11-05"),
            item_djen(91042, numero_cnj_novo(), data="2026-11-04"),
            item_djen(91043, numero_cnj_novo(), data="2026-11-03"),
        ]
        _nao_pertinentes(client, auth_headers, nome, [91041])
        rotulado = _exemplo(91041)
        nao_revisada = _exemplo(91043)
        # Nova marcação na mesma consulta: 91041 fica como estava (não vira
        # "não revisada"), e a 91043, já não revisada, não é recriada.
        r = _nao_pertinentes(client, auth_headers, nome, [91042])
        assert get_success_data(r)["nao_revisadas"] == 0
        assert _exemplo(91041) == rotulado
        assert _exemplo(91043) == nao_revisada
        assert _exemplo(91042)["rotulo"] == "nao_pertinente"

    def test_nao_revisada_promovida_por_rotulo_explicito(self, client, auth_headers, djen, transporte):
        nome = "Parte Fictícia Promovida"
        transporte.por_parte[nome] = [
            item_djen(91051, numero_cnj_novo(), data="2026-11-05"),
            item_djen(91052, numero_cnj_novo(), data="2026-11-04"),
        ]
        _nao_pertinentes(client, auth_headers, nome, [91051])
        assert _exemplo(91052)["rotulo"] == "nao_revisada"
        _nao_pertinentes(client, auth_headers, nome, [91052])
        e = _exemplo(91052)
        assert e["rotulo"] == "nao_pertinente" and e["rotulado_em"] is not None
        assert e["id_rotulado_por"] == _me(client, auth_headers)

    @pytest.mark.parametrize(
        "corpo",
        [
            {"nome": "Fulana", **PERIODO, "ids": []},
            {"nome": "Fulana", **PERIODO, "ids": list(range(1, 102))},
            {"nome": "Fulana", **PERIODO, "ids": ["1"]},
            {"nome": "Fulana", **PERIODO},
            {"nome": "Fu", **PERIODO, "ids": [1]},
            {"nome": "Fulana", "de": "2026-10-01", "ate": "2026-11-20", "ids": [1]},
        ],
    )
    def test_validacao_igual_a_da_importacao(self, client, auth_headers, djen, transporte, corpo):
        r = client.post("/api/djen/busca-parte/nao-pertinentes", json=corpo, headers=auth_headers)
        assert r.status_code == 400
        assert transporte.chamadas == []
        assert _linhas(djen_exemplos) == []

    def test_conteudo_vem_do_djen_e_nao_do_corpo(self, client, auth_headers, djen, transporte):
        # O id que o DJEN não devolve na reconsulta não vira exemplo.
        transporte.por_parte["Parte Fictícia Vazia"] = []
        d = get_success_data(_nao_pertinentes(client, auth_headers, "Parte Fictícia Vazia", [91061]))
        assert d == {"marcadas": 0, "nao_revisadas": 0, "nao_encontradas": [91061]}
        assert _linhas(djen_exemplos) == []

    @pytest.mark.parametrize("papel", ["colab_proj", "estag_direito", "colab_ext"])
    def test_so_quem_vincula_marca(self, client, papeis, djen, transporte, papel):
        r = _nao_pertinentes(client, papeis[papel]["h"], "Fulana", [1])
        assert r.status_code == 403
        assert transporte.chamadas == []

    @pytest.mark.parametrize("papel", ["prof", "orient"])
    def test_professor_e_orientador_marcam(self, client, papeis, djen, transporte, papel):
        transporte.por_parte["Parte Fictícia Docente"] = [item_djen(91071, numero_cnj_novo())]
        r = _nao_pertinentes(client, papeis[papel]["h"], "Parte Fictícia Docente", [91071])
        assert r.status_code == 200, r.get_json()
        assert _exemplo(91071)["id_rotulado_por"] == papeis[papel]["id"]

    def test_djen_desligado(self, client, auth_headers, transporte):
        assert _nao_pertinentes(client, auth_headers, "Fulana", [1]).status_code == 403
        assert client.get("/api/djen/exemplos/resumo", headers=auth_headers).status_code == 403
        assert client.get("/api/djen/exemplos/exportar", headers=auth_headers).status_code == 403


# --------------------------------------------------------------------------- #
# Rotina e caixa "Sem caso"
# --------------------------------------------------------------------------- #


class TestRotinaECaixa:
    def test_vinculo_automatico_da_rotina(
        self, app, client, auth_headers, djen, transporte, sync_habilitado
    ):
        caso = criar_caso(client, auth_headers)
        p = criar_processo(client, auth_headers, caso)
        transporte.por_processo[p["numero_cnj"]] = [item_djen(92001, p["numero_cnj"])]
        assert rodar_rotina(app)["daj-ufmg"] == "ok"
        e = _exemplo(92001)
        assert (e["rotulo"], e["origem"]) == ("pertinente", "vinculo_automatico")
        assert e["id_rotulado_por"] is None and e["termo_busca"] is None
        assert e["rotulado_em"] is not None
        assert "Prazo de 15 dias." in e["texto_plano"]

    def test_pendente_nao_vira_exemplo(self, app, djen):
        registrar_pendente(app, 92011, numero_cnj_novo())
        assert _exemplo(92011) is None

    def test_vinculo_manual(self, app, client, auth_headers, djen):
        caso = criar_caso(client, auth_headers)
        p = criar_processo(client, auth_headers, caso)
        pub = registrar_pendente(app, 92021, numero_cnj_novo())
        r = client.post(f"/api/djen/publicacoes/{pub}/vincular", json={"processo_id": p["id"]}, headers=auth_headers)
        assert r.status_code == 200, r.get_json()
        e = _exemplo(92021)
        assert (e["rotulo"], e["origem"]) == ("pertinente", "vinculo_manual")
        assert e["id_rotulado_por"] == _me(client, auth_headers)

    def test_descartar_e_desfazer_vinculando(self, app, client, auth_headers, djen):
        pub = registrar_pendente(app, 92031, numero_cnj_novo())
        r = client.post(f"/api/djen/publicacoes/{pub}/descartar", headers=auth_headers)
        assert r.status_code == 200, r.get_json()
        e = _exemplo(92031)
        assert (e["rotulo"], e["origem"]) == ("nao_pertinente", "descarte")
        assert e["id_rotulado_por"] == _me(client, auth_headers)
        assert "Prazo de 15 dias." in e["texto_plano"]
        # Desfazer o descarte vinculando: passa a pertinente.
        caso = criar_caso(client, auth_headers)
        p = criar_processo(client, auth_headers, caso)
        r = client.post(f"/api/djen/publicacoes/{pub}/vincular", json={"processo_id": p["id"]}, headers=auth_headers)
        assert r.status_code == 200, r.get_json()
        depois = _exemplo(92031)
        assert (depois["rotulo"], depois["origem"]) == ("pertinente", "vinculo_manual")
        assert depois["id"] == e["id"]

    def test_falha_ao_descartar_nao_grava_exemplo(self, app, client, auth_headers, djen):
        caso = criar_caso(client, auth_headers)
        p = criar_processo(client, auth_headers, caso)
        pub = registrar_pendente(app, 92041, numero_cnj_novo())
        client.post(f"/api/djen/publicacoes/{pub}/vincular", json={"processo_id": p["id"]}, headers=auth_headers)
        r = client.post(f"/api/djen/publicacoes/{pub}/descartar", headers=auth_headers)
        assert r.status_code == 400
        assert _exemplo(92041)["rotulo"] == "pertinente"


# --------------------------------------------------------------------------- #
# Retenção
# --------------------------------------------------------------------------- #


class TestRetencao:
    def test_apaga_nao_revisadas_e_anula_texto_das_rotuladas(
        self, app, client, auth_headers, djen, transporte, sync_habilitado
    ):
        nome = "Parte Fictícia Retida"
        transporte.por_parte[nome] = [
            item_djen(93000 + n, numero_cnj_novo(), data=f"2026-11-0{n}") for n in range(1, 6)
        ]
        _nao_pertinentes(client, auth_headers, nome, [93001, 93002])
        # 93003..93005 são não revisadas.
        agora = datetime.now()
        vencida = agora - timedelta(days=Config.DJEN_RETENCAO_DIAS + 1)
        _alterar_exemplo(93003, criado_em=vencida)  # não revisada antiga: some
        _alterar_exemplo(93004, criado_em=agora - timedelta(days=10))  # recente: fica
        # Não revisada antiga mas com rótulo? Não existe: o rótulo a tira daí.
        _alterar_exemplo(
            93001,
            criado_em=vencida,
            rotulado_em=agora - timedelta(days=Config.DJEN_EXEMPLOS_RETENCAO_DIAS + 1),
        )
        _alterar_exemplo(93002, criado_em=vencida, rotulado_em=agora - timedelta(days=100))

        assert rodar_rotina(app)["daj-ufmg"] == "ok"

        assert _exemplo(93003) is None
        assert _exemplo(93004)["texto_plano"] and _exemplo(93005)["texto_plano"]
        antigo = _exemplo(93001)
        assert antigo["texto_plano"] is None and antigo["destinatarios"] is None
        assert antigo["texto_apagado_em"] is not None
        # Rótulo e metadados ficam.
        assert (antigo["rotulo"], antigo["origem"], antigo["termo_busca"]) == (
            "nao_pertinente",
            "busca_parte",
            nome,
        )
        assert antigo["sigla_tribunal"] == "TJMG" and antigo["numero_processo"]
        recente = _exemplo(93002)
        assert recente["texto_plano"] and recente["destinatarios"] and recente["texto_apagado_em"] is None

        # Segunda passada não mexe de novo no que já foi anulado.
        apagado_em = antigo["texto_apagado_em"]
        rodar_rotina(app)
        assert _exemplo(93001)["texto_apagado_em"] == apagado_em

        # Rotular de novo renova o texto e o prazo.
        _nao_pertinentes(client, auth_headers, nome, [93001])
        renovado = _exemplo(93001)
        assert renovado["texto_plano"] and renovado["texto_apagado_em"] is None

    def test_retencao_nao_toca_outro_npj(
        self, app, client, auth_headers, headers_outro, djen, transporte, sync_habilitado
    ):
        # Só a DAJ roda a rotina; o exemplo do outro NPJ fica.
        ligar_djen(TENANT_OUTRO, True)
        transporte.por_parte["Parte Fictícia do Outro"] = [
            item_djen(93101, numero_cnj_novo()),
            item_djen(93102, numero_cnj_novo()),
        ]
        _nao_pertinentes(client, headers_outro, "Parte Fictícia do Outro", [93101])
        ligar_djen(TENANT_OUTRO, False)
        vencida = datetime.now() - timedelta(days=Config.DJEN_EXEMPLOS_RETENCAO_DIAS + 1)
        _alterar_exemplo(93101, rotulado_em=vencida, criado_em=vencida)
        _alterar_exemplo(93102, criado_em=vencida)
        assert rodar_rotina(app)["daj-ufmg"] == "ok"
        assert _exemplo(93101, TENANT_OUTRO)["texto_plano"]
        assert _exemplo(93102, TENANT_OUTRO) is not None


# --------------------------------------------------------------------------- #
# Resumo e exportação (admin)
# --------------------------------------------------------------------------- #


def _cenario_exportacao(app, client, h, transporte) -> None:
    nome = "Parte Fictícia Exportada"
    caso = criar_caso(client, h)
    p = criar_processo(client, h, caso)
    transporte.por_parte[nome] = [
        item_djen(94001, p["numero_cnj"], data="2026-11-05"),
        item_djen(94002, numero_cnj_novo(), data="2026-11-04"),
        item_djen(94003, numero_cnj_novo(), data="2026-11-03"),
    ]
    _importar(client, h, nome, [94001])
    _nao_pertinentes(client, h, nome, [94002])
    pub = registrar_pendente(app, 94004, numero_cnj_novo())
    client.post(f"/api/djen/publicacoes/{pub}/descartar", headers=h)
    _alterar_exemplo(
        94004, rotulado_em=datetime.now() - timedelta(days=Config.DJEN_EXEMPLOS_RETENCAO_DIAS + 1)
    )
    from gestaolegal.services.djen_service import DJENService
    from gestaolegal.utils.request_context import contexto_tenant

    with app.test_request_context(), contexto_tenant(TENANT_DAJ):
        DJENService()._aplicar_retencao()


class TestResumoEExportacao:
    def test_resumo(self, app, client, auth_headers, djen, transporte):
        _cenario_exportacao(app, client, auth_headers, transporte)
        r = client.get("/api/djen/exemplos/resumo", headers=auth_headers)
        assert r.status_code == 200, r.get_json()
        d = get_success_data(r)
        assert d["total"] == 4
        assert d["por_rotulo"] == {"pertinente": 1, "nao_pertinente": 2, "nao_revisada": 1}
        assert d["por_origem"] == {"busca_parte": 3, "descarte": 1}
        assert d["com_texto"] == 3  # o descarte antigo perdeu o texto
        assert d["retencao_dias"] == Config.DJEN_EXEMPLOS_RETENCAO_DIAS

    def test_exportar_jsonl(self, app, client, auth_headers, djen, transporte):
        _cenario_exportacao(app, client, auth_headers, transporte)
        r = client.get("/api/djen/exemplos/exportar", headers=auth_headers)
        assert r.status_code == 200
        assert r.mimetype == "application/x-ndjson"
        assert "attachment" in r.headers["Content-Disposition"]
        assert ".jsonl" in r.headers["Content-Disposition"]
        linhas = [json.loads(x) for x in r.get_data(as_text=True).splitlines()]
        por_id = {x["id_djen"]: x for x in linhas}
        assert set(por_id) == {94001, 94002, 94004}  # sem a não revisada
        assert por_id[94001]["rotulo"] == "pertinente"
        assert por_id[94002]["termo_busca"] == "Parte Fictícia Exportada"
        assert por_id[94002]["data_disponibilizacao"] == "2026-11-04"
        assert "Prazo de 15 dias." in por_id[94002]["texto_plano"]
        assert por_id[94004]["texto_plano"] is None and por_id[94004]["texto_apagado_em"]
        # Nada de quem rotulou nem ids internos no arquivo.
        assert all("id_rotulado_por" not in x and "id" not in x and "tenant_id" not in x for x in linhas)

        r = client.get("/api/djen/exemplos/exportar?incluir_nao_revisadas=1", headers=auth_headers)
        ids = {json.loads(x)["id_djen"] for x in r.get_data(as_text=True).splitlines()}
        assert ids == {94001, 94002, 94003, 94004}

    def test_banco_vazio(self, client, auth_headers, djen):
        d = get_success_data(client.get("/api/djen/exemplos/resumo", headers=auth_headers))
        assert d["total"] == 0 and d["com_texto"] == 0
        assert d["por_rotulo"] == {"pertinente": 0, "nao_pertinente": 0, "nao_revisada": 0}
        r = client.get("/api/djen/exemplos/exportar", headers=auth_headers)
        assert r.status_code == 200 and r.get_data() == b""

    @pytest.mark.parametrize("papel", ["prof", "orient", "colab_proj", "estag_direito", "colab_ext"])
    def test_so_admin(self, client, papeis, djen, papel):
        h = papeis[papel]["h"]
        assert client.get("/api/djen/exemplos/resumo", headers=h).status_code == 403
        assert client.get("/api/djen/exemplos/exportar", headers=h).status_code == 403

    def test_outro_npj_nao_ve(self, app, client, auth_headers, headers_outro, djen, transporte):
        _cenario_exportacao(app, client, auth_headers, transporte)
        ligar_djen(TENANT_OUTRO, True)
        d = get_success_data(client.get("/api/djen/exemplos/resumo", headers=headers_outro))
        assert d["total"] == 0
        r = client.get("/api/djen/exemplos/exportar?incluir_nao_revisadas=1", headers=headers_outro)
        assert r.status_code == 200 and r.get_data() == b""
        # O mesmo id_djen rotulado no outro NPJ é outro exemplo; o da DAJ fica.
        transporte.por_parte["Parte Fictícia Exportada"] = [item_djen(94001, numero_cnj_novo())]
        _nao_pertinentes(client, headers_outro, "Parte Fictícia Exportada", [94001])
        assert _exemplo(94001, TENANT_OUTRO)["rotulo"] == "nao_pertinente"
        assert _exemplo(94001, TENANT_DAJ)["rotulo"] == "pertinente"
        busca = _buscar(client, auth_headers, "Parte Fictícia Exportada")
        assert busca["items"][0]["rotulo"] == "pertinente"
