"""Regras estruturais da multitenancy sobre o `metadata`.

Nesta fase só as tabelas globais existem. A exigência de `tenant_id` em todas
as outras tabelas entra junto com a coluna (PR 2 do plano).
"""

from gestaolegal.database.tables import (
    TABELAS_GLOBAIS,
    coluna_tenant,
    metadata,
)


def test_tabelas_globais_existem_e_nao_tem_tenant_id():
    for nome in TABELAS_GLOBAIS:
        assert nome in metadata.tables, nome
        assert "tenant_id" not in metadata.tables[nome].c, nome


def test_coluna_tenant_e_obrigatoria_indexada_e_sem_default():
    coluna = coluna_tenant()
    assert coluna.name == "tenant_id"
    assert coluna.nullable is False
    assert coluna.index is True
    assert coluna.default is None and coluna.server_default is None
    (fk,) = coluna.foreign_keys
    assert fk.target_fullname == "tenants.id"


def test_coluna_tenant_devolve_uma_coluna_nova_a_cada_chamada():
    # Column não pode ser compartilhada entre tabelas.
    assert coluna_tenant() is not coluna_tenant()
