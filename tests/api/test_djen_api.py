"""DJEN: chave por NPJ, captura, rotina, rotas de leitura e permissões.

Sem rede: o transporte do cliente é trocado por `TransporteFalso`, com
respostas sintéticas (nomes e números inventados).
"""

import itertools
import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import select

from gestaolegal.config import Config
from gestaolegal.database import session as db_session_module
from gestaolegal.database.tables import djen_comunicacoes, djen_sincronizacoes, processos
from gestaolegal.integrations import djen_client
from gestaolegal.utils.request_context import sem_tenant

from .conftest import (
    TENANT_DAJ,
    TENANT_OUTRO,
    UNIDADE_OUTRO,
    criar_usuario,
    get_success_data,
    headers_para,
)
from .djen_fixtures import TransporteFalso, item_djen, ligar_djen, limpar_djen

_seq = itertools.count(1)


def numero_cnj_novo() -> str:
    """Número CNJ fictício e único por teste (unicidade de processos.numero)."""
    n = next(_seq)
    return f"{9000000 + n:07d}112026813{n:04d}"


def mascara(numero: str) -> str:
    d = numero
    return f"{d[:7]}-{d[7:9]}.{d[9:13]}.{d[13]}.{d[14:16]}.{d[16:]}"


@pytest.fixture
def transporte() -> TransporteFalso:
    falso = TransporteFalso()
    anterior = djen_client._transporte
    djen_client.definir_transporte(falso)
    yield falso
    djen_client.definir_transporte(anterior)


@pytest.fixture
def djen(app: Flask):
    """DJEN ligado para a DAJ; tudo limpo no fim."""
    with app.app_context():
        limpar_djen()
        ligar_djen(TENANT_DAJ)
    yield
    with app.app_context():
        limpar_djen()


@pytest.fixture
def sync_habilitado(monkeypatch):
    monkeypatch.setattr(Config, "DJEN_SYNC_ENABLED", True)


def _me(client, h) -> dict:
    return get_success_data(client.get("/api/user/me", headers=h))


def criar_caso(client, h, **extra) -> int:
    me = _me(client, h)
    corpo = {
        "id_usuario_responsavel": me["id"],
        "area_direito": "civel",
        "situacao_deferimento": "deferido",
        "ids_clientes": [],
        **extra,
    }
    r = client.post("/api/caso/", json=corpo, headers=h)
    assert r.status_code == 201, r.get_json()
    return get_success_data(r)["id"]


def criar_processo(client, h, caso_id: int, numero: str | None = None) -> dict:
    r = client.post(
        f"/api/caso/{caso_id}/processos",
        json={"especie": "Ação", "numero": numero or mascara(numero_cnj_novo()), "status": True},
        headers=h,
    )
    assert r.status_code == 201, r.get_json()
    return get_success_data(r)


def _linhas(tabela, **filtro):
    session = db_session_module.get_session()
    try:
        with sem_tenant("teste: leitura direta"):
            stmt = select(tabela)
            for coluna, valor in filtro.items():
                stmt = stmt.where(tabela.c[coluna] == valor)
            return [dict(r) for r in session.execute(stmt).mappings()]
    finally:
        session.close()


def rodar_rotina(app: Flask, **kwargs) -> dict:
    from gestaolegal.cli import sincronizar_djen

    with app.app_context():
        return sincronizar_djen(echo=lambda *_: None, **kwargs)


# --------------------------------------------------------------------------- #
# Processos: numero_cnj e pendência
# --------------------------------------------------------------------------- #


class TestProcessoCNJ:
    def test_cadastro_calcula_numero_cnj_e_marca_pendente(self, client, auth_headers):
        caso = criar_caso(client, auth_headers)
        numero = numero_cnj_novo()
        p = criar_processo(client, auth_headers, caso, mascara(numero))
        assert p["numero_cnj"] == numero
        assert p["djen_pendente"] is True
        assert p["djen_consultado_em"] is None

    def test_numero_fora_do_padrao_nao_marca(self, client, auth_headers):
        caso = criar_caso(client, auth_headers)
        p = criar_processo(client, auth_headers, caso, f"ANTIGO-{next(_seq)}")
        assert p["numero_cnj"] is None
        assert p["djen_pendente"] is False

    def test_alterar_numero_marca_de_novo(self, client, auth_headers):
        caso = criar_caso(client, auth_headers)
        p = criar_processo(client, auth_headers, caso, f"ANTIGO-{next(_seq)}")
        novo = numero_cnj_novo()
        r = client.put(
            f"/api/caso/{caso}/processos/{p['id']}",
            json={"numero": mascara(novo)},
            headers=auth_headers,
        )
        dados = get_success_data(r)
        assert dados["numero_cnj"] == novo
        assert dados["djen_pendente"] is True

    def test_editar_outro_campo_nao_mexe_na_pendencia(self, client, auth_headers):
        caso = criar_caso(client, auth_headers)
        p = criar_processo(client, auth_headers, caso, f"ANTIGO-{next(_seq)}")
        r = client.put(
            f"/api/caso/{caso}/processos/{p['id']}", json={"obs": "x"}, headers=auth_headers
        )
        assert get_success_data(r)["djen_pendente"] is False


# --------------------------------------------------------------------------- #
# Chave por NPJ
# --------------------------------------------------------------------------- #


class TestChave:
    def test_me_informa_djen_ativo(self, client, auth_headers, djen):
        assert _me(client, auth_headers)["tenant"]["djen_ativo"] is True
        ligar_djen(TENANT_DAJ, False)
        assert _me(client, auth_headers)["tenant"]["djen_ativo"] is False

    @pytest.mark.parametrize(
        "metodo,url",
        [
            ("GET", "/api/djen/publicacoes"),
            ("GET", "/api/djen/publicacoes/1"),
            ("GET", "/api/djen/status"),
            ("POST", "/api/processos/1/djen/buscar"),
            ("POST", "/api/djen/sincronizar"),
        ],
    )
    def test_rotas_dao_403_com_djen_desligado(self, client, auth_headers, app, metodo, url):
        with app.app_context():
            limpar_djen()
        r = client.open(url, method=metodo, headers=auth_headers)
        assert r.status_code == 403, r.get_json()

    def test_desligar_nao_apaga_publicacoes(self, client, auth_headers, djen, transporte):
        caso = criar_caso(client, auth_headers)
        p = criar_processo(client, auth_headers, caso)
        transporte.por_processo[p["numero_cnj"]] = [item_djen(5001, p["numero_cnj"])]
        assert client.post(f"/api/processos/{p['id']}/djen/buscar", headers=auth_headers).status_code == 200
        ligar_djen(TENANT_DAJ, False)
        assert client.get("/api/djen/publicacoes", headers=auth_headers).status_code == 403
        assert len(_linhas(djen_comunicacoes, id_djen=5001)) == 1
        ligar_djen(TENANT_DAJ, True)
        lista = get_success_data(client.get("/api/djen/publicacoes", headers=auth_headers))
        assert [i["id_processo"] for i in lista["items"]] == [p["id"]]


# --------------------------------------------------------------------------- #
# Busca pelo número do processo (botão)
# --------------------------------------------------------------------------- #


class TestBuscarProcesso:
    def test_busca_grava_vincula_e_limpa_pendencia(self, client, auth_headers, djen, transporte):
        caso = criar_caso(client, auth_headers)
        p = criar_processo(client, auth_headers, caso)
        numero = p["numero_cnj"]
        transporte.por_processo[numero] = [item_djen(6001, numero), item_djen(6002, numero, data="2026-11-04")]
        r = client.post(f"/api/processos/{p['id']}/djen/buscar", headers=auth_headers)
        assert r.status_code == 200, r.get_json()
        dados = get_success_data(r)
        assert dados["novas"] == 2 and dados["vinculadas"] == 2
        assert dados["djen_consultado_em"] is not None
        (linha,) = _linhas(processos, id=p["id"])
        assert linha["djen_pendente"] is False

        gravadas = _linhas(djen_comunicacoes, id_processo=p["id"])
        assert {g["id_djen"] for g in gravadas} == {6001, 6002}
        for g in gravadas:
            assert g["situacao"] == "vinculada"
            assert g["id_caso"] == caso
            assert g["unidade_id"] == 1
            assert g["tenant_id"] == TENANT_DAJ
            assert "Comic Sans" not in g["texto_plano"]

    def test_busca_e_idempotente(self, client, auth_headers, djen, transporte):
        caso = criar_caso(client, auth_headers)
        p = criar_processo(client, auth_headers, caso)
        transporte.por_processo[p["numero_cnj"]] = [item_djen(6101, p["numero_cnj"])]
        url = f"/api/processos/{p['id']}/djen/buscar"
        assert get_success_data(client.post(url, headers=auth_headers))["novas"] == 1
        segunda = get_success_data(client.post(url, headers=auth_headers))
        assert segunda["novas"] == 0 and segunda["atualizadas"] == 0
        assert len(_linhas(djen_comunicacoes, id_djen=6101)) == 1

    def test_cancelamento_atualiza_o_registro(self, client, auth_headers, djen, transporte):
        caso = criar_caso(client, auth_headers)
        p = criar_processo(client, auth_headers, caso)
        numero = p["numero_cnj"]
        url = f"/api/processos/{p['id']}/djen/buscar"
        transporte.por_processo[numero] = [item_djen(6201, numero)]
        client.post(url, headers=auth_headers)
        transporte.por_processo[numero] = [
            item_djen(6201, numero, ativo=False, motivo_cancelamento="Publicada por engano")
        ]
        dados = get_success_data(client.post(url, headers=auth_headers))
        assert dados["atualizadas"] == 1 and dados["novas"] == 0
        (linha,) = _linhas(djen_comunicacoes, id_djen=6201)
        assert linha["ativo"] is False
        assert linha["motivo_cancelamento"] == "Publicada por engano"

    def test_numero_fora_do_padrao_da_400(self, client, auth_headers, djen, transporte):
        caso = criar_caso(client, auth_headers)
        p = criar_processo(client, auth_headers, caso, f"ANTIGO-{next(_seq)}")
        r = client.post(f"/api/processos/{p['id']}/djen/buscar", headers=auth_headers)
        assert r.status_code == 400
        assert transporte.chamadas == []

    def test_processo_de_outra_unidade_da_404(self, client, auth_headers, auth_headers_nl, djen, transporte):
        caso = criar_caso(client, auth_headers)
        p = criar_processo(client, auth_headers, caso)
        r = client.post(f"/api/processos/{p['id']}/djen/buscar", headers=auth_headers_nl)
        assert r.status_code == 404
        assert transporte.chamadas == []

    def test_falha_de_rede_da_422_sem_gravar(self, client, auth_headers, djen, transporte):
        caso = criar_caso(client, auth_headers)
        p = criar_processo(client, auth_headers, caso)
        transporte.falhar.add(p["numero_cnj"])
        r = client.post(f"/api/processos/{p['id']}/djen/buscar", headers=auth_headers)
        assert r.status_code == 422
        (linha,) = _linhas(processos, id=p["id"])
        assert linha["djen_pendente"] is True

    @pytest.mark.parametrize("papel", ["colab_proj", "estag_direito", "colab_ext"])
    def test_so_quem_vincula_pode_buscar(self, client, app, djen, transporte, auth_headers, papel):
        caso = criar_caso(client, auth_headers)
        p = criar_processo(client, auth_headers, caso)
        with app.app_context():
            criar_usuario(f"{papel}.djen@gl.com", "senha12345", papel, f"Usuário {papel}")
        h = headers_para(client, f"{papel}.djen@gl.com", "senha12345")
        r = client.post(f"/api/processos/{p['id']}/djen/buscar", headers=h)
        assert r.status_code == 403
        assert transporte.chamadas == []


# --------------------------------------------------------------------------- #
# Rotina (flask djen sincronizar)
# --------------------------------------------------------------------------- #


class TestRotina:
    def test_trava_do_ambiente_desligada_nao_chama_a_api(self, app, client, auth_headers, djen, transporte):
        caso = criar_caso(client, auth_headers)
        criar_processo(client, auth_headers, caso)
        assert rodar_rotina(app) == {}
        assert transporte.chamadas == []
        assert _linhas(djen_sincronizacoes) == []

    def test_rotina_atende_pendentes_e_registra(self, app, client, auth_headers, djen, transporte, sync_habilitado):
        caso = criar_caso(client, auth_headers)
        p = criar_processo(client, auth_headers, caso)
        transporte.por_processo[p["numero_cnj"]] = [item_djen(7001, p["numero_cnj"])]
        resultado = rodar_rotina(app)
        assert resultado["daj-ufmg"] == "ok"
        assert resultado["npj-x"].startswith("pulado")
        (sinc,) = _linhas(djen_sincronizacoes, tenant_id=TENANT_DAJ)
        assert sinc["status"] == "ok"
        assert sinc["novas"] >= 1 and sinc["vinculadas"] >= 1
        assert _linhas(djen_sincronizacoes, tenant_id=TENANT_OUTRO) == []
        (linha,) = _linhas(processos, id=p["id"])
        assert linha["djen_pendente"] is False and linha["djen_consultado_em"] is not None
        # Segunda execução: nada pendente, nada novo.
        transporte.chamadas.clear()
        rodar_rotina(app)
        assert all(c.get("numeroProcesso") != p["numero_cnj"] for c in transporte.chamadas)

    def test_botao_roda_a_rotina_do_proprio_npj(self, client, auth_headers, djen, transporte):
        # Ação manual: não depende de DJEN_SYNC_ENABLED (desligado aqui).
        caso = criar_caso(client, auth_headers)
        p = criar_processo(client, auth_headers, caso)
        transporte.por_processo[p["numero_cnj"]] = [item_djen(7051, p["numero_cnj"])]
        r = client.post("/api/djen/sincronizar", headers=auth_headers)
        d = get_success_data(r)
        assert d["status"] == "ok" and d["novas"] >= 1 and d["vinculadas"] >= 1
        (sinc,) = _linhas(djen_sincronizacoes, tenant_id=TENANT_DAJ)
        assert sinc["status"] == "ok"
        assert _linhas(djen_sincronizacoes, tenant_id=TENANT_OUTRO) == []

        status = get_success_data(client.get("/api/djen/status", headers=auth_headers))
        assert status["ultima"]["status"] == "ok"
        assert status["rotina"] == {
            "janela_dias": Config.DJEN_JANELA_DIAS,
            "max_processos": Config.DJEN_MAX_PROCESSOS,
        }

    @pytest.mark.parametrize("papel", ["prof", "orient", "colab_proj", "estag_direito", "colab_ext"])
    def test_so_admin_roda_a_rotina_pela_tela(self, client, app, djen, transporte, auth_headers, papel):
        caso = criar_caso(client, auth_headers)
        criar_processo(client, auth_headers, caso)
        with app.app_context():
            criar_usuario(f"{papel}.rotina@gl.com", "senha12345", papel, f"Usuário {papel}")
        h = headers_para(client, f"{papel}.rotina@gl.com", "senha12345")
        assert client.post("/api/djen/sincronizar", headers=h).status_code == 403
        assert transporte.chamadas == []
        assert _linhas(djen_sincronizacoes) == []

    def test_respeita_o_maximo_de_processos(self, app, client, auth_headers, djen, transporte, sync_habilitado):
        caso = criar_caso(client, auth_headers)
        for _ in range(3):
            criar_processo(client, auth_headers, caso)
        rodar_rotina(app, max_processos=2)
        assert len([c for c in transporte.chamadas if "numeroProcesso" in c]) == 2

    def test_falha_de_um_processo_deixa_parcial_sem_perder_o_resto(
        self, app, client, auth_headers, djen, transporte, sync_habilitado
    ):
        caso = criar_caso(client, auth_headers)
        bom = criar_processo(client, auth_headers, caso)
        ruim = criar_processo(client, auth_headers, caso)
        transporte.por_processo[bom["numero_cnj"]] = [item_djen(7101, bom["numero_cnj"])]
        transporte.falhar.add(ruim["numero_cnj"])
        assert rodar_rotina(app)["daj-ufmg"] == "parcial"
        assert len(_linhas(djen_comunicacoes, id_djen=7101)) == 1
        (sinc,) = _linhas(djen_sincronizacoes, tenant_id=TENANT_DAJ)
        assert sinc["status"] == "parcial"
        assert f"processo {ruim['id']}" in sinc["mensagem"]
        (linha,) = _linhas(processos, id=ruim["id"])
        assert linha["djen_pendente"] is True  # fica para a próxima

    def test_tudo_falhando_da_erro(self, app, client, auth_headers, djen, transporte, sync_habilitado):
        caso = criar_caso(client, auth_headers)
        p = criar_processo(client, auth_headers, caso)
        transporte.falhar.add(p["numero_cnj"])
        rodar_rotina(app)
        (sinc,) = _linhas(djen_sincronizacoes, tenant_id=TENANT_DAJ)
        assert sinc["status"] in ("erro", "parcial")

    def test_npj_com_djen_desligado_e_pulado_sem_chamar_a_api(
        self, app, client, auth_headers, djen, transporte, sync_habilitado
    ):
        caso = criar_caso(client, auth_headers)
        criar_processo(client, auth_headers, caso)
        ligar_djen(TENANT_DAJ, False)
        resultado = rodar_rotina(app)
        assert resultado["daj-ufmg"] == "pulado: DJEN desligado para o NPJ"
        assert transporte.chamadas == []
        assert _linhas(djen_sincronizacoes) == []

    def test_falha_de_um_npj_nao_interrompe_os_outros(
        self, app, client, auth_headers, djen, transporte, sync_habilitado, monkeypatch
    ):
        from gestaolegal.services import djen_service

        ligar_djen(TENANT_OUTRO, True)
        original = djen_service.DJENService.sincronizar
        visitados = []

        def sincronizar(self, *a, **k):
            tenant = self.repo.tenant_id()
            visitados.append(tenant)
            if tenant == TENANT_DAJ:
                raise RuntimeError("falha simulada")
            return original(self, *a, **k)

        monkeypatch.setattr(djen_service.DJENService, "sincronizar", sincronizar)
        resultado = rodar_rotina(app)
        assert visitados == [TENANT_DAJ, TENANT_OUTRO]
        assert resultado["daj-ufmg"] == "falhou"
        assert resultado["npj-x"] == "ok"
        (sinc,) = _linhas(djen_sincronizacoes, tenant_id=TENANT_OUTRO)
        assert sinc["status"] == "ok"

    def test_tenant_unico(self, app, djen, transporte, sync_habilitado):
        resultado = rodar_rotina(app, slug="daj-ufmg")
        assert list(resultado) == ["daj-ufmg"]


# --------------------------------------------------------------------------- #
# Lista, detalhe, status e permissões
# --------------------------------------------------------------------------- #


@pytest.fixture
def publicacao(client, auth_headers, djen, transporte) -> dict:
    """Uma publicação vinculada a um caso da DAJ em BH."""
    caso = criar_caso(client, auth_headers)
    p = criar_processo(client, auth_headers, caso)
    transporte.por_processo[p["numero_cnj"]] = [item_djen(8001, p["numero_cnj"])]
    client.post(f"/api/processos/{p['id']}/djen/buscar", headers=auth_headers)
    (linha,) = _linhas(djen_comunicacoes, id_djen=8001)
    return {"id": linha["id"], "caso": caso, "processo": p}


class TestLeitura:
    def test_lista_e_detalhe(self, client, auth_headers, publicacao):
        lista = get_success_data(client.get("/api/djen/publicacoes", headers=auth_headers))
        (item,) = lista["items"]
        assert item["id"] == publicacao["id"]
        assert item["id_caso"] == publicacao["caso"]
        assert item["numero_processo_mascara"] == mascara(publicacao["processo"]["numero_cnj"])
        assert item["situacao"] == "vinculada"
        assert "texto_html" not in item

        r = client.get(f"/api/djen/publicacoes/{publicacao['id']}", headers=auth_headers)
        d = get_success_data(r)
        assert "texto_html" not in d and "texto_plano" not in d
        assert "<b>intimada</b>" in d["texto_html_seguro"]
        assert "alert" not in d["texto_html_seguro"]
        assert d["link_certidao"].endswith("/api/v1/comunicacao/hashficticio8001/certidao")
        assert {x["polo"] for x in d["destinatarios"]} == {"A", "P"}
        assert d["advogados"][0]["numero_oab"] == "123456"
        assert d["pode_vincular"] is True

    @pytest.mark.parametrize(
        "query,esperado",
        [
            ("tribunal=TJMG", 1),
            ("tribunal=TRF6", 0),
            ("tipo=Intima%C3%A7%C3%A3o", 1),
            ("inicio=2026-11-04", 0),
            ("fim=2026-11-03", 1),
            ("q=prazo", 1),
            ("q=inexistente", 0),
            ("situacao=vinculada", 1),
            ("situacao=pendente", 0),
        ],
    )
    def test_filtros(self, client, auth_headers, publicacao, query, esperado):
        lista = get_success_data(client.get(f"/api/djen/publicacoes?{query}", headers=auth_headers))
        assert lista["total"] == esperado

    def test_filtro_por_caso_e_numero(self, client, auth_headers, publicacao):
        q = f"caso_id={publicacao['caso']}"
        assert get_success_data(client.get(f"/api/djen/publicacoes?{q}", headers=auth_headers))["total"] == 1
        digitos = publicacao["processo"]["numero_cnj"][:9]
        assert get_success_data(client.get(f"/api/djen/publicacoes?q={digitos}", headers=auth_headers))["total"] == 1

    def test_data_invalida_da_400(self, client, auth_headers, publicacao):
        assert client.get("/api/djen/publicacoes?inicio=ontem", headers=auth_headers).status_code == 400

    def test_outra_unidade_nao_ve(self, client, auth_headers_nl, publicacao):
        lista = get_success_data(client.get("/api/djen/publicacoes", headers=auth_headers_nl))
        assert lista["total"] == 0
        r = client.get(f"/api/djen/publicacoes/{publicacao['id']}", headers=auth_headers_nl)
        assert r.status_code == 404

    def test_status_sem_sincronizacao(self, client, auth_headers, djen):
        d = get_success_data(client.get("/api/djen/status", headers=auth_headers))
        assert d["ultima"] is None and d["atrasada"] is True

    def test_status_com_sincronizacao(self, app, client, auth_headers, djen, transporte, sync_habilitado):
        rodar_rotina(app)
        d = get_success_data(client.get("/api/djen/status", headers=auth_headers))
        assert d["ultima"]["status"] == "ok"
        assert d["atrasada"] is False
        assert "tribunais" in d["filtros"]


class TestPermissoes:
    def _headers(self, client, app, papel):
        email = f"{papel}.leitura.djen@gl.com"
        with app.app_context():
            uid = criar_usuario(email, "senha12345", papel, f"Leitor {papel}")
        return uid, headers_para(client, email, "senha12345")

    @pytest.mark.parametrize("papel", ["prof", "orient", "colab_proj"])
    def test_papeis_da_unidade_veem_tudo_vinculado(self, client, app, publicacao, papel):
        _, h = self._headers(client, app, papel)
        assert get_success_data(client.get("/api/djen/publicacoes", headers=h))["total"] == 1
        assert client.get(f"/api/djen/publicacoes/{publicacao['id']}", headers=h).status_code == 200

    @pytest.mark.parametrize("papel", ["estag_direito", "colab_ext"])
    def test_participante_so_ve_os_seus_casos(self, client, app, auth_headers, publicacao, papel):
        uid, h = self._headers(client, app, papel)
        assert get_success_data(client.get("/api/djen/publicacoes", headers=h))["total"] == 0
        assert client.get(f"/api/djen/publicacoes/{publicacao['id']}", headers=h).status_code == 404
        # Entra no caso como colaborador: passa a ver.
        r = client.put(
            f"/api/caso/{publicacao['caso']}",
            json={"id_colaborador": uid},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.get_json()
        assert get_success_data(client.get("/api/djen/publicacoes", headers=h))["total"] == 1
        d = get_success_data(client.get(f"/api/djen/publicacoes/{publicacao['id']}", headers=h))
        assert d["pode_vincular"] is False

    @pytest.mark.parametrize("papel", ["colab_proj", "estag_direito", "colab_ext"])
    def test_sem_caso_e_so_de_quem_vincula(self, client, app, djen, papel):
        _, h = self._headers(client, app, papel)
        r = client.get("/api/djen/publicacoes?situacao=pendente", headers=h)
        assert r.status_code == 403


# --------------------------------------------------------------------------- #
# Área da plataforma
# --------------------------------------------------------------------------- #


class TestPlataforma:
    @pytest.fixture
    def ph(self, app, client):
        from gestaolegal.services.plataforma_service import PlataformaService

        with app.test_request_context():
            try:
                PlataformaService().criar_admin("Plataforma DJEN", "plataforma.djen@exemplo.test", "12345678")
                db_session_module.get_session().commit()
            except Exception:
                db_session_module.get_session().rollback()
        r = client.post(
            "/api/plataforma/auth/login",
            json={"email": "plataforma.djen@exemplo.test", "password": "12345678"},
        )
        return {"Authorization": f"Bearer {get_success_data(r)['token']}"}

    def test_admin_da_plataforma_liga_e_desliga(self, app, client, ph, auth_headers):
        with app.app_context():
            limpar_djen()
        assert get_success_data(client.get(f"/api/plataforma/tenants/{TENANT_DAJ}", headers=ph))["djen_ativo"] is False
        r = client.put(f"/api/plataforma/tenants/{TENANT_DAJ}", json={"djen_ativo": True}, headers=ph)
        assert get_success_data(r)["djen_ativo"] is True
        assert _me(client, auth_headers)["tenant"]["djen_ativo"] is True
        lista = get_success_data(client.get("/api/plataforma/tenants", headers=ph))["items"]
        assert {t["id"]: t["djen_ativo"] for t in lista}[TENANT_DAJ] is True
        r = client.put(f"/api/plataforma/tenants/{TENANT_DAJ}", json={"djen_ativo": False}, headers=ph)
        assert get_success_data(r)["djen_ativo"] is False

    def test_valor_invalido(self, client, ph):
        r = client.put(f"/api/plataforma/tenants/{TENANT_DAJ}", json={"djen_ativo": "sim"}, headers=ph)
        assert r.status_code == 400

    def test_token_de_npj_nao_altera_a_chave(self, app, client, auth_headers):
        with app.app_context():
            limpar_djen()
        r = client.put(f"/api/plataforma/tenants/{TENANT_DAJ}", json={"djen_ativo": True}, headers=auth_headers)
        assert r.status_code == 401
        assert _me(client, auth_headers)["tenant"]["djen_ativo"] is False


# --------------------------------------------------------------------------- #
# Tenants
# --------------------------------------------------------------------------- #


@pytest.fixture
def headers_outro(client, app):
    # A mesma conta dos testes de isolamento: eles contam os usuários do NPJ.
    from .test_tenant_isolamento import OUTRO_EMAIL, OUTRO_SENHA

    with app.app_context():
        criar_usuario(OUTRO_EMAIL, OUTRO_SENHA, "admin", "Admin Outro NPJ", tenant_id=TENANT_OUTRO)
    return headers_para(client, OUTRO_EMAIL, OUTRO_SENHA, unidade=UNIDADE_OUTRO)


class TestTenants:
    def test_mesma_publicacao_em_dois_npjs_vira_dois_registros(
        self, client, auth_headers, headers_outro, djen, transporte
    ):
        ligar_djen(TENANT_OUTRO, True)
        numero = numero_cnj_novo()
        caso_daj = criar_caso(client, auth_headers)
        p_daj = criar_processo(client, auth_headers, caso_daj, mascara(numero))
        caso_outro = criar_caso(client, headers_outro)
        p_outro = criar_processo(client, headers_outro, caso_outro, mascara(numero))
        transporte.por_processo[numero] = [item_djen(9001, numero)]
        client.post(f"/api/processos/{p_daj['id']}/djen/buscar", headers=auth_headers)
        client.post(f"/api/processos/{p_outro['id']}/djen/buscar", headers=headers_outro)
        linhas = _linhas(djen_comunicacoes, id_djen=9001)
        assert {(r["tenant_id"], r["id_processo"]) for r in linhas} == {
            (TENANT_DAJ, p_daj["id"]),
            (TENANT_OUTRO, p_outro["id"]),
        }
        lista_outro = get_success_data(client.get("/api/djen/publicacoes", headers=headers_outro))
        assert [i["id_processo"] for i in lista_outro["items"]] == [p_outro["id"]]
        daj_id = next(r["id"] for r in linhas if r["tenant_id"] == TENANT_DAJ)
        assert client.get(f"/api/djen/publicacoes/{daj_id}", headers=headers_outro).status_code == 404

    def test_casamento_nao_cruza_npjs(self, app, client, auth_headers, headers_outro, djen, transporte, sync_habilitado):
        # O processo existe só na DAJ; a rotina do outro NPJ não casa com ele.
        ligar_djen(TENANT_OUTRO, True)
        numero = numero_cnj_novo()
        caso_daj = criar_caso(client, auth_headers)
        criar_processo(client, auth_headers, caso_daj, mascara(numero))
        from gestaolegal.services.djen_service import DJENService
        from gestaolegal.models.djen import ResultadoCaptura
        from gestaolegal.integrations.djen_client import converter_item
        from gestaolegal.utils.request_context import contexto_tenant

        with app.test_request_context():
            with contexto_tenant(TENANT_OUTRO):
                service = DJENService()
                resultado = ResultadoCaptura()
                service.registrar(converter_item(item_djen(9101, numero)), resultado, unidade_padrao=UNIDADE_OUTRO)
                service.session.commit()
        (linha,) = _linhas(djen_comunicacoes, id_djen=9101)
        assert linha["tenant_id"] == TENANT_OUTRO
        assert linha["id_processo"] is None and linha["situacao"] == "pendente"
        assert linha["unidade_id"] == UNIDADE_OUTRO
