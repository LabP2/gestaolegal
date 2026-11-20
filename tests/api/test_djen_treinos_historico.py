# ruff: noqa: F811
from sqlalchemy import select
from gestaolegal.database.session import get_session
from gestaolegal.database.tables import djen_treinos, djen_modelos
from gestaolegal.services.djen_contexto_service import DjenContextoService
from gestaolegal.utils.request_context import contexto_tenant
from .conftest import TENANT_DAJ, UNIDADE_BH, get_success_data
from .test_djen_exemplos import djen, transporte  # noqa: F401
from .test_djen_contextos import criar
from .test_djen_contextos_treino import semear, cnj
from .test_djen_modelos_fila import solicitar


def test_treino_registra_etapas_metricas_e_bases_sem_vazamento(app, client, auth_headers, djen):
    cid = criar(client, auth_headers)
    semear(app, cid, 240, lambda i: i % 2 == 0, lambda i: cnj(i // 4))
    pedido = solicitar(client, auth_headers, cid)
    solicitar(client, auth_headers, cid)
    with app.test_request_context(), contexto_tenant(TENANT_DAJ):
        s = DjenContextoService()
        resultado = s.executar_treino(cid, UNIDADE_BH, pedido['treino_token'])
        assert resultado['id'] > 0
        row = s.session.execute(select(djen_treinos).where(djen_treinos.c.tenant_id == TENANT_DAJ, djen_treinos.c.contexto_id == cid)).mappings().one()
        assert row['etapas_concluidas'] == 7 and row['status'] == 'concluido'
        assert row['iniciado_em'] <= row['finalizado_em']
        assert len(row['logs']) == 10
        m = row['metricas']
        assert m['bases']['treino']['exemplos'] + m['bases']['validacao']['exemplos'] == 240
        assert m['bases']['treino']['processos'] + m['bases']['validacao']['processos'] == 60
        assert not set(m['ids_teste']) & set(m['ids_treino'])
        assert sum(sum(linha) for linha in m['matriz_confusao']) == m['teste']
        assert m['origens'] == {'classificacao': 240}
        assert m['classes'] == {'relevante': 120, 'irrelevante': 120}
        assert m['algoritmo'] == 'TF-IDF + regressão logística'
    historico = get_success_data(client.get(f'/api/djen/contextos/{cid}/treinos', headers=auth_headers))
    assert historico['total'] == 1
    assert 'amostra' not in historico['items'][0]['metricas'] and 'ids_treino' not in historico['items'][0]['metricas']
    assert 'token' not in historico['items'][0]
    assert client.put(f'/api/djen/contextos/{cid}', headers=auth_headers, json={'nome': 'Novo objetivo', 'versao': 1}).status_code == 200
    ctx = next(x for x in get_success_data(client.get('/api/djen/contextos', headers=auth_headers)) if x['id'] == cid)
    assert ctx['modelo_desatualizado'] is True
    # O registro anterior continua com os critérios originais.
    assert get_success_data(client.get(f'/api/djen/contextos/{cid}/treinos', headers=auth_headers))['items'][0]['contexto_snapshot']['nome'] == 'Parte teste'


def test_falha_persistida_retentativa_e_edicao_bloqueada_na_fila(app, client, auth_headers, djen):
    cid = criar(client, auth_headers)
    semear(app, cid, 240, lambda i: i % 2 == 0, lambda i: cnj(i // 4), texto=lambda i: ' ')
    pedido = solicitar(client, auth_headers, cid)
    assert client.put(f'/api/djen/contextos/{cid}', headers=auth_headers, json={'nome': 'Novo objetivo', 'versao': 1}).status_code == 400
    with app.test_request_context(), contexto_tenant(TENANT_DAJ):
        s = DjenContextoService()
        assert s.executar_treino(cid, UNIDADE_BH, pedido['treino_token']) is None
        assert s.ultimo_modelo(cid) is None
    historico = get_success_data(client.get(f'/api/djen/contextos/{cid}/treinos', headers=auth_headers))
    assert historico['items'][0]['status'] == 'erro'
    assert historico['items'][0]['erro']
    assert historico['items'][0]['etapas_concluidas'] < 7
    novo = solicitar(client, auth_headers, cid)
    assert novo['treino_token'] != pedido['treino_token']
    with app.test_request_context(), contexto_tenant(TENANT_DAJ):
        DjenContextoService().falhar_treino(cid, pedido['treino_token'], 'Execução antiga')
    historico = get_success_data(client.get(f'/api/djen/contextos/{cid}/treinos', headers=auth_headers))
    assert historico['total'] == 2
    assert historico['items'][0]['status'] == 'na_fila'
    assert historico['items'][1]['status'] == 'erro'
