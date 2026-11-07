"""Regras estruturais da multitenancy sobre o `metadata`.

Uma tabela nova sem `tenant_id`, ou uma unicidade que esqueça o tenant, quebra
estes testes antes de chegar a uma migration.
"""

from sqlalchemy import ForeignKeyConstraint, UniqueConstraint

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
        # A FK de uma coluna só é para `tenants`. As demais FKs em que o
        # tenant_id aparece são as compostas (PR 5), testadas abaixo.
        simples = {
            fk.target_fullname
            for fk in coluna.foreign_keys
            if len(fk.constraint.columns) == 1
        }
        assert simples == {"tenants.id"}, tabela.name
        for fk in coluna.foreign_keys:
            if len(fk.constraint.columns) > 1:
                assert fk.column.name == "tenant_id", (tabela.name, fk.target_fullname)


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


def _fks_entre_tabelas_de_tenant():
    for tabela in _tabelas_de_tenant():
        for fk in tabela.foreign_key_constraints:
            if fk.referred_table.name not in TABELAS_GLOBAIS:
                yield tabela, fk


def test_fk_entre_tabelas_de_tenant_e_composta_com_o_tenant():
    fks = list(_fks_entre_tabelas_de_tenant())
    assert fks, "nenhuma FK entre tabelas de tenant"
    for tabela, fk in fks:
        locais = [c.name for c in fk.columns]
        remotas = [e.column.name for e in fk.elements]
        assert len(locais) == 2 and locais[0] == "tenant_id", (tabela.name, locais)
        assert remotas == ["tenant_id", "id"], (tabela.name, fk.name, remotas)


def test_coluna_de_id_nao_tem_fk_simples_para_tabela_de_tenant():
    # Uma FK simples ao lado da composta deixaria o banco aceitar o par errado
    # quando a composta for removida por engano.
    for tabela in _tabelas_de_tenant():
        for fk in tabela.foreign_key_constraints:
            if len(fk.columns) == 1:
                assert fk.referred_table.name in TABELAS_GLOBAIS, (
                    tabela.name,
                    fk.name,
                )


def test_toda_tabela_referenciada_tem_unique_tenant_id_id():
    for tabela, fk in _fks_entre_tabelas_de_tenant():
        pai = fk.referred_table
        unicas = {
            tuple(c.name for c in uc.columns)
            for uc in pai.constraints
            if isinstance(uc, UniqueConstraint)
        }
        assert ("tenant_id", "id") in unicas, pai.name


def test_nomes_das_constraints_cabem_no_mysql():
    for tabela in metadata.sorted_tables:
        for constraint in tabela.constraints:
            if isinstance(constraint, (ForeignKeyConstraint, UniqueConstraint)):
                assert constraint.name is None or len(constraint.name) <= 64, (
                    constraint.name
                )
