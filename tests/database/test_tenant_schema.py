"""Regras estruturais da multitenancy sobre o `metadata`.

Uma tabela nova sem `tenant_id`, ou uma unicidade que esqueça o tenant, quebra
estes testes antes de chegar a uma migration.
"""

from sqlalchemy import UniqueConstraint

from gestaolegal.database.tables import (
    TABELAS_GLOBAIS,
    coluna_tenant,
    metadata,
)

# Unicidades que valem para a plataforma inteira, de propósito.
UNICAS_GLOBAIS = {
    # O e-mail identifica o NPJ no login (docs/plano-multitenant.md, §5).
    ("usuarios", ("email",)),
    # 256 bits aleatórios; o link de senha chega antes de haver tenant.
    ("password_reset_tokens", ("token_hash",)),
}


def _tabelas_de_tenant():
    return [t for t in metadata.sorted_tables if t.name not in TABELAS_GLOBAIS]


def test_tabelas_globais_existem_e_nao_tem_tenant_id():
    for nome in TABELAS_GLOBAIS:
        assert nome in metadata.tables, nome
        assert "tenant_id" not in metadata.tables[nome].c, nome


def test_toda_tabela_de_tenant_tem_tenant_id_obrigatorio_indexado_e_com_fk():
    tabelas = _tabelas_de_tenant()
    assert len(tabelas) == 28
    for tabela in tabelas:
        assert "tenant_id" in tabela.c, tabela.name
        coluna = tabela.c.tenant_id
        assert coluna.nullable is False, tabela.name
        assert coluna.index is True, tabela.name
        assert coluna.default is None and coluna.server_default is None, tabela.name
        assert {fk.target_fullname for fk in coluna.foreign_keys} == {"tenants.id"}, (
            tabela.name
        )


def test_toda_unicidade_de_tabela_de_tenant_inclui_o_tenant():
    for tabela in _tabelas_de_tenant():
        unicas = [
            tuple(c.name for c in uc.columns)
            for uc in tabela.constraints
            if isinstance(uc, UniqueConstraint)
        ]
        unicas += [(c.name,) for c in tabela.columns if c.unique]
        for colunas in unicas:
            if (tabela.name, colunas) in UNICAS_GLOBAIS:
                continue
            assert "tenant_id" in colunas, f"{tabela.name}{colunas} sem tenant_id"


def test_unicidades_globais_declaradas_existem():
    # A lista de exceções não pode guardar uma regra que já não vale.
    for nome, colunas in UNICAS_GLOBAIS:
        tabela = metadata.tables[nome]
        assert any(
            (c.name,) == colunas for c in tabela.columns if c.unique
        ), (nome, colunas)


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
