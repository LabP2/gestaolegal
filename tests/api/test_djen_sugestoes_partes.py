"""Sugestões exatas e importação explícita sem parte, sem consultas externas."""

# ruff: noqa: F811

from sqlalchemy import insert, update
from gestaolegal.database.session import get_session
from gestaolegal.database.tables import atendido_nomes, atendidos
from gestaolegal.utils.request_context import contexto_tenant
from .conftest import (
    TENANT_DAJ,
    TENANT_OUTRO,
    UNIDADE_OUTRO,
    UNIDADE_BH,
    UNIDADE_NL,
    get_success_data,
)
from .test_djen_exemplos import lote, djen, transporte  # noqa: F401


def test_sugestoes_nomes_variacoes_homonimos_e_unidade(client, auth_headers, lote):
    session = get_session()
    with contexto_tenant(TENANT_DAJ):
        ids = []
        for nome, unidade, status in [
            ("  FULANA DE TAL FICTICIA  ", UNIDADE_BH, 1),
            ("Outra grafia", UNIDADE_BH, 1),
            ("Fulana de Tal Fictícia", UNIDADE_NL, 1),
            ("Fulana de Tal Fictícia", UNIDADE_BH, 0),
            ("Fulana de Tal", UNIDADE_BH, 1),
        ]:
            ids.append(
                session.execute(
                    insert(atendidos).values(
                        nome=nome,
                        unidade_id=unidade,
                        tenant_id=TENANT_DAJ,
                        status=status,
                        sem_triagem=True,
                    )
                ).lastrowid
            )
        session.execute(
            insert(atendido_nomes).values(
                id_atendido=ids[1], nome="Fulana de Tal Fictícia", tenant_id=TENANT_DAJ
            )
        )
        session.commit()
    with contexto_tenant(TENANT_OUTRO):
        session.execute(
            insert(atendidos).values(
                nome="Fulana de Tal Fictícia",
                unidade_id=UNIDADE_OUTRO,
                tenant_id=TENANT_OUTRO,
                status=1,
                sem_triagem=True,
            )
        )
        session.commit()
    resposta = client.get("/api/djen/acervo", headers=auth_headers)
    assert resposta.status_code == 200, resposta.json
    for item in get_success_data(resposta)["items"]:
        assert "Fulana de Tal Fictícia" in item["partes"]
        assert {a["id"] for a in item["atendidos_sugeridos"]} == set(ids[:2])
    with contexto_tenant(TENANT_DAJ):
        session.execute(
            update(atendidos)
            .where(atendidos.c.tenant_id == TENANT_DAJ, atendidos.c.id.in_(ids))
            .values(status=0)
        )
        session.commit()


def test_importar_sem_parte_cria_processo_e_reimportar_nao_duplica(
    client, auth_headers, lote
):
    corpo = {"ids": [91002], "sem_parte": True, "contexto_ids": []}
    resposta = client.post(
        "/api/djen/busca-parte/importar", headers=auth_headers, json=corpo
    )
    assert resposta.status_code == 200, resposta.json
    [pid] = get_success_data(resposta)["processos_criados"]
    detalhe = get_success_data(
        client.get(f"/api/processos/{pid}", headers=auth_headers)
    )
    assert detalhe["partes"] == [] and detalhe["id_caso"] is None
    assert detalhe["total_publicacoes"] == 1
    repetida = client.post(
        "/api/djen/busca-parte/importar", headers=auth_headers, json=corpo
    )
    assert repetida.status_code == 200, repetida.json
    assert get_success_data(repetida)["processos_criados"] == []


def test_filtro_multiplos_tribunais_no_acervo_e_operacao(client, auth_headers, lote):
    from gestaolegal.database.tables import djen_publicacoes

    with contexto_tenant(TENANT_DAJ):
        session = get_session()
        session.execute(update(djen_publicacoes).where(
            djen_publicacoes.c.tenant_id == TENANT_DAJ,
            djen_publicacoes.c.id_djen == 91002,
        ).values(sigla_tribunal="TRT3"))
        session.commit()
    resposta = client.post('/api/djen/busca-parte/importar', headers=auth_headers,
                          json={'ids': [91001, 91002], 'sem_parte': True, 'contexto_ids': []})
    assert resposta.status_code == 200, resposta.json
    for rota in ['/api/djen/acervo', '/api/djen/publicacoes']:
        for query, esperado in [
            ('tribunal=TJMG', {91001}),
            ('tribunal=TRT3', {91002}),
            ('tribunal=TJMG&tribunal=TRT3', {91001, 91002}),
            ('tribunal=TJMG,TRT3', {91001, 91002}),
            ('tribunal=TRF6', set()),
            ('tribunal=', {91001, 91002}),
        ]:
            r = client.get(f'{rota}?{query}', headers=auth_headers)
            assert r.status_code == 200, r.json
            itens = get_success_data(r)['items']
            assert len(itens) == len(esperado)
            assert {item['sigla_tribunal'] for item in itens} == {
                {91001: 'TJMG', 91002: 'TRT3'}[id_djen] for id_djen in esperado
            }


def test_polo_filtra_a_mesma_parte_no_acervo_e_operacao(client, auth_headers, lote):
    from sqlalchemy import select
    from gestaolegal.database.tables import djen_publicacoes

    with contexto_tenant(TENANT_DAJ):
        session = get_session()
        for id_djen, polo in [(91001, 'A'), (91002, 'P')]:
            session.execute(update(djen_publicacoes).where(
                djen_publicacoes.c.tenant_id == TENANT_DAJ,
                djen_publicacoes.c.id_djen == id_djen,
            ).values(destinatarios=[{'nome': 'UFMG', 'polo': polo},
                                    {'nome': 'Outra parte', 'polo': 'P' if polo == 'A' else 'A'}]))
        session.commit()
        numeros = dict(session.execute(select(djen_publicacoes.c.id_djen, djen_publicacoes.c.numero_processo).where(
            djen_publicacoes.c.tenant_id == TENANT_DAJ,
            djen_publicacoes.c.id_djen.in_([91001, 91002]),
        )).all())
    r = client.post('/api/djen/busca-parte/importar', headers=auth_headers,
                    json={'ids': [91001, 91002], 'sem_parte': True, 'contexto_ids': []})
    assert r.status_code == 200, r.json
    for rota in ['/api/djen/acervo', '/api/djen/publicacoes']:
        for query, ids in [
            ('nome_parte=UFMG&polo=A', [91001]),
            ('nome_parte=UFMG&polo=P', [91002]),
            ('nome_parte=Outra&polo=P', [91001]),
            ('nome_parte=UFMG', [91001, 91002]),
            ('polo=A', [91001, 91002]),
        ]:
            r = client.get(f'{rota}?{query}', headers=auth_headers)
            assert r.status_code == 200, r.json
            assert {i['numero_processo'] for i in get_success_data(r)['items']} == {numeros[i] for i in ids}
        assert client.get(f'{rota}?polo=X', headers=auth_headers).status_code == 400
