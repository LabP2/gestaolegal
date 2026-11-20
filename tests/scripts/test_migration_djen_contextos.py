"""Migração aditiva preserva contextos e rótulos existentes."""
import importlib
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_upgrade_downgrade_contextos_preserva_legado():
    engine = sa.create_engine('sqlite://')
    with engine.begin() as conn:
        conn.exec_driver_sql('CREATE TABLE tenants (id INTEGER PRIMARY KEY)')
        conn.exec_driver_sql('CREATE TABLE djen_contextos (id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, nome TEXT NOT NULL, UNIQUE(tenant_id,id))')
        conn.exec_driver_sql('CREATE TABLE djen_modelos (id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, UNIQUE(tenant_id,id))')
        conn.exec_driver_sql('CREATE TABLE djen_publicacao_contextos (id INTEGER PRIMARY KEY, rotulo TEXT NOT NULL)')
        conn.exec_driver_sql("INSERT INTO djen_contextos VALUES (1,1,'Contexto existente')")
        conn.exec_driver_sql("INSERT INTO djen_publicacao_contextos VALUES (1,'relevante')")
        migration = importlib.import_module('migrations.versions.49b08df53ce1_djen_contextos_criterios_treinos')
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
        row = conn.execute(sa.text('SELECT * FROM djen_contextos')).mappings().one()
        assert row['nome'] == 'Contexto existente' and row['versao'] == 1
        assert row['criterios'] is None and row['avaliacoes_versao'] == 0
        assert conn.exec_driver_sql('SELECT rotulo,ativo FROM djen_publicacao_contextos').one() == ('relevante', 1)
        assert 'djen_treinos' in sa.inspect(conn).get_table_names()
        with Operations.context(MigrationContext.configure(conn)):
            migration.downgrade()
        assert conn.exec_driver_sql('SELECT rotulo FROM djen_publicacao_contextos').scalar_one() == 'relevante'
        assert 'djen_treinos' not in sa.inspect(conn).get_table_names()
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
        assert conn.exec_driver_sql('SELECT ativo FROM djen_publicacao_contextos').scalar_one() == 1
