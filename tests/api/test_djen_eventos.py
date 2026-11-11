"""DJEN, fase 2: evento no caso, notificações, vínculo manual e campos travados."""

import pytest
from flask import Flask
from sqlalchemy import select

from gestaolegal.database import session as db_session_module
from gestaolegal.database.tables import djen_comunicacoes, eventos, notificacao
from gestaolegal.integrations.djen_client import converter_item
from gestaolegal.models.djen import ResultadoCaptura
from gestaolegal.utils.request_context import contexto_tenant, sem_tenant

from .conftest import (
    TENANT_DAJ,
    TENANT_OUTRO,
    UNIDADE_BH,
    UNIDADE_OUTRO,
    criar_usuario,
    get_success_data,
    headers_para,
)
from .djen_fixtures import item_djen, ligar_djen
from .test_djen_api import (  # noqa: F401  (fixtures)
    _linhas,
    _me,
    criar_caso,
    criar_processo,
    djen,
    mascara,
    numero_cnj_novo,
    rodar_rotina,
    sync_habilitado,
    transporte,
)

SENHA = "senha12345"


@pytest.fixture
def equipe(app: Flask) -> dict[str, int]:
    with app.app_context():
        return {
            "orient": criar_usuario("orient.djen@gl.com", SENHA, "orient", "Orientadora DJEN"),
            "estag": criar_usuario("estag.djen@gl.com", SENHA, "estag_direito", "Estagiário DJEN"),
            "colab": criar_usuario("colab.djen@gl.com", SENHA, "colab_ext", "Colaboradora DJEN"),
        }


@pytest.fixture
def caso_com_equipe(client, auth_headers, equipe) -> int:
    return criar_caso(
        client,
        auth_headers,
        id_orientador=equipe["orient"],
        id_estagiario=equipe["estag"],
        id_colaborador=equipe["colab"],
    )


def _notificacoes_djen(id_caso: int) -> list[dict]:
    return [n for n in _linhas(notificacao, tipo="djen") if n["id_caso"] == id_caso]


def _eventos_djen(id_caso: int) -> list[dict]:
    return [e for e in _linhas(eventos, id_caso=id_caso) if e["origem"] == "djen"]


def registrar_pendente(app, id_djen: int, numero: str, tenant=TENANT_DAJ, unidade=UNIDADE_BH) -> int:
    """Publicação sem caso, como chega por uma OAB monitorada."""
    from gestaolegal.services.djen_service import DJENService

    with app.test_request_context():
        with contexto_tenant(tenant):
            service = DJENService()
            service.registrar(converter_item(item_djen(id_djen, numero)), ResultadoCaptura(),
                              unidade_padrao=unidade, oab_origem="123456/MG")
            service._depois_da_fonte()
            service.session.commit()
    session = db_session_module.get_session()
    try:
        with sem_tenant("teste: id da publicação"):
            return session.execute(
                select(djen_comunicacoes.c.id).where(
                    djen_comunicacoes.c.id_djen == id_djen, djen_comunicacoes.c.tenant_id == tenant
                )
            ).scalar_one()
    finally:
        session.close()


class TestVinculoAutomatico:
    def test_rotina_cria_evento_e_notifica_os_participantes(
        self, app, client, auth_headers, djen, transporte, sync_habilitado, caso_com_equipe, equipe
    ):
        p = criar_processo(client, auth_headers, caso_com_equipe)
        transporte.por_processo[p["numero_cnj"]] = [item_djen(11001, p["numero_cnj"])]
        rodar_rotina(app)

        (evento,) = _eventos_djen(caso_com_equipe)
        assert evento["tipo"] == "Intimação"
        assert str(evento["data_evento"]) == "2026-11-03"
        assert evento["descricao"].startswith("1ª Vara Cível da Comarca Fictícia — Procedimento Comum Cível")
        assert "Prazo de 15 dias." in evento["descricao"]
        assert "alert" not in evento["descricao"]
        assert evento["id_criado_por"] is None  # rotina, sem usuário
        assert evento["id_usuario_responsavel"] == equipe["estag"]
        assert evento["unidade_id"] == UNIDADE_BH
        assert evento["tenant_id"] == TENANT_DAJ
        (com,) = _linhas(djen_comunicacoes, id_djen=11001)
        assert evento["id_djen_comunicacao"] == com["id"]

        avisos = _notificacoes_djen(caso_com_equipe)
        assert sorted(a["id_usu_notificar"] for a in avisos) == sorted(equipe.values())
        assert all(a["id_referencia"] == evento["id"] for a in avisos)
        assert all(a["id_executor_acao"] is None for a in avisos)
        assert avisos[0]["acao"] == f"Nova publicação no DJEN no caso {caso_com_equipe}"

    def test_descricao_cabe_na_coluna_latin1_e_classe_em_maiusculas(
        self, client, auth_headers, djen, transporte, caso_com_equipe
    ):
        # `eventos.descricao` é latin1 no MySQL: U+0096 e símbolos fora do
        # cp1252 derrubavam o INSERT (erro 1366) e a busca dava 500.
        p = criar_processo(client, auth_headers, caso_com_equipe)
        item = item_djen(11050, p["numero_cnj"], texto="Juiz da Vara \x96 Orcri \x96 prazo ≥ 5 dias")
        item["nomeClasse"] = "AçãO TRABALHISTA - RITO SUMARíSSIMO"
        transporte.por_processo[p["numero_cnj"]] = [item]
        r = client.post(f"/api/processos/{p['id']}/djen/buscar", headers=auth_headers)
        assert r.status_code == 200

        (evento,) = _eventos_djen(caso_com_equipe)
        assert evento["descricao"].startswith(
            "1ª Vara Cível da Comarca Fictícia — AÇÃO TRABALHISTA - RITO SUMARÍSSIMO"
        )
        assert "Vara – Orcri – prazo ? 5 dias" in evento["descricao"]
        evento["descricao"].encode("cp1252")
        (com,) = _linhas(djen_comunicacoes, id_djen=11050)
        assert com["nome_classe"] == "AÇÃO TRABALHISTA - RITO SUMARÍSSIMO"

    def test_responsavel_e_o_orientador_sem_estagiario(self, client, auth_headers, djen, transporte, equipe):
        caso = criar_caso(client, auth_headers, id_orientador=equipe["orient"])
        p = criar_processo(client, auth_headers, caso)
        transporte.por_processo[p["numero_cnj"]] = [item_djen(11101, p["numero_cnj"])]
        client.post(f"/api/processos/{p['id']}/djen/buscar", headers=auth_headers)
        (evento,) = _eventos_djen(caso)
        assert evento["id_usuario_responsavel"] == equipe["orient"]

    def test_historico_vira_um_evento_por_publicacao_e_um_aviso_por_pessoa(
        self, client, auth_headers, djen, transporte, caso_com_equipe, equipe
    ):
        p = criar_processo(client, auth_headers, caso_com_equipe)
        n = p["numero_cnj"]
        transporte.por_processo[n] = [
            item_djen(11201, n, data="2026-10-01"),
            item_djen(11202, n, data="2026-10-15"),
            item_djen(11203, n, data="2026-11-01"),
        ]
        client.post(f"/api/processos/{p['id']}/djen/buscar", headers=auth_headers)
        evs = _eventos_djen(caso_com_equipe)
        assert len(evs) == 3
        assert sorted(e["num_evento"] for e in evs) == [1, 2, 3]
        avisos = _notificacoes_djen(caso_com_equipe)
        assert sorted(a["id_usu_notificar"] for a in avisos) == sorted(equipe.values())
        recente = next(e for e in evs if str(e["data_evento"]) == "2026-11-01")
        assert all(a["id_referencia"] == recente["id"] for a in avisos)
        assert avisos[0]["acao"] == f"3 novas publicações no DJEN no caso {caso_com_equipe}"

    def test_quem_clicou_nao_e_notificado(self, client, auth_headers, djen, transporte, equipe):
        admin_id = _me(client, auth_headers)["id"]
        caso = criar_caso(client, auth_headers, id_orientador=admin_id, id_estagiario=equipe["estag"])
        p = criar_processo(client, auth_headers, caso)
        transporte.por_processo[p["numero_cnj"]] = [item_djen(11301, p["numero_cnj"])]
        client.post(f"/api/processos/{p['id']}/djen/buscar", headers=auth_headers)
        avisos = _notificacoes_djen(caso)
        assert [a["id_usu_notificar"] for a in avisos] == [equipe["estag"]]
        (evento,) = _eventos_djen(caso)
        assert evento["id_criado_por"] == admin_id

    def test_buscar_de_novo_nao_duplica_evento_nem_aviso(
        self, client, auth_headers, djen, transporte, caso_com_equipe
    ):
        p = criar_processo(client, auth_headers, caso_com_equipe)
        transporte.por_processo[p["numero_cnj"]] = [item_djen(11401, p["numero_cnj"])]
        url = f"/api/processos/{p['id']}/djen/buscar"
        client.post(url, headers=auth_headers)
        client.post(url, headers=auth_headers)
        assert len(_eventos_djen(caso_com_equipe)) == 1
        assert len(_notificacoes_djen(caso_com_equipe)) == 3

    def test_processo_inativo_nao_casa(self, app, client, auth_headers, djen, caso_com_equipe):
        numero = numero_cnj_novo()
        p = criar_processo(client, auth_headers, caso_com_equipe, mascara(numero))
        assert client.delete(f"/api/caso/{caso_com_equipe}/processos/{p['id']}", headers=auth_headers).status_code == 200
        registrar_pendente(app, 11501, numero)
        (com,) = _linhas(djen_comunicacoes, id_djen=11501)
        assert com["situacao"] == "pendente" and com["id_caso"] is None
        assert com["unidade_id"] == UNIDADE_BH  # da OAB
        assert _eventos_djen(caso_com_equipe) == []

    def test_pendente_casa_quando_o_processo_e_cadastrado_depois(
        self, app, client, auth_headers, djen, caso_com_equipe
    ):
        numero = numero_cnj_novo()
        registrar_pendente(app, 11601, numero)
        criar_processo(client, auth_headers, caso_com_equipe, mascara(numero))
        registrar_pendente(app, 11601, numero)  # chega de novo pela OAB
        (com,) = _linhas(djen_comunicacoes, id_djen=11601)
        assert com["situacao"] == "vinculada" and com["id_caso"] == caso_com_equipe
        assert len(_eventos_djen(caso_com_equipe)) == 1

    def test_cancelamento_mantem_o_evento_com_selo_e_avisa(
        self, client, auth_headers, djen, transporte, caso_com_equipe, equipe
    ):
        p = criar_processo(client, auth_headers, caso_com_equipe)
        n = p["numero_cnj"]
        url = f"/api/processos/{p['id']}/djen/buscar"
        transporte.por_processo[n] = [item_djen(11701, n)]
        client.post(url, headers=auth_headers)
        transporte.por_processo[n] = [item_djen(11701, n, ativo=False, motivo_cancelamento="Erro material")]
        client.post(url, headers=auth_headers)

        (evento,) = _eventos_djen(caso_com_equipe)
        assert evento["status"] is True
        lista = get_success_data(client.get(f"/api/caso/{caso_com_equipe}/eventos", headers=auth_headers))
        (item,) = [e for e in lista["items"] if e["id"] == evento["id"]]
        assert item["origem"] == "djen" and item["djen_ativa"] is False
        detalhe = get_success_data(
            client.get(f"/api/caso/{caso_com_equipe}/eventos/{evento['id']}", headers=auth_headers)
        )
        assert detalhe["djen_ativa"] is False
        canceladas = [a for a in _notificacoes_djen(caso_com_equipe) if "cancelada" in a["acao"]]
        assert sorted(a["id_usu_notificar"] for a in canceladas) == sorted(equipe.values())


class TestVinculoManual:
    def test_vincular_cria_evento_e_notifica_sem_o_executor(
        self, app, client, auth_headers, djen, caso_com_equipe, equipe
    ):
        p = criar_processo(client, auth_headers, caso_com_equipe)
        pub = registrar_pendente(app, 12001, numero_cnj_novo())
        h = headers_para(client, "orient.djen@gl.com", SENHA)
        r = client.post(f"/api/djen/publicacoes/{pub}/vincular", json={"processo_id": p["id"]}, headers=h)
        assert r.status_code == 200, r.get_json()
        d = get_success_data(r)
        assert d["situacao"] == "vinculada" and d["id_caso"] == caso_com_equipe
        (com,) = _linhas(djen_comunicacoes, id=pub)
        assert com["id_vinculado_por"] == equipe["orient"]
        (evento,) = _eventos_djen(caso_com_equipe)
        assert evento["id_criado_por"] == equipe["orient"]
        avisos = _notificacoes_djen(caso_com_equipe)
        assert sorted(a["id_usu_notificar"] for a in avisos) == sorted([equipe["estag"], equipe["colab"]])

    def test_ja_vinculada_da_400(self, app, client, auth_headers, djen, caso_com_equipe):
        p = criar_processo(client, auth_headers, caso_com_equipe)
        pub = registrar_pendente(app, 12101, numero_cnj_novo())
        url = f"/api/djen/publicacoes/{pub}/vincular"
        assert client.post(url, json={"processo_id": p["id"]}, headers=auth_headers).status_code == 200
        assert client.post(url, json={"processo_id": p["id"]}, headers=auth_headers).status_code == 400
        assert len(_eventos_djen(caso_com_equipe)) == 1

    @pytest.mark.parametrize("corpo", [{}, {"processo_id": "1"}, {"processo_id": True}, {"processo_id": 987654}])
    def test_processo_invalido_da_400(self, app, client, auth_headers, djen, corpo):
        pub = registrar_pendente(app, 12201 + hash(str(corpo)) % 1000, numero_cnj_novo())
        r = client.post(f"/api/djen/publicacoes/{pub}/vincular", json=corpo, headers=auth_headers)
        assert r.status_code == 400

    def test_processo_de_outra_unidade_da_400(self, app, client, auth_headers, auth_headers_nl, djen):
        caso_nl = criar_caso(client, auth_headers_nl)
        p_nl = criar_processo(client, auth_headers_nl, caso_nl)
        pub = registrar_pendente(app, 12301, numero_cnj_novo())
        r = client.post(f"/api/djen/publicacoes/{pub}/vincular", json={"processo_id": p_nl["id"]}, headers=auth_headers)
        assert r.status_code == 400

    @pytest.mark.parametrize("papel", ["colab_proj", "estag_direito", "colab_ext"])
    def test_so_quem_vincula(self, app, client, auth_headers, djen, caso_com_equipe, papel):
        p = criar_processo(client, auth_headers, caso_com_equipe)
        pub = registrar_pendente(app, 12401, numero_cnj_novo())
        with app.app_context():
            criar_usuario(f"{papel}.vinc@gl.com", SENHA, papel, f"Usuário {papel}")
        h = headers_para(client, f"{papel}.vinc@gl.com", SENHA)
        r = client.post(f"/api/djen/publicacoes/{pub}/vincular", json={"processo_id": p["id"]}, headers=h)
        assert r.status_code == 403
        assert _eventos_djen(caso_com_equipe) == []

    def test_djen_desligado_da_403(self, app, client, auth_headers, djen, caso_com_equipe):
        p = criar_processo(client, auth_headers, caso_com_equipe)
        pub = registrar_pendente(app, 12501, numero_cnj_novo())
        ligar_djen(TENANT_DAJ, False)
        r = client.post(f"/api/djen/publicacoes/{pub}/vincular", json={"processo_id": p["id"]}, headers=auth_headers)
        assert r.status_code == 403

    def test_processo_de_outro_npj_da_a_mesma_resposta_de_inexistente(self, app, client, auth_headers, djen):
        from .test_tenant_isolamento import OUTRO_EMAIL, OUTRO_SENHA

        ligar_djen(TENANT_OUTRO, True)
        with app.app_context():
            criar_usuario(OUTRO_EMAIL, OUTRO_SENHA, "admin", "Admin Outro NPJ", tenant_id=TENANT_OUTRO)
        outro = headers_para(client, OUTRO_EMAIL, OUTRO_SENHA, unidade=UNIDADE_OUTRO)
        caso_daj = criar_caso(client, auth_headers)
        p_daj = criar_processo(client, auth_headers, caso_daj)
        pub_outro = registrar_pendente(app, 12601, numero_cnj_novo(), tenant=TENANT_OUTRO, unidade=UNIDADE_OUTRO)
        url = f"/api/djen/publicacoes/{pub_outro}/vincular"
        cruzada = client.post(url, json={"processo_id": p_daj["id"]}, headers=outro)
        inexistente = client.post(url, json={"processo_id": 987654}, headers=outro)
        assert cruzada.status_code == 400
        assert (cruzada.status_code, cruzada.get_json()) == (inexistente.status_code, inexistente.get_json())
        assert _eventos_djen(caso_daj) == []


class TestEventoDjenNoCaso:
    @pytest.fixture
    def evento_djen(self, client, auth_headers, djen, transporte, caso_com_equipe) -> dict:
        p = criar_processo(client, auth_headers, caso_com_equipe)
        transporte.por_processo[p["numero_cnj"]] = [item_djen(13001, p["numero_cnj"])]
        client.post(f"/api/processos/{p['id']}/djen/buscar", headers=auth_headers)
        (evento,) = _eventos_djen(caso_com_equipe)
        return evento

    def _put(self, client, h, caso, evento, **form):
        return client.put(
            f"/api/caso/{caso}/eventos/{evento}", data=form, headers=h, content_type="multipart/form-data"
        )

    @pytest.mark.parametrize(
        "campo,valor",
        [("tipo", "Audiência"), ("data_evento", "2026-12-01"), ("descricao", "Outra coisa")],
    )
    def test_campos_da_publicacao_sao_travados(self, client, auth_headers, caso_com_equipe, evento_djen, campo, valor):
        r = self._put(client, auth_headers, caso_com_equipe, evento_djen["id"], **{campo: valor})
        assert r.status_code == 400
        assert r.get_json()["error"]["details"]["field"] == campo
        (depois,) = _linhas(eventos, id=evento_djen["id"])
        assert depois[campo] == evento_djen[campo]

    def test_mesmo_valor_e_responsavel_passam(self, client, auth_headers, caso_com_equipe, evento_djen, equipe):
        r = self._put(
            client, auth_headers, caso_com_equipe, evento_djen["id"],
            tipo=evento_djen["tipo"], id_usuario_responsavel=str(equipe["orient"]),
        )
        assert r.status_code == 200, r.get_json()
        (depois,) = _linhas(eventos, id=evento_djen["id"])
        assert depois["id_usuario_responsavel"] == equipe["orient"]

    def test_evento_manual_continua_editavel(self, client, auth_headers, caso_com_equipe, djen):
        r = client.post(
            f"/api/caso/{caso_com_equipe}/eventos",
            data={"tipo": "Audiência", "data_evento": "2026-06-20", "descricao": "Manual", "status": "true"},
            headers=auth_headers,
            content_type="multipart/form-data",
        )
        evento = get_success_data(r)
        assert evento["origem"] == "manual"
        r = self._put(client, auth_headers, caso_com_equipe, evento["id"], tipo="Reunião", descricao="Alterado")
        assert r.status_code == 200
        d = get_success_data(r)
        assert d["tipo"] == "Reunião" and d["descricao"] == "Alterado"

    def test_filtro_por_origem(self, client, auth_headers, caso_com_equipe, evento_djen):
        client.post(
            f"/api/caso/{caso_com_equipe}/eventos",
            data={"tipo": "Audiência", "data_evento": "2026-06-20", "status": "true"},
            headers=auth_headers,
            content_type="multipart/form-data",
        )
        base = f"/api/caso/{caso_com_equipe}/eventos"
        djen_ = get_success_data(client.get(f"{base}?origem=djen", headers=auth_headers))["items"]
        manual = get_success_data(client.get(f"{base}?origem=manual", headers=auth_headers))["items"]
        todos = get_success_data(client.get(base, headers=auth_headers))["items"]
        assert [e["id"] for e in djen_] == [evento_djen["id"]]
        assert djen_[0]["id_djen_comunicacao"] == evento_djen["id_djen_comunicacao"]
        assert djen_[0]["djen_ativa"] is True
        assert all(e["origem"] == "manual" for e in manual) and manual
        assert len(todos) == len(djen_) + len(manual)
        assert client.get(f"{base}?origem=outra", headers=auth_headers).status_code == 400

    def test_eventos_continuam_visiveis_com_o_djen_desligado(
        self, client, auth_headers, caso_com_equipe, evento_djen
    ):
        ligar_djen(TENANT_DAJ, False)
        r = client.get(f"/api/caso/{caso_com_equipe}/eventos/{evento_djen['id']}", headers=auth_headers)
        assert r.status_code == 200
        assert get_success_data(r)["origem"] == "djen"

    def test_estagiario_ve_o_evento_no_caso(self, client, caso_com_equipe, evento_djen):
        h = headers_para(client, "estag.djen@gl.com", SENHA)
        r = client.get(f"/api/caso/{caso_com_equipe}/eventos/{evento_djen['id']}", headers=h)
        assert r.status_code == 200
        assert get_success_data(r)["origem"] == "djen"
