"""Exercita a migration em um banco descartável, sem acesso a dados reais."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations/versions/e2f3a4b5c6d7_dados_juridicos_pj.py"
)


def test_migration_preserva_legado_e_bloqueia_downgrade_sem_respostas():
    spec = importlib.util.spec_from_file_location("pj_migration", MIGRATION)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    table = sa.Table(
        "assistidos_pessoa_juridica",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("enquadramento", sa.String(100), nullable=False),
        sa.Column("socios", sa.String(1000)),
        *(
            sa.Column(nome, tipo, nullable=False)
            for nome, tipo in migration.OPCIONAIS.items()
        ),
    )
    metadata.create_all(engine)
    legado = {
        "id": 1,
        "enquadramento": "microempresa",
        "socios": "Ana; João",
        "situacao_receita": "Ativa",
        "sede_bh": True,
        "area_atuacao": "Educação",
        "negocio_nascente": False,
        "orgao_registro": "Junta",
        "faturamento_anual": 1000,
        "tem_funcionarios": "nao",
    }
    with engine.begin() as connection:
        connection.execute(table.insert().values(**legado))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        columns = {
            col["name"]: col for col in sa.inspect(connection).get_columns(table.name)
        }
        assert "especificacao_enquadramento" in columns
        assert all(columns[nome]["nullable"] for nome in migration.OPCIONAIS)
        assert dict(connection.execute(sa.select(table)).mappings().one()) == legado
        connection.execute(
            sa.text(
                "INSERT INTO assistidos_pessoa_juridica (id, enquadramento, socios) VALUES (2, 'mei', '[]')"
            )
        )
        with (
            Operations.context(MigrationContext.configure(connection)),
            pytest.raises(RuntimeError, match="campos opcionais vazios"),
        ):
            migration.downgrade()
        assert "especificacao_enquadramento" in {
            c["name"] for c in sa.inspect(connection).get_columns(table.name)
        }
        # Após preencher os campos, o esquema antigo pode ser restaurado.
        connection.execute(
            table.update()
            .where(table.c.id == 2)
            .values(**{k: v for k, v in legado.items() if k in migration.OPCIONAIS})
        )
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        columns = {
            col["name"]: col for col in sa.inspect(connection).get_columns(table.name)
        }
        assert "especificacao_enquadramento" not in columns
        assert all(not columns[nome]["nullable"] for nome in migration.OPCIONAIS)
        assert (
            connection.execute(sa.select(sa.func.count()).select_from(table)).scalar()
            == 2
        )
    engine.dispose()
