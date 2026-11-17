"""Monitoramento compartilhado, recuperação e retenção sem perda do acervo."""

from datetime import datetime, timedelta
import pytest
from sqlalchemy import update
from gestaolegal.database import session as db
from gestaolegal.database.tables import (
    djen_monitoramentos as m,
    djen_consultas as q,
    djen_publicacoes as p,
    djen_publicacao_unidades as a,
)
from gestaolegal.utils.request_context import contexto_tenant, sem_tenant
from gestaolegal.services.djen_monitoramento_service import DjenMonitoramentoService
from .test_djen_api import (
    djen,
    transporte,
    headers_outro,
    _linhas,
    criar_caso,
    criar_processo,
    numero_cnj_novo,
)
from .djen_fixtures import item_djen
from .conftest import TENANT_DAJ

pytestmark = pytest.mark.usefixtures("djen")
BASE = "/api/djen/monitoramentos"


def cadastrar(client, h, tipo="oab", valor="123456/MG", **extra):
    res = client.post(BASE, headers=h, json=dict(tipo=tipo, valor=valor, **extra))
    assert res.status_code == 201, res.json
    return next(
        i for i in res.json["data"] if i["tipo"] == tipo and i["valor"] == valor
    )


def test_cadastro_pausa_remocao_preservam_acervo(client, auth_headers, transporte):
    item = cadastrar(client, auth_headers)
    assert (
        client.patch(
            f"{BASE}/{item['id']}", headers=auth_headers, json={"ativo": False}
        ).status_code
        == 200
    )
    assert (
        next(
            i
            for i in client.get(BASE, headers=auth_headers).json["data"]
            if i["id"] == item["id"]
        )["ativo"]
        is False
    )
    assert (
        client.delete(f"{BASE}/{item['id']}", headers=auth_headers).status_code == 200
    )
    assert item["id"] not in [
        i["id"] for i in client.get(BASE, headers=auth_headers).json["data"]
    ]


def test_parte_exige_tribunal_e_normaliza(client, auth_headers):
    res = client.post(
        BASE, headers=auth_headers, json={"tipo": "parte", "valor": " Maria Teste "}
    )
    assert res.status_code == 400
    res = client.post(
        BASE,
        headers=auth_headers,
        json={"tipo": "parte", "valor": " Maria Teste ", "tribunais": ["tjmg"]},
    )
    assert res.status_code == 201
    assert any(
        i["valor"] == "MARIA TESTE" and i["tribunais"] == ["TJMG"]
        for i in res.json["data"]
    )


def test_processo_automatico_pausa_persistente(client, auth_headers):
    numero = numero_cnj_novo()
    criar_processo(client, auth_headers, criar_caso(client, auth_headers), numero)
    items = client.get(BASE, headers=auth_headers).json["data"]
    monitor = next(i for i in items if i["valor"] == numero)
    assert monitor["automatico"]
    client.patch(f"{BASE}/{monitor['id']}", headers=auth_headers, json={"ativo": False})
    assert not next(
        i
        for i in client.get(BASE, headers=auth_headers).json["data"]
        if i["id"] == monitor["id"]
    )["ativo"]


def test_busca_avulsa_logs_e_retencao(client, auth_headers, transporte, app):
    numero = numero_cnj_novo()
    transporte.por_processo[numero] = [item_djen(990001, numero)]
    res = client.post(
        BASE + "/buscar",
        headers=auth_headers,
        json=dict(
            tipo="processo",
            valor=numero,
            de="2026-11-01",
            ate="2026-11-20",
            tribunais=["TJMG"],
        ),
    )
    assert res.status_code == 200, res.json
    assert res.json["data"][0]["encontradas"] == 1
    assert len(_linhas(a)) == 1
    with app.test_request_context(), contexto_tenant(TENANT_DAJ):
        service = DjenMonitoramentoService()
        service.session.execute(
            service.escopo(update(q), q).values(
                inicio=datetime.now() - timedelta(days=100)
            )
        )
        service.session.commit()
        service.limpar_logs()
    assert len(_linhas(q)) == 0
    assert len(_linhas(p)) == 1
    assert len(_linhas(a)) == 1
    assert (
        client.get("/api/djen/acervo", headers=auth_headers).json["data"]["total"] == 1
    )


def test_rotina_reconsulta_processo_e_recupera_periodo(
    client, auth_headers, transporte, app
):
    numero = numero_cnj_novo()
    cadastrar(client, auth_headers, "processo", numero)
    transporte.por_processo[numero] = [item_djen(990002, numero)]
    with app.test_request_context(), contexto_tenant(TENANT_DAJ):
        service = DjenMonitoramentoService()
        service.session.execute(
            service.escopo(update(m).where(m.c.valor == numero), m).values(
                ultimo_sucesso=datetime.now().date() - timedelta(days=15)
            )
        )
        service.session.commit()
        assert service.djen.sincronizar(3)["status"] == "ok"
        assert service.djen.sincronizar(3)["status"] == "ok"
    logs = [row for row in _linhas(q) if row["parametros"].get("valor") == numero]
    assert len(logs) == 2
    assert (
        logs[0]["parametros"]["de"]
        <= (datetime.now().date() - timedelta(days=15)).isoformat()
    )
    assert len(_linhas(p)) == 1


def test_duas_unidades_compartilham_consulta_sem_duplicar(
    client, auth_headers, transporte, app
):
    cadastrar(client, auth_headers, unidade_id=1)
    cadastrar(client, auth_headers, unidade_id=2)
    transporte.por_oab[("123456", "MG")] = [item_djen(990003, numero_cnj_novo())]
    with app.test_request_context(), contexto_tenant(TENANT_DAJ):
        service = DjenMonitoramentoService()
        service.djen.sincronizar(7)
    assert len([c for c in transporte.chamadas if c.get("numeroOab") == "123456"]) == 1
    assert {row["unidade_id"] for row in _linhas(a)} == {1, 2}
    assert len(_linhas(p)) == 1
    assert {row["unidade_id"] for row in _linhas(q) if row["origem"] == "oab"} == {1, 2}


def test_recusa_unidade_de_outro_npj(client, auth_headers):
    res = client.post(
        BASE,
        headers=auth_headers,
        json=dict(tipo="oab", valor="123456/MG", unidade_id=3),
    )
    assert res.status_code == 400
    assert not _linhas(m)


def test_log_falha_e_repeticao_preserva_classificacao(
    client, auth_headers, transporte, app
):
    cadastrar(client, auth_headers)
    transporte.falhar.add("123456/MG")
    with app.test_request_context(), contexto_tenant(TENANT_DAJ):
        DjenMonitoramentoService().djen.sincronizar(7)
    log = next(row for row in _linhas(q) if row["origem"] == "oab")
    assert log["status"] == "erro" and log["mensagem"] and log["fim"]
    assert _linhas(m)[0]["ultimo_sucesso"] is None


def test_logs_manuais_isolados_entre_npjs(
    client, auth_headers, headers_outro, app, transporte
):
    from .conftest import TENANT_OUTRO
    from .djen_fixtures import ligar_djen

    with app.app_context():
        ligar_djen(TENANT_OUTRO)
    for headers, valor in [(auth_headers, "123456/MG"), (headers_outro, "654321/MG")]:
        res = client.post(
            BASE + "/buscar",
            headers=headers,
            json=dict(tipo="oab", valor=valor, de="2026-11-01", ate="2026-11-07"),
        )
        assert res.status_code == 200
    meus = client.get(BASE + "/logs", headers=auth_headers).json["data"]["items"]
    outros = client.get(BASE + "/logs", headers=headers_outro).json["data"]["items"]
    assert {i["tenant_id"] for i in meus} == {TENANT_DAJ}
    assert {i["tenant_id"] for i in outros} == {TENANT_OUTRO}
    assert {i["parametros"]["valor"] for i in meus} == {"123456/MG"}
    assert {i["parametros"]["valor"] for i in outros} == {"654321/MG"}


@pytest.mark.parametrize(
    "hora,esperado",
    [(0, None), (3, None), (4, 4), (9, 4), (10, 10), (15, 10), (16, 16), (23, 16)],
)
def test_agendamento_todos_os_dias(hora, esperado):
    from scripts.agendar_djen import horario_devido

    for dia in (14, 15, 16):  # sábado, domingo, segunda
        assert horario_devido(datetime(2026, 11, dia, hora)) == esperado


def test_gestor_ve_apenas_suas_unidades(client, auth_headers, app, transporte):
    from .conftest import criar_usuario, headers_para

    item = cadastrar(client, auth_headers, unidade_id=2)
    with app.app_context():
        criar_usuario(
            "prof.monitor@teste.br", "senha12345", "prof", "Professor monitor"
        )
    h = headers_para(client, "prof.monitor@teste.br", "senha12345")
    assert all(i["unidade_id"] == 1 for i in client.get(BASE, headers=h).json["data"])
    assert (
        client.patch(
            f"{BASE}/{item['id']}", headers=h, json={"ativo": False}
        ).status_code
        == 404
    )
    res = client.post(
        BASE + "/buscar",
        headers=auth_headers,
        json=dict(
            tipo="oab",
            valor="123456/MG",
            de="2026-11-01",
            ate="2026-11-07",
            unidade_id=2,
        ),
    )
    assert res.status_code == 200
    assert client.get(BASE + "/logs", headers=h).json["data"]["items"] == []


@pytest.mark.parametrize('tipo', ['oab', 'parte', 'processo'])
def test_busca_manual_vincula_processo_sem_duplicar(client,auth_headers,app,transporte,tipo):
    from gestaolegal.database.tables import djen_comunicacoes, eventos, djen_classificacoes
    numero=numero_cnj_novo()
    processo=criar_processo(client,auth_headers,criar_caso(client,auth_headers),numero)
    item=item_djen(992001,numero)
    transporte.por_processo[numero]=[item]
    transporte.por_oab[('123456','MG')]=[item]
    transporte.por_parte['PARTE TESTE']=[item]
    valor={'processo':numero,'oab':'123456/MG','parte':'PARTE TESTE'}[tipo]
    for _ in range(2):
        res=client.post(BASE+'/buscar',headers=auth_headers,json=dict(tipo=tipo,valor=valor,de='2026-11-01',ate='2026-11-20'))
        assert res.status_code==200,res.json
        assert res.json['data'][0]['status']=='ok'
    comunicacoes=_linhas(djen_comunicacoes,id_djen=992001)
    assert len(comunicacoes)==1
    assert comunicacoes[0]['id_processo']==processo['id']
    assert comunicacoes[0]['situacao']=='vinculada'
    assert len(_linhas(eventos,origem='djen'))==1
    assert _linhas(djen_classificacoes)[0]['rotulo']=='relevante'


def test_busca_parte_original_vincula_processo_cadastrado(client,auth_headers,transporte):
    from gestaolegal.database.tables import djen_comunicacoes,eventos
    numero=numero_cnj_novo()
    processo=criar_processo(client,auth_headers,criar_caso(client,auth_headers),numero)
    transporte.por_parte['Parte original']=[item_djen(992002,numero)]
    for _ in range(2):
        res=client.get('/api/djen/busca-parte',headers=auth_headers,query_string=dict(nome='Parte original',de='2026-11-01',ate='2026-11-20'))
        assert res.status_code==200,res.json
        assert res.json['data']['items'][0]['ja_no_banco']
    assert _linhas(djen_comunicacoes,id_djen=992002)[0]['id_processo']==processo['id']
    assert len(_linhas(eventos,origem='djen'))==1


@pytest.mark.parametrize("origem", ["monitoramento", "detalhe"])
def test_historico_completo_todas_paginas(client, auth_headers, transporte, monkeypatch, origem):
    from gestaolegal.integrations.djen_client import DJENClient
    from .djen_fixtures import resposta
    init = DJENClient.__init__
    def pequeno(self, *args, **kwargs):
        init(self, *args, **kwargs)
        self.itens_por_pagina = 1
        self.max_paginas = 1
    monkeypatch.setattr(DJENClient, "__init__", pequeno)
    numero = numero_cnj_novo()
    processo = criar_processo(client, auth_headers, criar_caso(client, auth_headers), numero)
    transporte.extra = lambda filtros: resposta(
        [item_djen(997000 + int(filtros["pagina"]), numero, data="2020-01-02")],
        count=3,
    )
    if origem == "monitoramento":
        res = client.post(f"{BASE}/buscar", headers=auth_headers, json={
            "tipo": "processo", "valor": numero, "historico_completo": True,
            "de": "2026-11-01", "ate": "2026-11-02", "tribunais": ["TJMG"],
        })
        assert res.status_code == 200, res.json
        assert res.json["data"][0]["encontradas"] == 3
    else:
        res = client.post(f"/api/processos/{processo['id']}/djen/buscar", headers=auth_headers)
        assert res.status_code == 200, res.json
        assert res.json["data"]["novas"] == 3
    assert len(transporte.chamadas) == 3
    assert all(c["numeroProcesso"] == numero for c in transporte.chamadas)
    assert all(not ({"dataDisponibilizacaoInicio", "dataDisponibilizacaoFim", "siglaTribunal"} & c.keys()) for c in transporte.chamadas)
    assert len(_linhas(p)) == 3
    assert _linhas(q)[0]["parametros"]["historico_completo"] is True


def test_link_processo_mesmo_tenant_e_unidade(app, client, auth_headers, headers_outro):
    from .conftest import TENANT_OUTRO
    from .djen_fixtures import ligar_djen
    with app.app_context():
        ligar_djen(TENANT_OUTRO)
    numero = numero_cnj_novo()
    processo = criar_processo(client, auth_headers, criar_caso(client, auth_headers), numero)
    items = client.get(BASE, headers=auth_headers).json["data"]
    assert next(i for i in items if i["valor"] == numero)["processo_id"] == processo["id"]
    outro = cadastrar(client, headers_outro, "processo", numero)
    assert outro["processo_id"] is None
    avulso = cadastrar(client, auth_headers, "processo", numero_cnj_novo())
    assert avulso["processo_id"] is None


@pytest.mark.parametrize("tipo,valor", [("oab", "123456/MG"), ("parte", "Parte Teste")])
def test_historico_completo_restrito_a_processo(client, auth_headers, tipo, valor):
    res = client.post(f"{BASE}/buscar", headers=auth_headers,
        json={"tipo": tipo, "valor": valor, "historico_completo": True})
    assert res.status_code == 400
