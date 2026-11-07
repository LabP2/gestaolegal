"""FKs compostas (multitenant, PR 5): o banco recusa ligar dois NPJs.

Roda num SQLite próprio com `PRAGMA foreign_keys=ON`. O banco dos testes da
API não liga as FKs, então é aqui que a garantia do banco é exercitada.
"""

import importlib.util
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Integer,
    Numeric,
    create_engine,
    event,
    exc,
)

from gestaolegal.database.tables import TABELAS_GLOBAIS, metadata

RAIZ = Path(__file__).resolve().parents[2]
MIGRATION = RAIZ / "migrations/versions/c2d3e4f5a6b7_fks_compostas.py"


@pytest.fixture
def conn():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def foreign_keys(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    metadata.create_all(engine)
    with engine.begin() as connection:
        for tenant_id in (1, 2):
            connection.execute(
                metadata.tables["tenants"].insert(),
                {
                    "id": tenant_id,
                    "nome": f"NPJ {tenant_id}",
                    "sigla": f"N{tenant_id}",
                    "slug": f"npj-{tenant_id}",
                    "ativo": True,
                    "criado_em": datetime.now(),
                },
            )
        yield connection
    engine.dispose()


def _valor(coluna):
    tipo = coluna.type
    if isinstance(tipo, Boolean):
        return False
    if isinstance(tipo, DateTime):
        return datetime(2026, 1, 1)
    if isinstance(tipo, Date):
        return date(2026, 1, 1)
    if isinstance(tipo, (Integer, Numeric)):
        return 0
    return "x"


def _inserir(conn, nome_tabela: str, **valores) -> int:
    """Insere uma linha preenchendo as colunas obrigatórias que faltarem."""
    tabela = metadata.tables[nome_tabela]
    linha = dict(valores)
    for coluna in tabela.columns:
        obrigatoria = not coluna.nullable and coluna.default is None
        obrigatoria = obrigatoria and coluna.server_default is None
        if coluna.name in linha or coluna.autoincrement is True or not obrigatoria:
            continue
        if coluna.primary_key and isinstance(coluna.type, Integer):
            continue
        linha[coluna.name] = _valor(coluna)
    return conn.execute(tabela.insert(), linha).inserted_primary_key[0]


def _unidade(conn, tenant_id: int) -> int:
    return _inserir(
        conn, "unidades", tenant_id=tenant_id, nome=f"U{tenant_id}", sigla=f"U{tenant_id}"
    )


def test_registro_aponta_para_pai_do_mesmo_tenant(conn):
    unidade = _unidade(conn, 1)
    _inserir(conn, "plantao", tenant_id=1, unidade_id=unidade)


def test_registro_nao_aponta_para_unidade_de_outro_tenant(conn):
    unidade_outro = _unidade(conn, 2)
    with pytest.raises(exc.IntegrityError, match="FOREIGN KEY"):
        _inserir(conn, "plantao", tenant_id=1, unidade_id=unidade_outro)


def test_tabela_de_ligacao_nao_cruza_tenants(conn):
    unidade_1, unidade_2 = _unidade(conn, 1), _unidade(conn, 2)
    endereco_2 = _inserir(conn, "enderecos", tenant_id=2)
    atendido_2 = _inserir(
        conn, "atendidos", tenant_id=2, unidade_id=unidade_2, endereco_id=endereco_2
    )
    orientacao_1 = _inserir(conn, "orientacao_juridica", tenant_id=1, unidade_id=unidade_1)
    with pytest.raises(exc.IntegrityError, match="FOREIGN KEY"):
        _inserir(
            conn,
            "atendido_xOrientacaoJuridica",
            tenant_id=1,
            id_orientacaoJuridica=orientacao_1,
            id_atendido=atendido_2,
        )


def test_mudar_o_tenant_do_filho_quebra_a_fk(conn):
    unidade = _unidade(conn, 1)
    plantao = _inserir(conn, "plantao", tenant_id=1, unidade_id=unidade)
    with pytest.raises(exc.IntegrityError, match="FOREIGN KEY"):
        conn.execute(
            metadata.tables["plantao"]
            .update()
            .where(metadata.tables["plantao"].c.id == plantao)
            .values(tenant_id=2)
        )


def _carregar_migration():
    spec = importlib.util.spec_from_file_location("fks_compostas", MIGRATION)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_migration_cria_as_fks_que_o_metadata_declara():
    # A lista literal da M3 e o tables.py (usado pelo create_all dos testes)
    # precisam dizer a mesma coisa. FKs criadas depois da M3 entram em
    # migrations próprias e não precisam estar na lista.
    migration = _carregar_migration()
    declaradas = {}
    for tabela in metadata.sorted_tables:
        if tabela.name in TABELAS_GLOBAIS:
            continue
        for fk in tabela.foreign_key_constraints:
            if fk.referred_table.name in TABELAS_GLOBAIS:
                continue
            coluna = [c.name for c in fk.columns][1]
            declaradas[fk.name] = (
                tabela.name,
                coluna,
                fk.referred_table.name,
                fk.ondelete,
            )
    for tabela, coluna, pai, ondelete, nome in migration.FKS:
        assert declaradas.get(nome) == (tabela, coluna, pai, ondelete), nome
    assert set(migration.PAIS) <= {pai for _, _, pai, _ in declaradas.values()}
