"""Migration M1 da multitenancy, exercitada num banco descartável."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

from gestaolegal.database.tables import TENANT_PADRAO_ID, metadata

RAIZ = Path(__file__).resolve().parents[2]
MIGRATION = RAIZ / "migrations/versions/a0b1c2d3e4f5_tenants.py"
MIGRATION_DJEN = RAIZ / "migrations/versions/d3e4f5a6b7c8_djen.py"

# Colunas que migrations posteriores à M1 acrescentam, com a migration que as
# cria. A M1 não pode mudar; a comparação com o tables.py desconta só estas.
COLUNAS_POSTERIORES = {
    "tenants": {"djen_ativo": MIGRATION_DJEN},
}


def _carregar_migration():
    spec = importlib.util.spec_from_file_location("tenants_migration", MIGRATION)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def _executar(connection, funcao):
    with Operations.context(MigrationContext.configure(connection)):
        funcao()


def _colunas(connection, tabela):
    return {
        c["name"]: c["nullable"] for c in sa.inspect(connection).get_columns(tabela)
    }


def test_alembic_tem_um_unico_head():
    # Dois heads derrubam produção e os demais testes não percebem (usam
    # create_all, não Alembic).
    script = ScriptDirectory.from_config(Config(str(RAIZ / "migrations/alembic.ini")))
    assert len(script.get_heads()) == 1, script.get_heads()


def test_upgrade_cria_tabelas_e_tenant_inicial():
    migration = _carregar_migration()
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        _executar(connection, migration.upgrade)

        for tabela in ("tenants", "plataforma_admins"):
            # O esquema criado pela migration bate com o declarado em tables.py
            # (que os testes da API usam via create_all).
            posteriores = COLUNAS_POSTERIORES.get(tabela, {})
            esperado = {
                c.name: c.nullable
                for c in metadata.tables[tabela].columns
                if c.name not in posteriores
            }
            assert _colunas(connection, tabela) == esperado
            for coluna, origem in posteriores.items():
                assert coluna in metadata.tables[tabela].c, (tabela, coluna)
                assert f"ADD COLUMN {coluna} " in origem.read_text(), (tabela, coluna)

        tenant = connection.execute(sa.text("SELECT * FROM tenants")).mappings().one()
        assert tenant["id"] == TENANT_PADRAO_ID
        assert tenant["slug"] == "daj-ufmg"
        assert tenant["sigla"] == "DAJ"
        assert tenant["ativo"]
        assert tenant["criado_em"] is not None
        assert tenant["id_criado_por"] is None


def test_slug_e_sigla_sao_unicos():
    migration = _carregar_migration()
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        _executar(connection, migration.upgrade)
        with pytest.raises(sa.exc.IntegrityError):
            connection.execute(
                sa.text(
                    "INSERT INTO tenants (nome, sigla, slug, ativo, criado_em) "
                    "VALUES ('Outro', 'OUT', 'daj-ufmg', 1, '2026-11-07')"
                )
            )


def test_downgrade_remove_tabelas_quando_so_existe_o_tenant_inicial():
    migration = _carregar_migration()
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        _executar(connection, migration.upgrade)
        _executar(connection, migration.downgrade)
        tabelas = set(sa.inspect(connection).get_table_names())
        assert not tabelas & {"tenants", "plataforma_admins"}


@pytest.mark.parametrize(
    "insert",
    [
        "INSERT INTO tenants (nome, sigla, slug, ativo, criado_em) "
        "VALUES ('NPJ X', 'NPJX', 'npj-x', 1, '2026-11-07')",
        "INSERT INTO plataforma_admins (nome, email, senha, ativo, criado_em) "
        "VALUES ('Admin', 'admin@plataforma.br', 'hash', 1, '2026-11-07')",
    ],
)
def test_downgrade_recusa_quando_ha_dados_a_perder(insert):
    migration = _carregar_migration()
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        _executar(connection, migration.upgrade)
        connection.execute(sa.text(insert))
        with pytest.raises(RuntimeError, match="antes do downgrade"):
            _executar(connection, migration.downgrade)
        assert {"tenants", "plataforma_admins"} <= set(
            sa.inspect(connection).get_table_names()
        )
