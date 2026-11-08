"""Guarda de execução da multitenancy (docs/plano-multitenant.md, §2.3 e §10).

Roda num SQLite próprio, com a guarda no modo de produção (SQL textual
recusado), para exercitar cada regra isoladamente.
"""

import re
import tokenize
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import Integer, and_, bindparam, create_engine, delete, exists, insert, select, text, update, union, union_all

from sqlalchemy.sql.selectable import Select

from gestaolegal.database import guarda_tenant
from gestaolegal.database.guarda_tenant import (
    TenantLeakError,
    instalar_guarda,
    remover_guarda,
)
from gestaolegal.database.tables import (
    atendidos,
    casos,
    metadata,
    notificacao,
    tenants,
    unidades,
    usuarios,
)
from gestaolegal.repositories.repository import BaseRepository
from gestaolegal.utils.request_context import contexto_tenant, sem_tenant

RAIZ = Path(__file__).resolve().parents[2]
AGORA = datetime(2026, 11, 7)


@pytest.fixture
def conn():
    engine = create_engine("sqlite://")
    metadata.create_all(engine)
    instalar_guarda(engine)
    with engine.connect() as conexao:
        with sem_tenant("teste da guarda: tenants de partida"):
            conexao.execute(
                insert(tenants),
                [
                    {"id": 1, "nome": "DAJ", "sigla": "DAJ", "slug": "daj", "ativo": True,
                     "criado_em": AGORA},
                    {"id": 2, "nome": "Outro", "sigla": "OUT", "slug": "out", "ativo": True,
                     "criado_em": AGORA},
                ],
            )
        yield conexao
    remover_guarda(engine)
    engine.dispose()


def _recusa(conexao, stmt, *args, mensagem=""):
    with pytest.raises(TenantLeakError, match=mensagem):
        conexao.execute(stmt, *args)


class TestSelect:
    @pytest.mark.parametrize("compor", [union, union_all])
    @pytest.mark.parametrize("aninhada", [False, True])
    def test_cada_ramo_da_union_exige_filtro(self, conn, compor, aninhada):
        seguro = select(unidades.c.id).where(unidades.c.tenant_id == 1)
        inseguro = compor(seguro, select(unidades.c.id))
        if aninhada:
            inseguro = select(inseguro.subquery())
        with contexto_tenant(1):
            _recusa(conn, inseguro, mensagem="sem critério de tenant")
            conn.execute(compor(seguro, seguro))

    @pytest.mark.parametrize("nomeado", [False, True])
    def test_override_do_bind_usa_valor_executado(self, conn, nomeado):
        valor = bindparam("npj", 1) if nomeado else 1
        stmt = select(unidades).where(unidades.c.tenant_id == valor)
        chave = "npj" if nomeado else "tenant_id_1"
        with contexto_tenant(1):
            _recusa(conn, stmt, {chave: 2}, mensagem="tenant ativo é 1")
            conn.execute(stmt, {chave: 1})

    def test_sem_parametros_externos_nao_compila(self, conn, monkeypatch):
        # Compilar custa ~100 µs por statement; só vale quando execute() traz
        # valores que podem substituir os do statement.
        compilacoes = []
        original = Select.compile

        def contar(self, *args, **kwargs):
            compilacoes.append(self)
            return original(self, *args, **kwargs)

        monkeypatch.setattr(Select, "compile", contar)
        stmt = select(unidades).where(unidades.c.tenant_id == 1)
        with contexto_tenant(1):
            guarda_tenant.conferir(stmt, [], {})
            assert compilacoes == []
            guarda_tenant.conferir(stmt, [], {"tenant_id_1": 1})
            assert compilacoes == [stmt]
            with pytest.raises(guarda_tenant.TenantLeakError):
                guarda_tenant.conferir(stmt, [], {"tenant_id_1": 2})

    def test_statement_desconhecido_e_recusado(self, conn):
        with contexto_tenant(1):
            _recusa(conn, text("SELECT 1").columns(id=Integer), mensagem="não suportado")
            _recusa(conn, select(text("id")).select_from(text("unidades")), mensagem="não é suportado")

    def test_sem_criterio_e_recusado(self, conn):
        with contexto_tenant(1):
            _recusa(conn, select(atendidos.c.id), mensagem="sem critério de tenant")

    def test_criterio_do_tenant_ativo_passa(self, conn):
        with contexto_tenant(1):
            conn.execute(select(atendidos.c.id).where(atendidos.c.tenant_id == 1))

    def test_criterio_de_outro_tenant_e_recusado(self, conn):
        with contexto_tenant(1):
            _recusa(
                conn,
                select(atendidos.c.id).where(atendidos.c.tenant_id == 2),
                mensagem="tenant ativo é 1",
            )

    def test_comparar_tenant_com_outra_coluna_nao_conta(self, conn):
        stmt = select(casos.c.id).join(
            usuarios, and_(casos.c.id_orientador == usuarios.c.id,
                           casos.c.tenant_id == usuarios.c.tenant_id)
        ).where(casos.c.tenant_id == 1)
        with contexto_tenant(1):
            _recusa(conn, stmt, mensagem="usuarios")

    def test_join_com_lado_direito_sem_criterio_e_recusado(self, conn):
        stmt = (
            select(casos.c.id)
            .join(usuarios, casos.c.id_orientador == usuarios.c.id)
            .where(casos.c.tenant_id == 1)
        )
        with contexto_tenant(1):
            _recusa(conn, stmt, mensagem="usuarios")

    def test_outer_join_com_criterio_no_on_passa(self, conn):
        stmt = (
            select(casos.c.id)
            .outerjoin(
                usuarios,
                and_(casos.c.id_orientador == usuarios.c.id, usuarios.c.tenant_id == 1),
            )
            .where(casos.c.tenant_id == 1)
        )
        with contexto_tenant(1):
            conn.execute(stmt)

    def test_alias_exige_criterio_proprio(self, conn):
        orientador = usuarios.alias("orientador")
        sem_alias = (
            select(casos.c.id, orientador.c.nome)
            .join(orientador, casos.c.id_orientador == orientador.c.id)
            .where(casos.c.tenant_id == 1, usuarios.c.tenant_id == 1)
        )
        com_alias = (
            select(casos.c.id, orientador.c.nome)
            .join(orientador, casos.c.id_orientador == orientador.c.id)
            .where(casos.c.tenant_id == 1, orientador.c.tenant_id == 1)
        )
        with contexto_tenant(1):
            # O critério na tabela base não cobre o alias.
            _recusa(conn, sem_alias, mensagem="orientador")
            conn.execute(com_alias)

    def test_subquery_sem_criterio_e_recusada(self, conn):
        sub = select(casos.c.id_orientador).scalar_subquery()
        stmt = select(usuarios.c.id).where(usuarios.c.tenant_id == 1, usuarios.c.id.in_(sub))
        with contexto_tenant(1):
            _recusa(conn, stmt, mensagem="casos")

    def test_exists_sem_criterio_e_recusado(self, conn):
        stmt = select(usuarios.c.id).where(
            usuarios.c.tenant_id == 1,
            exists().where(casos.c.id_orientador == usuarios.c.id),
        )
        with contexto_tenant(1):
            _recusa(conn, stmt, mensagem="casos")

    def test_repositorio_com_escopo_passa(self, conn):
        repo = BaseRepository()
        with contexto_tenant(2):
            conn.execute(repo.escopo(select(atendidos.c.id), atendidos))


class TestUpdateDelete:
    @pytest.mark.parametrize("lote", [False, True])
    def test_update_parametrizado_nao_transfere_tenant(self, conn, lote):
        stmt = update(unidades).where(unidades.c.tenant_id == 1)
        params = [{"tenant_id": 1}, {"tenant_id": 2}] if lote else {"tenant_id": 2}
        with contexto_tenant(1):
            _recusa(conn, stmt, params, mensagem="muda tenant_id")

    def test_update_bind_e_ordered_values(self, conn):
        stmt = update(unidades).where(unidades.c.tenant_id == 1).ordered_values(
            (unidades.c.tenant_id, bindparam("destino", 1))
        )
        with contexto_tenant(1):
            _recusa(conn, stmt, {"destino": 2}, mensagem="muda tenant_id")
            conn.execute(stmt, {"destino": 1})

    def test_delete_override_do_filtro_em_lote(self, conn):
        stmt = delete(unidades).where(unidades.c.tenant_id == bindparam("npj", 1))
        with contexto_tenant(1):
            _recusa(conn, stmt, [{"npj": 1}, {"npj": 2}], mensagem="tenant ativo é 1")

    def test_update_sem_criterio_e_recusado(self, conn):
        with contexto_tenant(1):
            _recusa(conn, update(atendidos).values(nome="x"), mensagem="Update")
            conn.execute(update(atendidos).where(atendidos.c.tenant_id == 1).values(nome="x"))

    def test_delete_sem_criterio_e_recusado(self, conn):
        with contexto_tenant(1):
            _recusa(conn, delete(atendidos).where(atendidos.c.id == 5), mensagem="Delete")
            conn.execute(delete(atendidos).where(atendidos.c.tenant_id == 1))

    def test_update_nao_muda_o_tenant(self, conn):
        stmt = update(atendidos).where(atendidos.c.tenant_id == 1).values(tenant_id=2)
        with contexto_tenant(1):
            _recusa(conn, stmt, mensagem="muda tenant_id")


class TestInsert:
    def test_insert_bind_resolvido_em_todas_as_linhas(self, conn):
        stmt = insert(unidades).values(**self._unidade(tenant_id=bindparam("npj", 1)))
        with contexto_tenant(1):
            _recusa(conn, stmt, [{"npj": 1}, {"npj": 2}], mensagem="tenant ativo é 1")
            conn.execute(stmt, {"npj": 1})

    def test_insert_lote_com_override_externo_e_recusado(self, conn):
        stmt = insert(unidades).values([self._unidade(tenant_id=1)])
        with contexto_tenant(1):
            _recusa(conn, stmt, {"tenant_id_m0": 2}, mensagem="não é suportado")

    def _unidade(self, **extra):
        return {"nome": "Sede", "sigla": "SD", "ativa": True, "criado": AGORA, **extra}

    def test_sem_tenant_id_e_recusado(self, conn):
        with contexto_tenant(1):
            _recusa(conn, insert(unidades).values(**self._unidade()), mensagem="sem tenant_id")

    def test_com_tenant_ativo_passa(self, conn):
        with contexto_tenant(1):
            conn.execute(insert(unidades).values(**self._unidade(tenant_id=1)))

    def test_tenant_divergente_e_recusado(self, conn):
        with contexto_tenant(1):
            _recusa(
                conn,
                insert(unidades).values(**self._unidade(tenant_id=2)),
                mensagem="tenant ativo é 1",
            )

    def test_lote_e_conferido_linha_a_linha(self, conn):
        linhas = [self._unidade(tenant_id=1), self._unidade(nome="B", sigla="B", tenant_id=2)]
        with contexto_tenant(1):
            _recusa(conn, insert(unidades).values(linhas), mensagem="tenant ativo é 1")

    def test_executemany_e_conferido_linha_a_linha(self, conn):
        linhas = [self._unidade(tenant_id=1), self._unidade(nome="B", sigla="B")]
        with contexto_tenant(1):
            _recusa(conn, insert(unidades), linhas, mensagem="sem tenant_id")

    def test_tabela_global_nao_exige_tenant(self, conn):
        with contexto_tenant(1):
            conn.execute(select(tenants.c.id).where(tenants.c.id == 1))


class TestContexto:
    def test_sem_contexto_e_recusado_mesmo_em_tabela_global(self, conn):
        _recusa(conn, select(tenants.c.id), mensagem="sem tenant ativo")
        _recusa(conn, select(notificacao.c.id), mensagem="sem tenant ativo")

    def test_sem_tenant_libera_a_consulta_global(self, conn):
        with sem_tenant("teste: consulta global"):
            conn.execute(select(usuarios.c.id))
            conn.execute(update(atendidos).values(nome="x"))

    def test_sql_textual_e_recusado(self, conn):
        with contexto_tenant(1):
            _recusa(conn, text("SELECT id FROM atendidos WHERE tenant_id = 1"),
                    mensagem="text")
        with sem_tenant("teste: nem a plataforma usa text()"):
            _recusa(conn, text("SELECT 1"), mensagem="text")

    def test_texto_permitido_quando_pedido(self):
        engine = create_engine("sqlite://")
        instalar_guarda(engine, permitir_texto=True)
        with engine.connect() as conexao:
            assert conexao.execute(text("SELECT 1")).scalar() == 1

    def test_instalar_duas_vezes_nao_duplica(self, conn):
        engine = conn.engine
        instalar_guarda(engine)
        with contexto_tenant(1):
            conn.execute(select(atendidos.c.id).where(atendidos.c.tenant_id == 1))

    def test_engine_do_app_tem_a_guarda(self):
        import gestaolegal.database.session as session_module
        from tests.api.conftest import test_engine

        assert getattr(test_engine, "_guarda_tenant", None) is not None
        assert session_module.engine is test_engine


# Lint (§10): o acesso ao banco mora nos repositórios. Fora deles, SQL textual
# ou `execute` direto só nos pontos listados, para que cada exceção seja vista.
EXCECOES_EXECUTE = {
    # Três consultas de apoio da escala, já com `repository.escopo`.
    "gestaolegal/services/plantao_service.py",
}


def _codigo_sem_textos(arquivo: Path) -> str:
    """Código do arquivo sem strings nem comentários (uma docstring que cite
    `text()` não é uso)."""
    with arquivo.open("rb") as f:
        tokens = [
            t.string
            for t in tokenize.tokenize(f.readline)
            if t.type in (tokenize.NAME, tokenize.OP)
        ]
    codigo = ""
    for anterior, atual in zip([""] + tokens, tokens):
        separa = anterior.isidentifier() and atual.isidentifier()
        codigo += f" {atual}" if separa else atual
    return codigo


def test_sql_fora_dos_repositorios_so_nas_excecoes():
    ocorrencias = {}
    for arquivo in sorted((RAIZ / "gestaolegal").rglob("*.py")):
        relativo = arquivo.relative_to(RAIZ).as_posix()
        if relativo.startswith("gestaolegal/repositories/"):
            continue
        if re.search(r"\btext\(|\.execute\(", _codigo_sem_textos(arquivo)):
            ocorrencias[relativo] = True
    assert set(ocorrencias) == EXCECOES_EXECUTE


def test_repositorios_nao_usam_sql_textual():
    usos = [
        arquivo.name
        for arquivo in (RAIZ / "gestaolegal/repositories").glob("*.py")
        if re.search(r"\btext\(", _codigo_sem_textos(arquivo))
    ]
    assert usos == []
