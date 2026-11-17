"""DJEN, fase 3: OABs monitoradas, captura por OAB, descarte e retenção.

Sem rede: respostas sintéticas do `TransporteFalso`, com dados inventados.
"""

from datetime import datetime, timedelta

import pytest
from flask import Flask
from sqlalchemy import update

from gestaolegal.config import Config
from gestaolegal.database import session as db_session_module
from gestaolegal.database.tables import (
    djen_comunicacoes,
    djen_oabs,
    djen_sincronizacoes,
    eventos,
    processos,
    usuarios,
)
from gestaolegal.utils.request_context import sem_tenant

from .conftest import (
    TENANT_DAJ,
    TENANT_OUTRO,
    UNIDADE_BH,
    UNIDADE_NL,
    UNIDADE_OUTRO,
    criar_usuario,
    get_success_data,
    headers_para,
)
from .djen_fixtures import item_djen, ligar_djen, limpar_djen
from .test_djen_api import (  # noqa: F401 (fixtures)
    _linhas,
    criar_caso,
    criar_processo,
    djen,
    headers_outro,
    mascara,
    numero_cnj_novo,
    rodar_rotina,
    sync_habilitado,
    transporte,
)


def cadastrar(client, h, numero="123456", uf="MG", **extra) -> dict:
    r = client.post("/api/djen/oabs", json={"numero_oab": numero, "uf_oab": uf, **extra}, headers=h)
    assert r.status_code == 201, r.get_json()
    return get_success_data(r)


def _alterar(tabela, filtro, **valores) -> None:
    session = db_session_module.get_session()
    try:
        with sem_tenant("teste: ajuste direto"):
            if tabela is djen_comunicacoes and 'id_djen' in filtro:
                from gestaolegal.database.tables import djen_publicacoes
                pid = session.execute(djen_publicacoes.select().where(djen_publicacoes.c.id_djen == filtro['id_djen'])).mappings().one()['id']
                if 'capturada_em' in valores:
                    session.execute(update(djen_publicacoes).where(djen_publicacoes.c.id == pid).values(capturada_em=valores.pop('capturada_em')))
                filtro = {'id_publicacao': pid}
                if not valores:
                    session.commit()
                    return
            stmt = update(tabela)
            for coluna, valor in filtro.items():
                stmt = stmt.where(tabela.c[coluna] == valor)
            session.execute(stmt.values(**valores))
            session.commit()
    finally:
        session.close()


def _headers_papel(client, app, papel: str):
    email = f"{papel}.oab.djen@gl.com"
    with app.app_context():
        uid = criar_usuario(email, "senha12345", papel, f"Pessoa {papel}")
    return uid, headers_para(client, email, "senha12345")


# --------------------------------------------------------------------------- #
# Cadastro das OABs (admin)
# --------------------------------------------------------------------------- #


class TestCadastroOab:
    def test_crud(self, client, auth_headers, djen):
        me = get_success_data(client.get("/api/user/me", headers=auth_headers))
        oab = cadastrar(client, auth_headers, "012.345", "mg", id_usuario=me["id"])
        assert oab["numero_oab"] == "12345" and oab["uf_oab"] == "MG"
        assert oab["rotulo"] == "12345/MG"
        assert oab["unidade_id"] == UNIDADE_BH and oab["ativo"] is True
        assert oab["usuario_nome"] == me["nome"]
        assert oab["id_criado_por"] == me["id"]

        lista = get_success_data(client.get("/api/djen/oabs", headers=auth_headers))
        assert [o["id"] for o in lista] == [oab["id"]]

        r = client.put(f"/api/djen/oabs/{oab['id']}", json={"ativo": False, "id_usuario": None}, headers=auth_headers)
        assert r.status_code == 200, r.get_json()
        alterada = get_success_data(r)
        assert alterada["ativo"] is False and alterada["id_usuario"] is None

        assert client.delete(f"/api/djen/oabs/{oab['id']}", headers=auth_headers).status_code == 200
        assert _linhas(djen_oabs, id=oab["id"]) == []

    def test_duplicada_da_400(self, client, auth_headers, djen):
        cadastrar(client, auth_headers, "222333", "SP")
        r = client.post("/api/djen/oabs", json={"numero_oab": "222333", "uf_oab": "sp"}, headers=auth_headers)
        assert r.status_code == 400

    @pytest.mark.parametrize(
        "corpo",
        [
            {"numero_oab": "", "uf_oab": "MG"},
            {"numero_oab": "12A45", "uf_oab": "MG"},
            {"numero_oab": "12345678901", "uf_oab": "MG"},
            {"numero_oab": "12345", "uf_oab": "XX"},
            {"numero_oab": "12345"},
            {"numero_oab": True, "uf_oab": "MG"},
            {"numero_oab": "12345", "uf_oab": "MG", "ativo": "sim"},
        ],
    )
    def test_validacao(self, client, auth_headers, djen, corpo):
        assert client.post("/api/djen/oabs", json=corpo, headers=auth_headers).status_code == 400

    def test_unidade_escolhida_precisa_ser_do_admin(self, client, auth_headers, djen):
        oab = cadastrar(client, auth_headers, "444555", "MG", unidade_id=UNIDADE_NL)
        assert oab["unidade_id"] == UNIDADE_NL
        # Unidade de outro NPJ: mesma resposta de id inexistente.
        for unidade in (UNIDADE_OUTRO, 999):
            r = client.post(
                "/api/djen/oabs",
                json={"numero_oab": "444556", "uf_oab": "MG", "unidade_id": unidade},
                headers=auth_headers,
            )
            assert r.status_code == 400

    def test_usuario_de_outro_npj_e_recusado(self, client, app, auth_headers, djen):
        # A conta do outro NPJ dos testes de isolamento (eles contam os usuários).
        from .test_tenant_isolamento import OUTRO_EMAIL, OUTRO_SENHA

        with app.app_context():
            outro = criar_usuario(OUTRO_EMAIL, OUTRO_SENHA, "admin", "Admin Outro NPJ", tenant_id=TENANT_OUTRO)
        r = client.post(
            "/api/djen/oabs",
            json={"numero_oab": "555666", "uf_oab": "MG", "id_usuario": outro},
            headers=auth_headers,
        )
        assert r.status_code == 400
        assert _linhas(djen_oabs, numero_oab="555666") == []

    def test_lista_filtra_pela_unidade_ativa(self, client, auth_headers, auth_headers_nl, djen):
        bh = cadastrar(client, auth_headers, "777001", "MG")
        nl = cadastrar(client, auth_headers_nl, "777002", "MG")
        assert [o["id"] for o in get_success_data(client.get("/api/djen/oabs", headers=auth_headers))] == [bh["id"]]
        assert [o["id"] for o in get_success_data(client.get("/api/djen/oabs", headers=auth_headers_nl))] == [nl["id"]]
        # De outra unidade: 404 na edição e na remoção.
        assert client.put(f"/api/djen/oabs/{nl['id']}", json={"ativo": False}, headers=auth_headers).status_code == 404
        assert client.delete(f"/api/djen/oabs/{nl['id']}", headers=auth_headers).status_code == 404

    @pytest.mark.parametrize("papel", ["prof", "orient", "colab_proj", "estag_direito", "colab_ext"])
    def test_so_admin(self, client, app, djen, papel):
        _, h = _headers_papel(client, app, papel)
        assert client.get("/api/djen/oabs", headers=h).status_code == 403
        assert client.get("/api/djen/oabs/sugestoes", headers=h).status_code == 403
        r = client.post("/api/djen/oabs", json={"numero_oab": "1", "uf_oab": "MG"}, headers=h)
        assert r.status_code == 403
        assert _linhas(djen_oabs) == []

    def test_djen_desligado_da_403(self, client, app, auth_headers):
        with app.app_context():
            limpar_djen()
        assert client.get("/api/djen/oabs", headers=auth_headers).status_code == 403
        r = client.post("/api/djen/oabs", json={"numero_oab": "1", "uf_oab": "MG"}, headers=auth_headers)
        assert r.status_code == 403

    def test_sugestoes_vem_do_cadastro_de_usuarios(self, client, app, auth_headers, djen):
        uid, _ = _headers_papel(client, app, "orient")
        estag, _ = _headers_papel(client, app, "estag_direito")
        _alterar(usuarios, {"id": uid}, oab="MG 98.765")
        _alterar(usuarios, {"id": estag}, oab="11111/MG")
        try:
            sugestoes = get_success_data(client.get("/api/djen/oabs/sugestoes", headers=auth_headers))
            minha = next(s for s in sugestoes if s["id_usuario"] == uid)
            assert (minha["numero_oab"], minha["uf_oab"], minha["cadastrada"]) == ("98765", "MG", False)
            assert all(s["id_usuario"] != estag for s in sugestoes)  # só orient/prof/admin
            cadastrar(client, auth_headers, "98765", "MG")
            sugestoes = get_success_data(client.get("/api/djen/oabs/sugestoes", headers=auth_headers))
            assert next(s for s in sugestoes if s["id_usuario"] == uid)["cadastrada"] is True
        finally:
            _alterar(usuarios, {"id": uid}, oab=None)
            _alterar(usuarios, {"id": estag}, oab=None)

    def test_separar_oab(self):
        from gestaolegal.services.djen_service import separar_oab

        assert separar_oab("123456/MG") == ("123456", "MG")
        assert separar_oab("MG-123.456") == ("123456", "MG")
        assert separar_oab("OAB 1") is None  # "OAB" não é UF
        assert separar_oab("123456") is None
        assert separar_oab(None) is None


# --------------------------------------------------------------------------- #
# Captura por OAB (rotina)
# --------------------------------------------------------------------------- #


class TestCapturaPorOab:
    def test_rotina_busca_a_janela_de_cada_oab_ativa(
        self, app, client, auth_headers, djen, transporte, sync_habilitado
    ):
        cadastrar(client, auth_headers, "123456", "MG")
        inativa = cadastrar(client, auth_headers, "654321", "MG")
        client.put(f"/api/djen/oabs/{inativa['id']}", json={"ativo": False}, headers=auth_headers)
        assert rodar_rotina(app, janela_dias=3)["daj-ufmg"] == "ok"
        chamadas = [c for c in transporte.chamadas if "numeroOab" in c]
        assert [(c["numeroOab"], c["ufOab"]) for c in chamadas] == [("123456", "MG")]
        hoje = datetime.now().date()
        assert chamadas[0]["dataDisponibilizacaoFim"] == hoje.isoformat()
        assert chamadas[0]["dataDisponibilizacaoInicio"] == (hoje - timedelta(days=2)).isoformat()

    def test_sem_processo_fica_pendente_na_unidade_da_oab(
        self, app, client, auth_headers, auth_headers_nl, djen, transporte, sync_habilitado
    ):
        cadastrar(client, auth_headers_nl, "123456", "MG")
        numero = numero_cnj_novo()
        transporte.por_oab[("123456", "MG")] = [item_djen(11001, numero)]
        rodar_rotina(app)
        (linha,) = _linhas(djen_comunicacoes, id_djen=11001)
        assert linha["situacao"] == "pendente" and linha["id_caso"] is None
        assert linha["unidade_id"] == UNIDADE_NL
        assert linha["oab_origem"] == "123456/MG"
        # Aparece no "Sem caso" de Nova Lima, não no de BH.
        nl = get_success_data(client.get("/api/djen/publicacoes?situacao=pendente", headers=auth_headers_nl))
        assert [i["id"] for i in nl["items"]] == [linha["id"]]
        bh = get_success_data(client.get("/api/djen/publicacoes?situacao=pendente", headers=auth_headers))
        assert bh["total"] == 0

    def test_com_processo_casa_e_usa_a_unidade_do_caso(
        self, app, client, auth_headers, auth_headers_nl, djen, transporte, sync_habilitado
    ):
        # OAB em Nova Lima, processo num caso de BH: vale a unidade do caso.
        cadastrar(client, auth_headers_nl, "123456", "MG")
        caso = criar_caso(client, auth_headers)
        p = criar_processo(client, auth_headers, caso)
        # Fora da fila de pendentes: o casamento vem só pela OAB.
        _alterar(processos, {"id": p["id"]}, djen_pendente=False)
        transporte.por_oab[("123456", "MG")] = [item_djen(11101, p["numero_cnj"])]
        rodar_rotina(app)
        (linha,) = _linhas(djen_comunicacoes, id_djen=11101)
        assert linha["situacao"] == "vinculada"
        assert linha["id_processo"] == p["id"] and linha["id_caso"] == caso
        assert linha["unidade_id"] == UNIDADE_BH
        assert len(_linhas(eventos, id_djen_comunicacao=linha["id"])) == 1

    def test_a_mesma_publicacao_por_duas_oabs_grava_uma_vez(
        self, app, client, auth_headers, djen, transporte, sync_habilitado
    ):
        cadastrar(client, auth_headers, "123456", "MG")
        cadastrar(client, auth_headers, "999888", "MG")
        numero = numero_cnj_novo()
        transporte.por_oab[("123456", "MG")] = [item_djen(11201, numero)]
        transporte.por_oab[("999888", "MG")] = [item_djen(11201, numero)]
        rodar_rotina(app)
        rodar_rotina(app)
        assert len(_linhas(djen_comunicacoes, id_djen=11201)) == 1

    def test_falha_de_uma_oab_deixa_parcial(
        self, app, client, auth_headers, djen, transporte, sync_habilitado
    ):
        cadastrar(client, auth_headers, "123456", "MG")
        cadastrar(client, auth_headers, "999888", "MG")
        transporte.por_oab[("123456", "MG")] = [item_djen(11301, numero_cnj_novo())]
        transporte.falhar.add("999888/MG")
        assert rodar_rotina(app)["daj-ufmg"] == "parcial"
        assert len(_linhas(djen_comunicacoes, id_djen=11301)) == 1
        (sinc,) = _linhas(djen_sincronizacoes, tenant_id=TENANT_DAJ)
        assert "OAB 999888/MG" in sinc["mensagem"]

    def test_oab_de_um_npj_nao_e_consultada_pelo_outro(
        self, app, client, auth_headers, headers_outro, djen, transporte, sync_habilitado
    ):
        ligar_djen(TENANT_OUTRO, True)
        cadastrar(client, auth_headers, "123456", "MG")
        numero = numero_cnj_novo()
        transporte.por_oab[("123456", "MG")] = [item_djen(11401, numero)]
        rodar_rotina(app)
        linhas = _linhas(djen_comunicacoes, id_djen=11401)
        assert [r["tenant_id"] for r in linhas] == [TENANT_DAJ]
        assert get_success_data(client.get("/api/djen/oabs", headers=headers_outro)) == []
        # A mesma OAB pode ser cadastrada no outro NPJ (unicidade por tenant).
        oab_outro = cadastrar(client, headers_outro, "123456", "MG")
        assert oab_outro["unidade_id"] == UNIDADE_OUTRO
        rodar_rotina(app)
        assert {r["tenant_id"] for r in _linhas(djen_comunicacoes, id_djen=11401)} == {
            TENANT_DAJ,
            TENANT_OUTRO,
        }


# --------------------------------------------------------------------------- #
# Descarte e vínculo a partir do "Sem caso"
# --------------------------------------------------------------------------- #


@pytest.fixture
def pendente(app, client, auth_headers, djen, transporte, sync_habilitado) -> dict:
    cadastrar(client, auth_headers, "123456", "MG")
    transporte.por_oab[("123456", "MG")] = [item_djen(12001, numero_cnj_novo())]
    rodar_rotina(app)
    (linha,) = _linhas(djen_comunicacoes, id_djen=12001)
    return linha


class TestDescarte:
    def test_descartar(self, client, auth_headers, pendente):
        r = client.post(f"/api/djen/publicacoes/{pendente['id']}/descartar", headers=auth_headers)
        assert r.status_code == 200, r.get_json()
        assert get_success_data(r)["situacao"] == "descartada"
        me = get_success_data(client.get("/api/user/me", headers=auth_headers))
        (linha,) = _linhas(djen_comunicacoes, id=pendente["id"])
        assert linha["situacao"] == "descartada"
        assert linha["data_situacao"] is not None and linha["id_vinculado_por"] == me["id"]
        sem_caso = get_success_data(client.get("/api/djen/publicacoes?situacao=pendente", headers=auth_headers))
        assert sem_caso["total"] == 0
        # Descartar de novo: 400.
        assert client.post(f"/api/djen/publicacoes/{pendente['id']}/descartar", headers=auth_headers).status_code == 400

    def test_vinculada_nao_pode_ser_descartada(self, client, auth_headers, pendente):
        caso = criar_caso(client, auth_headers)
        p = criar_processo(client, auth_headers, caso)
        r = client.post(
            f"/api/djen/publicacoes/{pendente['id']}/vincular",
            json={"processo_id": p["id"]},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.get_json()
        r = client.post(f"/api/djen/publicacoes/{pendente['id']}/descartar", headers=auth_headers)
        assert r.status_code == 400
        assert _linhas(djen_comunicacoes, id=pendente["id"])[0]["situacao"] == "vinculada"

    def test_descartada_ainda_pode_ser_vinculada(self, client, auth_headers, pendente):
        client.post(f"/api/djen/publicacoes/{pendente['id']}/descartar", headers=auth_headers)
        caso = criar_caso(client, auth_headers)
        p = criar_processo(client, auth_headers, caso)
        r = client.post(
            f"/api/djen/publicacoes/{pendente['id']}/vincular",
            json={"processo_id": p["id"]},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.get_json()
        assert get_success_data(r)["situacao"] == "vinculada"

    def test_outra_unidade_da_404(self, client, auth_headers_nl, pendente):
        r = client.post(f"/api/djen/publicacoes/{pendente['id']}/descartar", headers=auth_headers_nl)
        assert r.status_code == 404
        assert _linhas(djen_comunicacoes, id=pendente["id"])[0]["situacao"] == "pendente"

    @pytest.mark.parametrize("papel", ["colab_proj", "estag_direito", "colab_ext"])
    def test_so_quem_vincula_descarta(self, client, app, pendente, papel):
        _, h = _headers_papel(client, app, papel)
        r = client.post(f"/api/djen/publicacoes/{pendente['id']}/descartar", headers=h)
        assert r.status_code == 403
        assert _linhas(djen_comunicacoes, id=pendente["id"])[0]["situacao"] == "pendente"

    @pytest.mark.parametrize("papel", ["prof", "orient"])
    def test_professor_e_orientador_descartam(self, client, app, pendente, papel):
        _, h = _headers_papel(client, app, papel)
        r = client.post(f"/api/djen/publicacoes/{pendente['id']}/descartar", headers=h)
        assert r.status_code == 200, r.get_json()


# --------------------------------------------------------------------------- #
# Retenção (plano, §8)
# --------------------------------------------------------------------------- #


class TestRetencao:
    def test_preserva_descartadas_e_pendentes_antigas(
        self, app, client, auth_headers, djen, transporte, sync_habilitado
    ):
        cadastrar(client, auth_headers, "123456", "MG")
        caso = criar_caso(client, auth_headers)
        p = criar_processo(client, auth_headers, caso)
        numeros = [numero_cnj_novo() for _ in range(4)]
        transporte.por_oab[("123456", "MG")] = [
            item_djen(13001, numeros[0]),  # pendente antiga: apagada
            item_djen(13002, numeros[1]),  # pendente recente: fica
            item_djen(13003, numeros[2]),  # descartada há muito: apagada
            item_djen(13004, numeros[3]),  # descartada agora: fica
            item_djen(13005, p["numero_cnj"]),  # vinculada antiga: fica
        ]
        rodar_rotina(app)
        transporte.por_oab.clear()
        antigo = datetime.now() - timedelta(days=Config.DJEN_RETENCAO_DIAS + 1)
        _alterar(djen_comunicacoes, {"id_djen": 13001}, capturada_em=antigo)
        _alterar(djen_comunicacoes, {"id_djen": 13003}, situacao="descartada", data_situacao=antigo, capturada_em=antigo)
        _alterar(djen_comunicacoes, {"id_djen": 13004}, situacao="descartada", data_situacao=datetime.now(), capturada_em=antigo)
        _alterar(djen_comunicacoes, {"id_djen": 13005}, capturada_em=antigo)

        rodar_rotina(app)

        restantes = {r["id_djen"] for r in _linhas(djen_comunicacoes, tenant_id=TENANT_DAJ)}
        assert restantes == {13001, 13002, 13003, 13004, 13005}

    def test_retencao_nao_toca_outro_npj(
        self, app, client, auth_headers, headers_outro, djen, transporte, sync_habilitado
    ):
        # Só a DAJ roda (o outro NPJ está desligado): a pendente antiga do outro fica.
        cadastrar(client, auth_headers, "123456", "MG")
        from gestaolegal.integrations.djen_client import converter_item
        from gestaolegal.models.djen import ResultadoCaptura
        from gestaolegal.services.djen_service import DJENService
        from gestaolegal.utils.request_context import contexto_tenant

        with app.test_request_context():
            with contexto_tenant(TENANT_OUTRO):
                service = DJENService()
                service.registrar(
                    converter_item(item_djen(13101, numero_cnj_novo())),
                    ResultadoCaptura(),
                    unidade_padrao=UNIDADE_OUTRO,
                )
                service.session.commit()
        antigo = datetime.now() - timedelta(days=Config.DJEN_RETENCAO_DIAS + 1)
        _alterar(djen_comunicacoes, {"id_djen": 13101}, capturada_em=antigo)
        assert rodar_rotina(app)["daj-ufmg"] == "ok"
        assert len(_linhas(djen_comunicacoes, id_djen=13101)) == 1
