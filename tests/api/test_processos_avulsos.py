"""Processos sem caso, parte sem triagem, lista geral e busca por parte no DJEN.

docs/plano-processos-avulsos.md. Sem rede: o DJEN responde pelo
`TransporteFalso` (nomes e números inventados).
"""

import itertools

import pytest
from flask import Flask
from sqlalchemy import select

from gestaolegal.database import session as db_session_module
from gestaolegal.database.tables import (
    assistidos,
    casos,
    casos_atendidos,
    atendido_nomes,
    atendidos,
    djen_comunicacoes,
    eventos,
    notificacao,
    processo_partes,
    processos,
)
from gestaolegal.services.djen_service import PAPEIS_UNIDADE
from gestaolegal.services.processo_service import PAPEIS_SEM_CASO
from gestaolegal.utils.request_context import sem_tenant

from .conftest import (
    UNIDADE_BH,
    UNIDADE_NL,
    criar_usuario,
    get_success_data,
    headers_para,
)
from .djen_fixtures import item_djen
from .test_djen_api import (  # noqa: F401  (fixtures)
    _linhas,
    criar_caso,
    djen,
    mascara,
    numero_cnj_novo,
    rodar_rotina,
    sync_habilitado,
    transporte,
)

SENHA = "senha12345"
_seq = itertools.count(1)


def _unico(prefixo: str) -> str:
    return f"{prefixo} {next(_seq):04d}"


@pytest.fixture(scope="module", autouse=True)
def _sem_sobras(app: Flask):
    """Remove, ao fim do módulo, fichas e vínculos criados aqui.

    Outros módulos limpam `atendidos` sem limpar `assistidos`; o SQLite reusa
    o id, e uma ficha que sobrasse daqui passaria a pertencer a um atendido
    novo de outro teste.
    """
    tabelas = (processo_partes, atendido_nomes, assistidos)
    session = db_session_module.get_session()
    try:
        with sem_tenant("teste: registros anteriores"):
            # O banco SQLite compartilhado reusa IDs removidos por outros
            # módulos. Remover referências órfãs ANTES de criar os cenários,
            # para um caso novo não herdar processos/partes de outro teste.
            session.execute(processos.delete().where(
                processos.c.id_caso.is_not(None),
                ~select(casos.c.id).where(casos.c.id == processos.c.id_caso).exists(),
            ))
            session.execute(casos_atendidos.delete().where(
                ~select(casos.c.id).where(casos.c.id == casos_atendidos.c.id_caso).exists()
                | ~select(atendidos.c.id).where(atendidos.c.id == casos_atendidos.c.id_atendido).exists()
            ))
            session.commit()
            anteriores = {t.name: set(session.execute(select(t.c.id)).scalars()) for t in tabelas}
    finally:
        session.close()
    yield
    session = db_session_module.get_session()
    try:
        with sem_tenant("teste: limpeza dos registros do módulo"):
            for tabela in tabelas:
                session.execute(tabela.delete().where(tabela.c.id.not_in(anteriores[tabela.name])))
            session.commit()
    finally:
        session.close()


@pytest.fixture
def papeis(client, app: Flask) -> dict[str, dict]:
    """Um usuário de cada papel, na unidade BH: {papel: {"id", "h"}}."""
    resultado = {}
    with app.app_context():
        for papel in ("prof", "orient", "colab_proj", "estag_direito", "colab_ext"):
            email = f"{papel}.avulso@gl.com"
            uid = criar_usuario(email, SENHA, papel, f"Usuário {papel} avulso")
            resultado[papel] = {"id": uid, "h": headers_para(client, email, SENHA)}
    return resultado


def parte(client, h, nome: str | None = None, **extra) -> dict:
    r = client.post(
        "/api/atendido/simplificado", json={"nome": nome or _unico("Parte Fictícia"), **extra}, headers=h
    )
    assert r.status_code == 201, r.get_json()
    return get_success_data(r)


def processo_sem_caso(client, h, ids_partes: list[int], **extra) -> dict:
    corpo = {
        "especie": "Ação",
        "numero": mascara(numero_cnj_novo()),
        "partes": [{"id_atendido": p} for p in ids_partes],
        **extra,
    }
    r = client.post("/api/processos", json=corpo, headers=h)
    assert r.status_code == 201, r.get_json()
    return get_success_data(r)


def listar(client, h, **filtros) -> dict:
    r = client.get("/api/processos", query_string={"per_page": 100, **filtros}, headers=h)
    assert r.status_code == 200, r.get_json()
    return get_success_data(r)


def ids(lista: dict) -> set[int]:
    return {p["id"] for p in lista["items"]}


def test_papeis_iguais_aos_da_lista_do_djen():
    # O plano manda usar a mesma régua da gestão do DJEN.
    assert set(PAPEIS_SEM_CASO) == set(PAPEIS_UNIDADE)


# --------------------------------------------------------------------------- #
# Cadastro simplificado e variações do nome
# --------------------------------------------------------------------------- #


class TestParteSemTriagem:
    def test_cadastro_simplificado(self, client, auth_headers):
        a = parte(client, auth_headers, cpf="12345678901", obs="Procuradoria")
        assert a["sem_triagem"] is True
        assert a["cpf"] == "123.456.789-01"
        assert a["unidade_id"] == UNIDADE_BH
        assert a["data_nascimento"] is None and a["email"] is None and a["celular"] is None
        assert a["assistido"] is None
        ficha = get_success_data(client.get(f"/api/atendido/{a['id']}", headers=auth_headers))
        assert ficha["sem_triagem"] is True and ficha["obs"] == "Procuradoria"
        # Conta como assistido na lista, sem ter ficha de assistido.
        lista = get_success_data(
            client.get(
                "/api/atendido/",
                query_string={"search": a["nome"], "tipo_busca": "assistidos"},
                headers=auth_headers,
            )
        )
        (item,) = lista["items"]
        assert item["is_assistido"] is True and item["sem_triagem"] is True

    def test_cnpj(self, client, auth_headers):
        a = parte(client, auth_headers, nome="Universidade Fictícia", cnpj="17.217.985/0001-04")
        assert a["cnpj"] == "17.217.985/0001-04" and a["cpf"] is None

    @pytest.mark.parametrize(
        "corpo",
        [{"nome": ""}, {"nome": "   "}, {}, {"nome": "X", "cpf": "123"}, {"nome": "X", "cnpj": "1"}],
    )
    def test_validacao(self, client, auth_headers, corpo):
        antes = len(_linhas(atendidos))
        assert client.post("/api/atendido/simplificado", json=corpo, headers=auth_headers).status_code == 400
        assert len(_linhas(atendidos)) == antes

    @pytest.mark.parametrize("papel", ["estag_direito", "colab_ext"])
    def test_so_papeis_da_unidade_cadastram(self, client, papeis, papel):
        r = client.post("/api/atendido/simplificado", json={"nome": "Não pode"}, headers=papeis[papel]["h"])
        assert r.status_code == 403

    def test_cadastro_normal_continua_exigindo_os_campos(self, client, auth_headers):
        r = client.post("/api/atendido/", json={"nome": "Sem o resto"}, headers=auth_headers)
        assert r.status_code == 400

    def test_triagem_depois_encerra_o_sem_triagem(self, client, auth_headers):
        from .test_tenant_vazamento import _assistido

        a = parte(client, auth_headers)
        r = client.post(f"/api/atendido/{a['id']}/tornar-assistido", json=_assistido({}), headers=auth_headers)
        assert r.status_code == 200, r.get_json()
        dados = get_success_data(r)
        assert dados["id"] == a["id"] and dados["sem_triagem"] is False
        assert dados["assistido"] is not None


class TestNomes:
    def test_adicionar_listar_remover(self, client, auth_headers):
        a = parte(client, auth_headers)
        url = f"/api/atendido/{a['id']}/nomes"
        r = client.post(url, json={"nome": "  UFMG  "}, headers=auth_headers)
        assert r.status_code == 201
        client.post(url, json={"nome": "Univ. Fed. de Minas"}, headers=auth_headers)
        nomes = get_success_data(client.get(url, headers=auth_headers))
        assert [n["nome"] for n in nomes] == ["UFMG", "Univ. Fed. de Minas"]
        # Repetido (sem diferenciar caixa) ou igual ao nome principal: 400.
        assert client.post(url, json={"nome": "ufmg"}, headers=auth_headers).status_code == 400
        assert client.post(url, json={"nome": a["nome"]}, headers=auth_headers).status_code == 400
        assert client.post(url, json={"nome": ""}, headers=auth_headers).status_code == 400
        r = client.delete(f"{url}/{nomes[0]['id']}", headers=auth_headers)
        assert r.status_code == 200
        assert [n["nome"] for n in get_success_data(client.get(url, headers=auth_headers))] == [
            "Univ. Fed. de Minas"
        ]
        assert client.delete(f"{url}/{nomes[0]['id']}", headers=auth_headers).status_code == 404

    def test_outra_unidade_nao_ve(self, client, auth_headers, auth_headers_nl):
        a = parte(client, auth_headers)
        url = f"/api/atendido/{a['id']}/nomes"
        assert client.get(url, headers=auth_headers_nl).status_code == 404
        assert client.post(url, json={"nome": "Outro"}, headers=auth_headers_nl).status_code == 404

    def test_estagiario_le_mas_nao_altera(self, client, auth_headers, papeis):
        a = parte(client, auth_headers)
        url = f"/api/atendido/{a['id']}/nomes"
        h = papeis["estag_direito"]["h"]
        assert client.get(url, headers=h).status_code == 200
        assert client.post(url, json={"nome": "Outro"}, headers=h).status_code == 403


# --------------------------------------------------------------------------- #
# Processo sem caso
# --------------------------------------------------------------------------- #


class TestProcessoSemCaso:
    def test_cria_com_partes_na_unidade_ativa(self, client, auth_headers):
        a, b = parte(client, auth_headers), parte(client, auth_headers)
        numero = numero_cnj_novo()
        p = processo_sem_caso(
            client,
            auth_headers,
            [a["id"]],
            numero=mascara(numero),
            partes=[{"id_atendido": a["id"], "polo": "passivo"}, {"id_atendido": b["id"]}],
        )
        assert p["id_caso"] is None
        assert p["unidade_id"] == UNIDADE_BH
        assert p["numero_cnj"] == numero and p["djen_pendente"] is True
        assert [(x["id_atendido"], x["polo"], x["origem"]) for x in p["partes"]] == [
            (a["id"], "passivo", "processo"),
            (b["id"], None, "processo"),
        ]
        assert all(x["sem_triagem"] for x in p["partes"])

    def test_colab_proj_cadastra(self, client, auth_headers, papeis):
        a = parte(client, auth_headers)
        assert processo_sem_caso(client, papeis["colab_proj"]["h"], [a["id"]])["id_caso"] is None

    @pytest.mark.parametrize("papel", ["estag_direito", "colab_ext"])
    def test_estagiario_e_colab_ext_nao_cadastram(self, client, auth_headers, papeis, papel):
        a = parte(client, auth_headers)
        r = client.post(
            "/api/processos",
            json={"especie": "Ação", "partes": [{"id_atendido": a["id"]}]},
            headers=papeis[papel]["h"],
        )
        assert r.status_code == 403

    def test_validacoes(self, client, auth_headers, auth_headers_nl):
        a = parte(client, auth_headers)
        de_nl = parte(client, auth_headers_nl)
        antes = len(_linhas(processos))
        for corpo in (
            {"especie": "Ação", "partes": []},
            {"especie": "Ação"},
            {"especie": "Ação", "partes": [{"id_atendido": 987654}]},
            # Parte de outra unidade: mesma resposta de um id inexistente.
            {"especie": "Ação", "partes": [{"id_atendido": de_nl["id"]}]},
            {"especie": "Ação", "partes": [{"id_atendido": a["id"], "polo": "x"}]},
            {"especie": "Ação", "id_caso": 1, "partes": [{"id_atendido": a["id"]}]},
        ):
            r = client.post("/api/processos", json=corpo, headers=auth_headers)
            assert r.status_code == 400, (corpo, r.get_json())
        assert len(_linhas(processos)) == antes

    def test_numero_repetido(self, client, auth_headers):
        a = parte(client, auth_headers)
        p = processo_sem_caso(client, auth_headers, [a["id"]])
        r = client.post(
            "/api/processos",
            json={"especie": "Ação", "numero": p["numero"], "partes": [{"id_atendido": a["id"]}]},
            headers=auth_headers,
        )
        assert r.status_code == 400
        assert r.get_json()["error"]["details"]["field"] == "numero"

    def test_editar_partes_e_campos(self, client, auth_headers):
        a, b = parte(client, auth_headers), parte(client, auth_headers)
        p = processo_sem_caso(client, auth_headers, [a["id"]])
        r = client.put(
            f"/api/processos/{p['id']}",
            json={"vara": "2ª Vara Fictícia", "partes": [{"id_atendido": b["id"], "polo": "ativo"}]},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.get_json()
        d = get_success_data(r)
        assert d["vara"] == "2ª Vara Fictícia"
        assert [(x["id_atendido"], x["polo"]) for x in d["partes"]] == [(b["id"], "ativo")]
        for corpo in ({"partes": []}, {"id_caso": 1}):
            assert client.put(f"/api/processos/{p['id']}", json=corpo, headers=auth_headers).status_code == 400

    def test_excluir(self, client, auth_headers, papeis):
        a = parte(client, auth_headers)
        p = processo_sem_caso(client, auth_headers, [a["id"]])
        assert client.delete(f"/api/processos/{p['id']}", headers=papeis["orient"]["h"]).status_code == 200
        (linha,) = _linhas(processos, id=p["id"])
        assert linha["status"] is False or linha["status"] == 0

    def test_processo_de_caso_pela_rota_geral(self, client, auth_headers, papeis):
        a = parte(client, auth_headers)
        caso = criar_caso(client, auth_headers, ids_clientes=[a["id"]])
        r = client.post(
            f"/api/caso/{caso}/processos", json={"especie": "Ação", "status": True}, headers=auth_headers
        )
        p = get_success_data(r)
        assert p["unidade_id"] == UNIDADE_BH
        d = get_success_data(client.get(f"/api/processos/{p['id']}", headers=auth_headers))
        assert d["id_caso"] == caso
        assert [(x["id_atendido"], x["origem"]) for x in d["partes"]] == [(a["id"], "caso")]
        # As partes do processo de caso vêm do caso; o resto se edita aqui.
        r = client.put(f"/api/processos/{p['id']}", json={"partes": [{"id_atendido": a["id"]}]}, headers=auth_headers)
        assert r.status_code == 400
        r = client.put(f"/api/processos/{p['id']}", json={"obs": "Editado"}, headers=auth_headers)
        assert get_success_data(r)["obs"] == "Editado"
        # Excluir processo de caso continua só para admin, como na rota do caso.
        assert client.delete(f"/api/processos/{p['id']}", headers=papeis["orient"]["h"]).status_code == 403
        assert client.delete(f"/api/processos/{p['id']}", headers=auth_headers).status_code == 200


# --------------------------------------------------------------------------- #
# Lista geral: filtros, papéis e unidade
# --------------------------------------------------------------------------- #


@pytest.fixture
def cenario_lista(client, auth_headers, papeis):
    """Um processo sem caso, um de caso do estagiário e um de caso alheio."""
    marca = _unico("Lista")
    sem = parte(client, auth_headers, nome=f"{marca} Universidade")
    client.post(f"/api/atendido/{sem['id']}/nomes", json={"nome": f"{marca} UNIV"}, headers=auth_headers)
    cliente = parte(client, auth_headers, nome=f"{marca} Cliente do caso")
    p_sem = processo_sem_caso(client, auth_headers, [sem["id"]], data_distribuicao="2026-03-10")

    caso_estag = criar_caso(
        client, auth_headers, ids_clientes=[cliente["id"]], id_estagiario=papeis["estag_direito"]["id"]
    )
    caso_alheio = criar_caso(client, auth_headers, ids_clientes=[cliente["id"]])

    def de_caso(caso, **extra):
        corpo = {"especie": "Recurso", "numero": mascara(numero_cnj_novo()), "status": True, **extra}
        r = client.post(f"/api/caso/{caso}/processos", json=corpo, headers=auth_headers)
        assert r.status_code == 201, r.get_json()
        return get_success_data(r)

    p_estag = de_caso(caso_estag, data_distribuicao="2026-05-20")
    p_alheio = de_caso(caso_alheio, data_distribuicao="2026-07-01")
    p_inativo = de_caso(caso_alheio, status=False)
    return {
        "marca": marca,
        "sem": p_sem,
        "estag": p_estag,
        "alheio": p_alheio,
        "inativo": p_inativo,
        "todos": {p_sem["id"], p_estag["id"], p_alheio["id"]},
    }


class TestLista:
    def test_item_traz_partes_e_publicacoes(self, client, auth_headers, cenario_lista):
        lista = listar(client, auth_headers, parte=cenario_lista["marca"])
        por_id = {p["id"]: p for p in lista["items"]}
        assert set(por_id) == cenario_lista["todos"]
        sem = por_id[cenario_lista["sem"]["id"]]
        assert sem["id_caso"] is None
        assert sem["partes"] == [f"{cenario_lista['marca']} Universidade"]
        assert sem["total_publicacoes"] == 0
        assert por_id[cenario_lista["estag"]["id"]]["partes"] == [f"{cenario_lista['marca']} Cliente do caso"]
        assert lista["total"] == 3 and "total_pages" in lista

    def test_filtro_por_parte_e_variacao(self, client, auth_headers, cenario_lista):
        marca = cenario_lista["marca"]
        assert ids(listar(client, auth_headers, parte=f"{marca} UNIV")) == {cenario_lista["sem"]["id"]}
        assert ids(listar(client, auth_headers, parte=f"{marca} universidade")) == {cenario_lista["sem"]["id"]}
        assert ids(listar(client, auth_headers, parte=f"{marca} Cliente")) == {
            cenario_lista["estag"]["id"],
            cenario_lista["alheio"]["id"],
        }
        assert ids(listar(client, auth_headers, parte=f"{marca} ninguém")) == set()

    def test_filtro_por_numero(self, client, auth_headers, cenario_lista):
        p = cenario_lista["estag"]
        assert ids(listar(client, auth_headers, numero=p["numero"])) == {p["id"]}
        assert ids(listar(client, auth_headers, numero=p["numero_cnj"][-12:])) == {p["id"]}

    def test_filtro_por_distribuicao(self, client, auth_headers, cenario_lista):
        marca = cenario_lista["marca"]
        assert ids(listar(client, auth_headers, parte=marca, distribuicao_de="2026-05-01")) == {
            cenario_lista["estag"]["id"],
            cenario_lista["alheio"]["id"],
        }
        assert ids(
            listar(client, auth_headers, parte=marca, distribuicao_de="2026-03-01", distribuicao_ate="2026-06-01")
        ) == {cenario_lista["sem"]["id"], cenario_lista["estag"]["id"]}
        r = client.get("/api/processos?distribuicao_de=ontem", headers=auth_headers)
        assert r.status_code == 400

    def test_filtro_por_status(self, client, auth_headers, cenario_lista):
        marca = cenario_lista["marca"]
        inativo = cenario_lista["inativo"]["id"]
        assert inativo not in ids(listar(client, auth_headers, parte=marca))
        assert ids(listar(client, auth_headers, parte=marca, status="inativo")) == {inativo}
        assert ids(listar(client, auth_headers, parte=marca, status="todos")) == cenario_lista["todos"] | {inativo}
        assert client.get("/api/processos?status=x", headers=auth_headers).status_code == 400

    def test_filtro_com_caso(self, client, auth_headers, cenario_lista):
        marca = cenario_lista["marca"]
        assert ids(listar(client, auth_headers, parte=marca, com_caso="nao")) == {cenario_lista["sem"]["id"]}
        assert ids(listar(client, auth_headers, parte=marca, com_caso="sim")) == {
            cenario_lista["estag"]["id"],
            cenario_lista["alheio"]["id"],
        }
        assert client.get("/api/processos?com_caso=talvez", headers=auth_headers).status_code == 400

    @pytest.mark.parametrize("papel", ["prof", "orient", "colab_proj"])
    def test_papeis_da_unidade_veem_tudo(self, client, papeis, cenario_lista, papel):
        h = papeis[papel]["h"]
        assert ids(listar(client, h, parte=cenario_lista["marca"])) == cenario_lista["todos"]
        assert client.get(f"/api/processos/{cenario_lista['sem']['id']}", headers=h).status_code == 200

    def test_estagiario_ve_so_os_casos_dele_e_nunca_sem_caso(self, client, papeis, cenario_lista):
        h = papeis["estag_direito"]["h"]
        marca = cenario_lista["marca"]
        assert ids(listar(client, h, parte=marca)) == {cenario_lista["estag"]["id"]}
        assert ids(listar(client, h, parte=marca, com_caso="nao")) == set()
        assert client.get(f"/api/processos/{cenario_lista['estag']['id']}", headers=h).status_code == 200
        for chave in ("sem", "alheio"):
            pid = cenario_lista[chave]["id"]
            assert client.get(f"/api/processos/{pid}", headers=h).status_code == 404
            assert client.put(f"/api/processos/{pid}", json={"obs": "x"}, headers=h).status_code == 404
            assert client.delete(f"/api/processos/{pid}", headers=h).status_code == 404

    def test_colab_ext_sem_caso_nenhum_nao_ve_nada(self, client, papeis, cenario_lista):
        h = papeis["colab_ext"]["h"]
        assert ids(listar(client, h, parte=cenario_lista["marca"])) == set()
        assert client.get(f"/api/processos/{cenario_lista['sem']['id']}", headers=h).status_code == 404

    def test_outra_unidade_nao_ve(self, client, auth_headers_nl, cenario_lista):
        assert ids(listar(client, auth_headers_nl, parte=cenario_lista["marca"])) == set()
        for chave in ("sem", "estag"):
            pid = cenario_lista[chave]["id"]
            assert client.get(f"/api/processos/{pid}", headers=auth_headers_nl).status_code == 404
            r = client.put(f"/api/processos/{pid}", json={"obs": "x"}, headers=auth_headers_nl)
            assert r.status_code == 404

    def test_processo_sem_caso_de_nova_lima_fica_em_nova_lima(self, client, auth_headers, auth_headers_nl):
        a = parte(client, auth_headers_nl)
        assert a["unidade_id"] == UNIDADE_NL
        p = processo_sem_caso(client, auth_headers_nl, [a["id"]])
        assert p["unidade_id"] == UNIDADE_NL
        assert p["id"] in ids(listar(client, auth_headers_nl, com_caso="nao"))
        assert p["id"] not in ids(listar(client, auth_headers, com_caso="nao"))


# --------------------------------------------------------------------------- #
# DJEN com processo sem caso
# --------------------------------------------------------------------------- #


def _eventos_djen() -> list[dict]:
    return [e for e in _linhas(eventos) if e["origem"] == "djen"]


class TestDjenSemCaso:
    def test_buscar_vincula_sem_criar_evento(self, client, auth_headers, djen, transporte):
        a = parte(client, auth_headers)
        p = processo_sem_caso(client, auth_headers, [a["id"]])
        transporte.por_processo[p["numero_cnj"]] = [item_djen(81001, p["numero_cnj"])]
        r = client.post(f"/api/processos/{p['id']}/djen/buscar", headers=auth_headers)
        assert r.status_code == 200, r.get_json()
        assert get_success_data(r)["vinculadas"] == 1
        (com,) = _linhas(djen_comunicacoes, id_djen=81001)
        assert com["situacao"] == "vinculada"
        assert com["id_processo"] == p["id"] and com["id_caso"] is None
        assert com["unidade_id"] == UNIDADE_BH
        assert _eventos_djen() == []
        assert _linhas(notificacao, tipo="djen") == []
        # A lista de processos conta a publicação; a do DJEN filtra pelo processo.
        (item,) = [x for x in listar(client, auth_headers, com_caso="nao")["items"] if x["id"] == p["id"]]
        assert item["total_publicacoes"] == 1
        pubs = get_success_data(
            client.get(f"/api/djen/publicacoes?processo_id={p['id']}", headers=auth_headers)
        )
        assert [x["id"] for x in pubs["items"]] == [com["id"]]

    def test_rotina_vincula_pelo_numero(self, app, client, auth_headers, djen, transporte, sync_habilitado):
        a = parte(client, auth_headers)
        p = processo_sem_caso(client, auth_headers, [a["id"]])
        transporte.por_processo[p["numero_cnj"]] = [item_djen(81002, p["numero_cnj"])]
        assert rodar_rotina(app)["daj-ufmg"] == "ok"
        (com,) = _linhas(djen_comunicacoes, id_djen=81002)
        assert (com["situacao"], com["id_processo"], com["id_caso"]) == ("vinculada", p["id"], None)
        assert _eventos_djen() == []

    def test_vinculo_manual_a_processo_sem_caso(self, app, client, auth_headers, djen, transporte):
        from .test_djen_eventos import registrar_pendente

        a = parte(client, auth_headers)
        p = processo_sem_caso(client, auth_headers, [a["id"]])
        pub = registrar_pendente(app, 81003, numero_cnj_novo())
        r = client.post(
            f"/api/djen/publicacoes/{pub}/vincular", json={"processo_id": p["id"]}, headers=auth_headers
        )
        assert r.status_code == 200, r.get_json()
        d = get_success_data(r)
        assert (d["situacao"], d["id_processo"], d["id_caso"]) == ("vinculada", p["id"], None)
        assert _eventos_djen() == []

    def test_estagiario_nao_ve_publicacao_de_processo_sem_caso(self, client, auth_headers, papeis, djen, transporte):
        a = parte(client, auth_headers)
        p = processo_sem_caso(client, auth_headers, [a["id"]])
        transporte.por_processo[p["numero_cnj"]] = [item_djen(81004, p["numero_cnj"])]
        client.post(f"/api/processos/{p['id']}/djen/buscar", headers=auth_headers)
        (com,) = _linhas(djen_comunicacoes, id_djen=81004)
        h = papeis["estag_direito"]["h"]
        assert client.get(f"/api/djen/publicacoes/{com['id']}", headers=h).status_code == 404
        # colab_proj vê as vinculadas da unidade, inclusive as sem caso.
        assert client.get(f"/api/djen/publicacoes/{com['id']}", headers=papeis["colab_proj"]["h"]).status_code == 200


# --------------------------------------------------------------------------- #
# Busca por parte
# --------------------------------------------------------------------------- #

PERIODO = {"de": "2026-11-01", "ate": "2026-11-20"}


def _contagens() -> tuple[int, int, int, int]:
    return (
        len(_linhas(djen_comunicacoes)),
        len(_linhas(processos)),
        len(_linhas(processo_partes)),
        len(_linhas(eventos)),
    )


class TestBuscaParte:
    def test_consulta_salva_acervo_e_vincula_processos_existentes(self, client, auth_headers, djen, transporte):
        a = parte(client, auth_headers)
        cadastrado = processo_sem_caso(client, auth_headers, [a["id"]])
        nome = _unico("Universidade Fictícia")
        novo = numero_cnj_novo()
        transporte.por_parte[nome] = [
            item_djen(82001, cadastrado["numero_cnj"], data="2026-11-03"),
            item_djen(82002, novo, data="2026-11-05", tribunal="TRF6"),
        ]
        transporte.por_parte["UFMG"] = [item_djen(82002, novo, data="2026-11-05", tribunal="TRF6")]
        antes = _contagens()
        r = client.get(
            "/api/djen/busca-parte",
            query_string=[("nome", nome), ("nome", "UFMG"), ("de", PERIODO["de"]), ("ate", PERIODO["ate"])],
            headers=auth_headers,
        )
        assert r.status_code == 200, r.get_json()
        d = get_success_data(r)
        assert _contagens() == (antes[0] + 1, *antes[1:])
        # Os dois nomes trazem a 82002 uma vez só; mais recente primeiro.
        assert [i["id_djen"] for i in d["items"]] == [82002, 82001]
        por_id = {i["id_djen"]: i for i in d["items"]}
        assert por_id[82001]["processo_id"] == cadastrado["id"]
        assert por_id[82001]["ja_no_banco"] is True
        assert por_id[82002]["processo_id"] is None
        assert por_id[82002]["numero_processo_mascara"] == mascara(novo)
        assert "resumo" in por_id[82002] and "texto" not in por_id[82002]
        consultas = [c for c in transporte.chamadas if "nomeParte" in c]
        assert {c["nomeParte"] for c in consultas} == {nome, "UFMG"}
        assert all(c["dataDisponibilizacaoInicio"] == PERIODO["de"] for c in consultas)

    def test_importa_com_o_periodo_que_a_busca_devolveu(self, client, auth_headers, djen, transporte):
        # A tela manda de volta o "de"/"ate" da resposta da busca.
        a = parte(client, auth_headers)
        nome = _unico("Ida e volta")
        transporte.por_parte[nome] = [item_djen(82030, numero_cnj_novo())]
        busca = get_success_data(
            client.get("/api/djen/busca-parte", query_string={"nome": nome, **PERIODO}, headers=auth_headers)
        )
        assert (busca["de"], busca["ate"]) == (PERIODO["de"], PERIODO["ate"])
        r = client.post(
            "/api/djen/busca-parte/importar",
            json={
                "nome": busca["nomes"],
                "de": busca["de"],
                "ate": busca["ate"],
                "ids": [82030],
                "id_atendido": a["id"],
            },
            headers=auth_headers,
        )
        assert r.status_code == 200, r.get_json()
        assert len(get_success_data(r)["processos_criados"]) == 1

    def test_publicacao_ja_gravada(self, client, auth_headers, djen, transporte):
        a = parte(client, auth_headers)
        p = processo_sem_caso(client, auth_headers, [a["id"]])
        transporte.por_processo[p["numero_cnj"]] = [item_djen(82010, p["numero_cnj"])]
        client.post(f"/api/processos/{p['id']}/djen/buscar", headers=auth_headers)
        nome = _unico("Parte já gravada")
        transporte.por_parte[nome] = [item_djen(82010, p["numero_cnj"])]
        d = get_success_data(
            client.get("/api/djen/busca-parte", query_string={"nome": nome, **PERIODO}, headers=auth_headers)
        )
        (item,) = d["items"]
        assert item["ja_no_banco"] is True
        assert item["publicacao_id"] == _linhas(djen_comunicacoes, id_djen=82010)[0]["id"]

    def test_tribunal(self, client, auth_headers, djen, transporte):
        nome = _unico("Parte com tribunal")
        transporte.por_parte[nome] = [
            item_djen(82020, numero_cnj_novo(), tribunal="TJMG"),
            item_djen(82021, numero_cnj_novo(), tribunal="TRF6"),
        ]
        d = get_success_data(
            client.get(
                "/api/djen/busca-parte",
                query_string={"nome": nome, "tribunal": "trf6", **PERIODO},
                headers=auth_headers,
            )
        )
        assert [i["id_djen"] for i in d["items"]] == [82021]
        assert transporte.chamadas[-1]["siglaTribunal"] == "TRF6"

    def test_varios_tribunais(self, client, auth_headers, djen, transporte):
        # Uma consulta por nome e por tribunal; a resposta devolve as siglas.
        nome = _unico("Parte em vários tribunais")
        transporte.por_parte[nome] = [
            item_djen(82040, numero_cnj_novo(), tribunal="TJMG"),
            item_djen(82041, numero_cnj_novo(), tribunal="TRF6"),
            item_djen(82042, numero_cnj_novo(), tribunal="TRT3"),
        ]
        antes = len(transporte.chamadas)
        d = get_success_data(
            client.get(
                "/api/djen/busca-parte",
                query_string=[("nome", nome), ("tribunal", "trf6"), ("tribunal", "TJMG"), *PERIODO.items()],
                headers=auth_headers,
            )
        )
        assert sorted(i["id_djen"] for i in d["items"]) == [82040, 82041]
        assert d["tribunais"] == ["TRF6", "TJMG"]
        assert {c["siglaTribunal"] for c in transporte.chamadas[antes:]} == {"TRF6", "TJMG"}

    def test_limite_de_tribunais(self, client, auth_headers, djen, transporte):
        siglas = [("tribunal", f"TRT{n}") for n in range(1, 12)]
        r = client.get(
            "/api/djen/busca-parte",
            query_string=[("nome", "Fulana"), *siglas, *PERIODO.items()],
            headers=auth_headers,
        )
        assert r.status_code == 400
        assert r.get_json()["error"]["details"]["field"] == "tribunal"

    @pytest.mark.parametrize(
        "query",
        [
            {"de": "2026-10-01", "ate": "2026-11-20", "nome": "Fulana"},  # mais de 30 dias
            {"de": "2026-11-20", "ate": "2026-11-01", "nome": "Fulana"},
            {"de": "2026-11-01", "nome": "Fulana"},
            {"de": "2026-11-01", "ate": "2026-11-02", "nome": "Fu"},
            {"de": "2026-11-01", "ate": "2026-11-02"},
        ],
    )
    def test_validacao(self, client, auth_headers, djen, transporte, query):
        r = client.get("/api/djen/busca-parte", query_string=query, headers=auth_headers)
        assert r.status_code == 400
        assert transporte.chamadas == []

    def test_periodo_de_30_dias_passa(self, client, auth_headers, djen, transporte):
        r = client.get(
            "/api/djen/busca-parte",
            query_string={"nome": "Fulana", "de": "2026-10-21", "ate": "2026-11-20"},
            headers=auth_headers,
        )
        assert r.status_code == 200

    @pytest.mark.parametrize("papel", ["colab_proj", "estag_direito", "colab_ext"])
    def test_so_quem_vincula_busca(self, client, papeis, djen, transporte, papel):
        h = papeis[papel]["h"]
        r = client.get("/api/djen/busca-parte", query_string={"nome": "Fulana", **PERIODO}, headers=h)
        assert r.status_code == 403
        r = client.post("/api/djen/busca-parte/importar", json={"nome": "Fulana", **PERIODO, "ids": [1]}, headers=h)
        assert r.status_code == 403
        assert transporte.chamadas == []

    def test_djen_desligado(self, client, auth_headers, transporte):
        r = client.get("/api/djen/busca-parte", query_string={"nome": "Fulana", **PERIODO}, headers=auth_headers)
        assert r.status_code == 403
        assert transporte.chamadas == []

    def test_djen_fora_do_ar(self, client, auth_headers, djen, transporte):
        transporte.falhar.add("Fulana Fora")
        r = client.get("/api/djen/busca-parte", query_string={"nome": "Fulana Fora", **PERIODO}, headers=auth_headers)
        assert r.status_code == 422
        assert r.get_json()["error"]["code"] == "DJEN_INDISPONIVEL"


class TestImportacao:
    def test_vincula_ao_existente_e_cria_processo_sem_caso(self, client, auth_headers, djen, transporte):
        a = parte(client, auth_headers)
        existente = processo_sem_caso(client, auth_headers, [a["id"]])
        nova_parte = parte(client, auth_headers, nome="Universidade Fictícia de Minas")
        nome = _unico("Importação")
        novo = numero_cnj_novo()
        item_novo = item_djen(83002, novo, tribunal="TRF6")
        item_novo["nomeOrgao"] = "23ª VARA FEDERAL – BH ≥"
        transporte.por_parte[nome] = [
            item_djen(83001, existente["numero_cnj"]),
            item_novo,
            item_djen(83003, novo, data="2026-11-02"),
            item_djen(83004, numero_cnj_novo()),  # não escolhida
        ]
        assert client.get("/api/djen/busca-parte", query_string={"nome": nome, **PERIODO}, headers=auth_headers).status_code == 200
        r = client.post(
            "/api/djen/busca-parte/importar",
            json={"nome": nome, **PERIODO, "ids": [83001, 83002, 83003], "id_atendido": nova_parte["id"]},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.get_json()
        d = get_success_data(r)
        assert d["novas"] == 2 and d["vinculadas"] == 2  # o existente já foi vinculado na captura
        assert d["nao_encontradas"] == []
        (criado,) = d["processos_criados"]
        assert _linhas(djen_comunicacoes, id_djen=83004) == []
        (c1,) = _linhas(djen_comunicacoes, id_djen=83001)
        assert (c1["id_processo"], c1["id_caso"], c1["situacao"]) == (existente["id"], None, "vinculada")
        for id_djen in (83002, 83003):
            (c,) = _linhas(djen_comunicacoes, id_djen=id_djen)
            assert (c["id_processo"], c["id_caso"], c["unidade_id"]) == (criado, None, UNIDADE_BH)
        p = get_success_data(client.get(f"/api/processos/{criado}", headers=auth_headers))
        assert p["id_caso"] is None and p["numero_cnj"] == novo and p["numero"] == mascara(novo)
        assert p["especie"] == "Outros"
        # Coluna legada em latin1: o que o cp1252 não tem vira "?".
        assert p["vara"] == "23ª VARA FEDERAL – BH ?"
        assert [x["id_atendido"] for x in p["partes"]] == [nova_parte["id"]]
        assert _eventos_djen() == []

    def test_sem_parte_para_numero_novo_nao_grava_nada(self, client, auth_headers, djen, transporte):
        nome = _unico("Sem parte")
        transporte.por_parte[nome] = [item_djen(83010, numero_cnj_novo())]
        assert client.get("/api/djen/busca-parte", query_string={"nome": nome, **PERIODO}, headers=auth_headers).status_code == 200
        antes = _contagens()
        r = client.post(
            "/api/djen/busca-parte/importar", json={"nome": nome, **PERIODO, "ids": [83010]}, headers=auth_headers
        )
        assert r.status_code == 400
        assert r.get_json()["error"]["details"]["field"] == "id_atendido"
        assert _contagens() == antes

    def test_parte_de_outra_unidade(self, client, auth_headers, auth_headers_nl, djen, transporte):
        de_nl = parte(client, auth_headers_nl)
        r = client.post(
            "/api/djen/busca-parte/importar",
            json={"nome": "Fulana", **PERIODO, "ids": [1], "id_atendido": de_nl["id"]},
            headers=auth_headers,
        )
        assert r.status_code == 400
        assert transporte.chamadas == []

    def test_importar_de_novo_nao_duplica(self, client, auth_headers, djen, transporte):
        a = parte(client, auth_headers)
        p = processo_sem_caso(client, auth_headers, [a["id"]])
        nome = _unico("Duas vezes")
        transporte.por_parte[nome] = [item_djen(83020, p["numero_cnj"])]
        assert client.get("/api/djen/busca-parte", query_string={"nome": nome, **PERIODO}, headers=auth_headers).status_code == 200
        corpo = {"nome": nome, **PERIODO, "ids": [83020]}
        assert get_success_data(client.post("/api/djen/busca-parte/importar", json=corpo, headers=auth_headers))["novas"] == 0  # já vinculada na busca
        d = get_success_data(client.post("/api/djen/busca-parte/importar", json=corpo, headers=auth_headers))
        assert d["novas"] == 0 and d["processos_criados"] == []
        assert len(_linhas(djen_comunicacoes, id_djen=83020)) == 1

    def test_importacao_para_processo_de_caso_cria_evento(self, client, auth_headers, djen, transporte):
        caso = criar_caso(client, auth_headers)
        r = client.post(
            f"/api/caso/{caso}/processos",
            json={"especie": "Ação", "numero": mascara(numero_cnj_novo()), "status": True},
            headers=auth_headers,
        )
        p = get_success_data(r)
        nome = _unico("Com caso")
        transporte.por_parte[nome] = [item_djen(83030, p["numero_cnj"])]
        assert client.get("/api/djen/busca-parte", query_string={"nome": nome, **PERIODO}, headers=auth_headers).status_code == 200
        d = get_success_data(
            client.post(
                "/api/djen/busca-parte/importar", json={"nome": nome, **PERIODO, "ids": [83030]}, headers=auth_headers
            )
        )
        assert d["vinculadas"] == 0  # evento e vínculo já foram criados pela busca
        (c,) = _linhas(djen_comunicacoes, id_djen=83030)
        assert c["id_caso"] == caso
        assert [e["id_caso"] for e in _eventos_djen()] == [caso]


class TestVincularProcessoCaso:
    def test_historico_eventos_e_repeticao(self, client, auth_headers, djen, transporte):
        a = parte(client, auth_headers)
        p = processo_sem_caso(client, auth_headers, [a["id"]])
        transporte.por_processo[p["numero_cnj"]] = [
            item_djen(89501, p["numero_cnj"]), item_djen(89502, p["numero_cnj"])
        ]
        r = client.post(f"/api/processos/{p['id']}/djen/buscar", headers=auth_headers)
        assert r.status_code == 200
        from .test_djen_exemplos import classificar, rotulos
        assert classificar(client, auth_headers, [89501], "irrelevante").status_code == 200
        caso = criar_caso(client, auth_headers)
        url = f"/api/processos/{p['id']}/vincular-caso"
        r = client.post(url, json={"caso_id": caso}, headers=auth_headers)
        assert r.status_code == 200, r.get_json()
        dados = get_success_data(r)
        assert dados["eventos_criados"] == 2
        assert rotulos()[89501] == "irrelevante"
        assert dados["processo"]["id_caso"] == caso
        assert a["id"] in [p["id_atendido"] for p in dados["processo"]["partes"]]
        pubs = _linhas(djen_comunicacoes, id_processo=p["id"])
        evs = _linhas(eventos, id_caso=caso)
        assert len(evs) == 2
        assert all(pub["id_caso"] == caso for pub in pubs)
        assert {e["data_evento"] for e in evs} == {pub["data_disponibilizacao"] for pub in pubs}
        r = client.post(url, json={"caso_id": caso}, headers=auth_headers)
        assert r.status_code == 200
        assert get_success_data(r)["eventos_criados"] == 0
        assert len(_linhas(eventos, id_caso=caso)) == 2
        outro = criar_caso(client, auth_headers)
        assert client.post(url, json={"caso_id": outro}, headers=auth_headers).status_code == 400

    def test_rejeita_outra_unidade_e_papel(self, client, auth_headers, auth_headers_nl, papeis):
        a = parte(client, auth_headers)
        p = processo_sem_caso(client, auth_headers, [a["id"]])
        caso = criar_caso(client, auth_headers_nl)
        url = f"/api/processos/{p['id']}/vincular-caso"
        assert client.post(url, json={"caso_id": caso}, headers=auth_headers).status_code == 400
        assert client.post(url, json={"caso_id": caso}, headers=auth_headers_nl).status_code == 404
        assert client.post(url, json={"caso_id": caso}, headers=papeis["estag_direito"]["h"]).status_code == 403
        assert get_success_data(client.get(f"/api/processos/{p['id']}", headers=auth_headers))["id_caso"] is None

    def test_falha_evento_desfaz_vinculo(self, client, auth_headers, djen, transporte, monkeypatch):
        from gestaolegal.services.djen_service import DJENService
        from gestaolegal.exceptions import ValidationException

        a = parte(client, auth_headers)
        p = processo_sem_caso(client, auth_headers, [a["id"]])
        transporte.por_processo[p["numero_cnj"]] = [item_djen(89503, p["numero_cnj"])]
        assert client.post(f"/api/processos/{p['id']}/djen/buscar", headers=auth_headers).status_code == 200
        caso = criar_caso(client, auth_headers)
        def falhar(*args, **kwargs):
            raise ValidationException("Falha simulada")
        monkeypatch.setattr(DJENService, "_criar_evento", falhar)
        r = client.post(f"/api/processos/{p['id']}/vincular-caso", json={"caso_id": caso}, headers=auth_headers)
        assert r.status_code == 400
        assert get_success_data(client.get(f"/api/processos/{p['id']}", headers=auth_headers))["id_caso"] is None
        assert _linhas(djen_comunicacoes, id_processo=p["id"])[0]["id_caso"] is None

    def test_captura_com_processo_lido_antes_do_vinculo(self, app, client, auth_headers, djen):
        from dataclasses import replace
        from gestaolegal.integrations.djen_client import converter_item
        from gestaolegal.services.djen_service import DJENService, ResultadoCaptura
        from gestaolegal.utils.request_context import contexto_tenant
        from .conftest import TENANT_DAJ

        a = parte(client, auth_headers)
        p = processo_sem_caso(client, auth_headers, [a["id"]])
        caso = criar_caso(client, auth_headers)
        r = client.post(f"/api/processos/{p['id']}/vincular-caso", json={"caso_id": caso}, headers=auth_headers)
        assert r.status_code == 200
        assert get_success_data(r)["eventos_criados"] == 0
        with app.test_request_context(), contexto_tenant(TENANT_DAJ):
            service = DJENService()
            antigo = replace(service.processos.find_by_id(p["id"]), id_caso=None)
            service.registrar(converter_item(item_djen(89504, p["numero_cnj"])),
                              ResultadoCaptura(), processo=antigo)
            service._depois_da_fonte()
            service.session.commit()
        assert len(_linhas(eventos, id_caso=caso)) == 1
        assert _linhas(djen_comunicacoes, id_processo=p["id"])[0]["id_caso"] == caso
