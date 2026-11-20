# ruff: noqa: F811
"""Critérios reutilizam os filtros do acervo, com revisão e histórico preservados."""
import pytest
from sqlalchemy import select, update
from gestaolegal.database.session import get_session
from gestaolegal.database.tables import djen_publicacoes, djen_publicacao_contextos, djen_contextos
from gestaolegal.services.djen_contexto_service import DjenContextoService
from gestaolegal.utils.request_context import contexto_tenant
from .conftest import TENANT_DAJ, UNIDADE_BH, get_success_data
from .test_djen_exemplos import lote, djen, transporte, headers_outro  # noqa: F401
from .test_djen_contextos import listar, rotular


def criar_criterios(client, headers, criterios):
    resposta = client.post('/api/djen/contextos', headers=headers, json={'nome': 'Critérios do acervo', 'descricao': 'Relevância para a assistência', 'criterios': criterios})
    assert resposta.status_code == 200, resposta.json
    return get_success_data(resposta)


def test_contexto_sem_parte_e_edicao_preserva_rotulos(app, client, auth_headers, lote):
    ctx = criar_criterios(client, auth_headers, {'tribunal': ['TJMG']})
    cid = ctx['id']
    assert listar(client, auth_headers, cid)['total'] == 2
    assert rotular(client, auth_headers, cid, 'relevante').status_code == 200
    corpo = {'nome': 'Contexto restrito', 'criterios': {'tribunal': ['TRF6']}, 'versao': 1}
    previa = client.post(f'/api/djen/contextos/{cid}/previa', headers=auth_headers, json=corpo)
    assert get_success_data(previa) == dict(total=0, entram=0, saem=2, permanecem=0)
    editado = client.put(f'/api/djen/contextos/{cid}', headers=auth_headers, json=corpo)
    assert get_success_data(editado)['versao'] == 2
    assert listar(client, auth_headers, cid)['total'] == 0
    assert rotular(client, auth_headers, cid, 'irrelevante').status_code == 400
    with app.test_request_context(), contexto_tenant(TENANT_DAJ):
        rows = get_session().execute(select(djen_publicacao_contextos).where(djen_publicacao_contextos.c.tenant_id == TENANT_DAJ, djen_publicacao_contextos.c.contexto_id == cid)).mappings().all()
        assert len(rows) == 2 and all(not x['ativo'] for x in rows)
        assert any(x['rotulo'] == 'relevante' for x in rows)
    corpo.update(criterios={}, versao=2)
    assert client.put(f'/api/djen/contextos/{cid}', headers=auth_headers, json=corpo).status_code == 200
    itens = listar(client, auth_headers, cid)['items']
    assert len(itens) == 2
    assert next(i for i in itens if i['id_djen'] == 91001)['rotulo'] == 'relevante'
    assert client.put(f'/api/djen/contextos/{cid}', headers=auth_headers, json=corpo).status_code == 400


def test_criterios_combinados_iguais_acervo_e_novas_publicacoes(app, client, auth_headers, lote):
    with app.test_request_context(), contexto_tenant(TENANT_DAJ):
        session = get_session()
        session.execute(update(djen_publicacoes).where(djen_publicacoes.c.tenant_id == TENANT_DAJ, djen_publicacoes.c.id_djen == 91001).values(destinatarios=[dict(nome='Universidade Teste', polo='P')], advogados=[dict(numero_oab='123', uf_oab='MG')]))
        session.commit()
    criterios = dict(nome_parte='Universidade', polo='P', oab='123/MG', tribunal=['TJMG'], inicio='2020-01-01', fim='2030-01-01', fonte='parte')
    acervo = get_success_data(client.get('/api/djen/acervo', headers=auth_headers, query_string=criterios))
    ctx = criar_criterios(client, auth_headers, criterios)
    assert acervo['total'] == 1
    assert [i['id_djen'] for i in listar(client, auth_headers, ctx['id'])['items']] == [i['id_djen'] for i in acervo['items']]
    # Alteração da publicação e nova captura atualizam o pertencimento, sem apagar histórico.
    with app.test_request_context(), contexto_tenant(TENANT_DAJ):
        session = get_session()
        session.execute(update(djen_publicacoes).where(djen_publicacoes.c.tenant_id == TENANT_DAJ, djen_publicacoes.c.id_djen == 91002).values(destinatarios=[dict(nome='Universidade Teste', polo='P')], advogados=[dict(numero_oab='123', uf_oab='MG')]))
        pid = session.execute(select(djen_publicacoes.c.id).where(djen_publicacoes.c.tenant_id == TENANT_DAJ, djen_publicacoes.c.id_djen == 91002)).scalar_one()
        DjenContextoService().sincronizar_publicacao(pid)
        session.commit()
    assert listar(client, auth_headers, ctx['id'])['total'] == 2


@pytest.mark.parametrize('criterios', [{'rotulo': 'relevante'}, {'sugestao': 'relevante'}, {'situacao': 'vinculada'}, {'contexto_id': 1}, {'polo': 'A'}, {'inicio': 'ontem'}, {'inicio': '2026-12-01', 'fim': '2026-01-01'}, {'tribunal': 'TJMG'}])
def test_criterios_invalidos(client, auth_headers, djen, criterios):
    resposta = client.post('/api/djen/contextos', headers=auth_headers, json={'nome': 'Teste inválido', 'criterios': criterios})
    assert resposta.status_code == 400


def test_edicao_historico_e_previa_isolados_por_npj(client, auth_headers, headers_outro, lote):
    ctx = criar_criterios(client, auth_headers, {})
    for metodo, sufixo, corpo in [('get', '/treinos', None), ('put', '', {'nome': 'Outro nome', 'versao': 1}), ('post', '/previa', {'criterios': {}})]:
        resposta = getattr(client, metodo)(f'/api/djen/contextos/{ctx["id"]}{sufixo}', headers=headers_outro, json=corpo)
        assert resposta.status_code in (403, 404), resposta.json


def test_variacoes_acervo_equivalem_contexto_e_respeitam_polo(client, auth_headers, lote):
    with contexto_tenant(TENANT_DAJ):
        session = get_session()
        for id_djen, nome in [(91001, 'UFMG'), (91002, 'Universidade Federal de Minas Gerais')]:
            session.execute(update(djen_publicacoes).where(
                djen_publicacoes.c.tenant_id == TENANT_DAJ, djen_publicacoes.c.id_djen == id_djen
            ).values(destinatarios=[dict(nome=nome, polo='P'), dict(nome='Outra parte', polo='A')]))
        session.commit()
    filtros = {'nome_parte': 'UFMG', 'nomes': ['Universidade Federal de Minas Gerais', 'UFMG'], 'polo': 'P'}
    acervo = get_success_data(client.get('/api/djen/acervo', headers=auth_headers, query_string=filtros))
    assert acervo['total'] == 2
    assert len(acervo['items']) == 2  # variações sobrepostas não duplicam linhas
    ctx = criar_criterios(client, auth_headers, {'nomes': ['UFMG', 'Universidade Federal de Minas Gerais'], 'polo': 'P'})
    assert {i['id_djen'] for i in listar(client, auth_headers, ctx['id'])['items']} == {i['id_djen'] for i in acervo['items']}
    filtros['polo'] = 'A'
    assert get_success_data(client.get('/api/djen/acervo', headers=auth_headers, query_string=filtros))['total'] == 0
    filtros['polo'] = 'P'
    filtros['tribunal'] = 'TRF6'
    assert get_success_data(client.get('/api/djen/acervo', headers=auth_headers, query_string=filtros))['total'] == 0


def test_variacoes_limite_validado(client, auth_headers, lote):
    resposta = client.get('/api/djen/acervo', headers=auth_headers, query_string={'nomes': ['Universidade'] * 21})
    assert resposta.status_code == 400


def test_excluir_contexto_preserva_publicacoes_operacao_e_outros_contextos(client, auth_headers, lote):
    from datetime import datetime
    from sqlalchemy import insert
    from gestaolegal.database.tables import djen_contexto_historico, djen_modelos, djen_treinos, djen_comunicacoes, processos
    from .test_djen_api import _linhas

    ctx = criar_criterios(client, auth_headers, {})
    outro = criar_criterios(client, auth_headers, {})
    assert rotular(client, auth_headers, ctx['id'], 'relevante').status_code == 200
    assert rotular(client, auth_headers, outro['id'], 'irrelevante').status_code == 200
    pubs, ops, procs = _linhas(djen_publicacoes), _linhas(djen_comunicacoes), _linhas(processos)
    with contexto_tenant(TENANT_DAJ):
        session = get_session()
        mid = session.execute(insert(djen_modelos).values(tenant_id=TENANT_DAJ, contexto_id=ctx['id'], criado_em=datetime.now(), artefato={}, metricas={})).lastrowid
        session.execute(update(djen_publicacao_contextos).where(djen_publicacao_contextos.c.contexto_id == ctx['id'], djen_publicacao_contextos.c.tenant_id == TENANT_DAJ).values(modelo_id=mid))
        session.execute(insert(djen_treinos).values(tenant_id=TENANT_DAJ, contexto_id=ctx['id'], token='exclusao-teste', status='concluido', etapa='Concluído', solicitado_em=datetime.now(), contexto_snapshot={}, logs=[], modelo_id=mid))
        session.commit()
    resposta = client.delete(f'/api/djen/contextos/{ctx["id"]}', headers=auth_headers)
    assert resposta.status_code == 200, resposta.json
    assert _linhas(djen_publicacoes) == pubs
    assert _linhas(djen_comunicacoes) == ops
    assert _linhas(processos) == procs
    assert all(row['contexto_id'] != ctx['id'] for row in _linhas(djen_publicacao_contextos))
    assert all(row['contexto_id'] != ctx['id'] for row in _linhas(djen_modelos))
    assert all(row['contexto_id'] != ctx['id'] for row in _linhas(djen_treinos))
    assert len(_linhas(djen_contexto_historico)) == 1  # histórico do outro contexto
    assert listar(client, auth_headers, outro['id'])['total'] == 2
    assert client.delete(f'/api/djen/contextos/{ctx["id"]}', headers=auth_headers).status_code == 404


@pytest.mark.parametrize('status', ['na_fila', 'executando'])
def test_excluir_contexto_recusa_treinamento_ativo(client, auth_headers, lote, status):
    ctx = criar_criterios(client, auth_headers, {})
    with contexto_tenant(TENANT_DAJ):
        session = get_session()
        session.execute(update(djen_contextos).where(djen_contextos.c.id == ctx['id'], djen_contextos.c.tenant_id == TENANT_DAJ).values(treino_status=status))
        session.commit()
    resposta = client.delete(f'/api/djen/contextos/{ctx["id"]}', headers=auth_headers)
    assert resposta.status_code == 400
    assert listar(client, auth_headers, ctx['id'])['total'] == 2


def test_excluir_contexto_rollback_em_falha(client, auth_headers, lote, monkeypatch):
    from sqlalchemy.sql.dml import Delete
    from gestaolegal.database.tables import djen_contexto_historico
    from .test_djen_api import _linhas
    ctx = criar_criterios(client, auth_headers, {})
    assert rotular(client, auth_headers, ctx['id'], 'relevante').status_code == 200
    antes = _linhas(djen_contexto_historico)
    with contexto_tenant(TENANT_DAJ):
        repo = DjenContextoService()
        executar = repo.session.execute
        def falhar(stmt, *args, **kwargs):
            if isinstance(stmt, Delete) and stmt.table.name == 'djen_contextos':
                raise RuntimeError('Falha simulada')
            return executar(stmt, *args, **kwargs)
        with monkeypatch.context() as patch:
            patch.setattr(repo.session, 'execute', falhar)
            with pytest.raises(RuntimeError, match='Falha simulada'):
                repo.excluir(ctx['id'], UNIDADE_BH)
    assert _linhas(djen_contexto_historico) == antes
    assert listar(client, auth_headers, ctx['id'])['total'] == 2
