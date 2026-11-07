from datetime import date, datetime

import bcrypt
import pytest
from sqlalchemy import create_engine, event, select

from scripts.seed_database import main, metadata, seed_database


@pytest.fixture
def engine():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def foreign_keys(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(metadata.tables["tenants"].insert(), [
            {"id": 1, "nome": "DAJ", "sigla": "DAJ", "slug": "daj-ufmg", "ativo": True, "criado_em": datetime.now()},
        ])
        conn.execute(metadata.tables["unidades"].insert(), [
            {"id": 7, "nome": "Belo Horizonte", "sigla": "BH", "ativa": True, "criado": datetime.now(), "tenant_id": 1},
            {"id": 12, "nome": "Nova Lima", "sigla": "NL", "ativa": True, "criado": datetime.now(), "tenant_id": 1},
            {"id": 15, "nome": "Inativa", "sigla": "OFF", "ativa": False, "criado": datetime.now(), "tenant_id": 1},
        ])
    yield engine
    engine.dispose()


def snapshot(engine):
    with engine.connect() as conn:
        return {t.name: conn.execute(select(t)).all() for t in metadata.sorted_tables}


def test_seed_relacoes_senha_e_idempotencia(engine):
    criados = seed_database(engine, senha="123456", hoje=date(2026, 10, 13))
    assert criados["usuarios"] == 4
    assert criados["atendidos"] == 40
    assert criados["assistidos"] == 20
    assert criados["casos"] == 4
    assert criados["eventos"] == 8
    with engine.connect() as conn:
        usuarios = metadata.tables["usuarios"]
        contas = conn.execute(select(usuarios)).mappings().all()
        assert {u["email"]: u["urole"] for u in contas} == {
            "admin@ufmg.br": "admin",
            "orient@ufmg.br": "orient",
            "estag_direito@ufmg.br": "estag_direito",
            "colab_ext@ufmg.br": "colab_ext",
        }
        for usuario in contas:
            assert bcrypt.checkpw(b"123456", usuario["senha"].encode())
        casos = metadata.tables["casos"]
        vinculos = metadata.tables["usuarios_unidades"]
        for caso in conn.execute(select(casos)).mappings():
            assert caso["unidade_id"] in (7, 12)
            assert conn.execute(select(vinculos).filter_by(
                usuario_id=caso["id_usuario_responsavel"], unidade_id=caso["unidade_id"]
            )).first()
        clientes = metadata.tables["atendidos"]
        links = metadata.tables["casos_atendidos"]
        pares = conn.execute(select(casos.c.unidade_id, clientes.c.unidade_id).select_from(
            links.join(casos, casos.c.id == links.c.id_caso).join(clientes, clientes.c.id == links.c.id_atendido)
        )).all()
        assert len(pares) == 4
        assert all(a == b for a, b in pares)
    antes = snapshot(engine)
    assert not seed_database(engine, senha="OutraSenha123!", hoje=date(2027, 1, 1))
    assert snapshot(engine) == antes


def test_dry_run_e_filtro_unidade(engine):
    antes = snapshot(engine)
    assert seed_database(engine, senha="123456", dry_run=True)["casos"] == 4
    assert snapshot(engine) == antes
    assert seed_database(engine, senha="123456", sigla="NL")["casos"] == 2
    with engine.connect() as conn:
        assert set(conn.execute(select(metadata.tables["casos"].c.unidade_id)).scalars()) == {12}


def test_falha_desfaz_insercoes_parciais(engine):
    antes = snapshot(engine)

    @event.listens_for(engine, "before_cursor_execute")
    def falhar(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO eventos"):
            raise RuntimeError("Falha simulada após criar usuários, atendidos e casos")

    with pytest.raises(RuntimeError, match="Falha simulada"):
        seed_database(engine, senha="123456")
    assert snapshot(engine) == antes


def test_unidade_inexistente_nao_insere(engine):
    antes = snapshot(engine)
    with pytest.raises(ValueError, match="Nenhuma unidade"):
        seed_database(engine, senha="123456", sigla="OFF")
    assert snapshot(engine) == antes


def test_reexecucao_preserva_edicoes(engine):
    seed_database(engine, senha="123456")
    casos = metadata.tables["casos"]
    with engine.begin() as conn:
        conn.execute(casos.update().values(situacao_deferimento="arquivado", status=False))
    antes = snapshot(engine)
    seed_database(engine, senha="123456")
    assert snapshot(engine) == antes


def test_cli_bloqueia_producao(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


def test_cpfs_validos_unicos_e_metade_assistidos_por_unidade(engine):
    seed_database(engine, senha="123456")
    cpfs = []
    with engine.connect() as conn:
        for table_name in ("usuarios", "atendidos"):
            for cpf in conn.execute(select(metadata.tables[table_name].c.cpf)).scalars():
                digits = [int(c) for c in cpf if c.isdigit()]
                assert len(digits) == 11 and len(set(digits)) > 1
                for length in (9, 10):
                    check = (sum(digits[i] * (length + 1 - i) for i in range(length)) * 10 % 11) % 10
                    assert digits[length] == check
                cpfs.append(cpf)
        assert len(cpfs) == len(set(cpfs)) == 44
        atendidos, assistidos = metadata.tables["atendidos"], metadata.tables["assistidos"]
        for unidade in (7, 12):
            people = set(conn.execute(select(atendidos.c.id).where(atendidos.c.unidade_id == unidade)).scalars())
            assisted = set(conn.execute(select(assistidos.c.id_atendido).where(assistidos.c.id_atendido.in_(people))).scalars())
            assert len(people) == 20
            assert len(assisted) == 10


def test_atualiza_rotulos_antigos_sem_duplicar_ou_alterar_vinculos(engine):
    from scripts.seed_database import MARCA, MARCA_ANTIGA

    seed_database(engine, senha="123456")
    esperado = snapshot(engine)
    with engine.begin() as conn:
        for table_name in ("usuarios", "atendidos"):
            tabela = metadata.tables[table_name]
            for row in conn.execute(select(tabela)).mappings().all():
                values = {"nome": row["nome"] + " Seed", "cpf": "000.000.000-00", "obs": MARCA_ANTIGA}
                if table_name == "usuarios":
                    values["rg"] = "SEED"
                else:
                    values["email"] = row["email"].replace("@example.test", "@seed.example.test")
                conn.execute(tabela.update().where(tabela.c.id == row["id"]).values(**values))
        for table_name, column in (("casos", "descricao"), ("processos", "identificacao"),
                                   ("eventos", "descricao"), ("lembretes", "descricao"),
                                   ("orientacao_juridica", "descricao"), ("plantao", "nome")):
            tabela = metadata.tables[table_name]
            for row in conn.execute(select(tabela)).mappings().all():
                conn.execute(tabela.update().where(tabela.c.id == row["id"]).values(
                    **{column: row[column].replace(MARCA, MARCA_ANTIGA)}))
    assert not seed_database(engine, senha="OutraSenha123!")
    assert snapshot(engine) == esperado
    for rows in esperado.values():
        for row in rows:
            assert all("seed" not in value.lower() for key, value in row._mapping.items()
                       if isinstance(value, str) and key != "senha")


DEMOS = ("daj-ufmg", "npj-demo")


def _tenant(conn, slug):
    tenants = metadata.tables["tenants"]
    return conn.execute(select(tenants).where(tenants.c.slug == slug)).mappings().one_or_none()


def test_npj_demo_criado_com_tenant_unidade_e_contas_proprias(engine):
    criados = seed_database(engine, senha="123456", hoje=date(2026, 10, 13), tenants=DEMOS)
    assert criados["tenants"] == 1
    assert criados["unidades"] == 1
    assert criados["usuarios"] == 8
    with engine.connect() as conn:
        demo = _tenant(conn, "npj-demo")
        assert demo is not None and demo["ativo"] and demo["id"] != 1
        usuarios = metadata.tables["usuarios"]
        por_tenant = {}
        for u in conn.execute(select(usuarios)).mappings():
            por_tenant.setdefault(u["tenant_id"], {})[u["email"]] = u["urole"]
            assert bcrypt.checkpw(b"123456", u["senha"].encode())
        # As contas da DAJ continuam exatamente as documentadas.
        assert por_tenant[1] == {
            "admin@ufmg.br": "admin", "orient@ufmg.br": "orient",
            "estag_direito@ufmg.br": "estag_direito", "colab_ext@ufmg.br": "colab_ext",
        }
        assert por_tenant[demo["id"]] == {
            "admin@npjdemo.br": "admin", "orient@npjdemo.br": "orient",
            "estag_direito@npjdemo.br": "estag_direito", "colab_ext@npjdemo.br": "colab_ext",
        }
        unidades = metadata.tables["unidades"]
        (sede,) = conn.execute(select(unidades).where(unidades.c.tenant_id == demo["id"])).mappings()
        assert (sede["nome"], sede["sigla"], sede["ativa"]) == ("Sede", "SEDE", True)


def test_npj_demo_nao_aponta_para_registros_da_daj(engine):
    seed_database(engine, senha="123456", tenants=DEMOS)
    with engine.connect() as conn:
        demo_id = _tenant(conn, "npj-demo")["id"]
        ids = {}
        for nome in ("usuarios", "unidades", "atendidos", "casos"):
            tabela = metadata.tables[nome]
            ids[nome] = {r.id: r.tenant_id for r in conn.execute(select(tabela.c.id, tabela.c.tenant_id))}
        casos = metadata.tables["casos"]
        for caso in conn.execute(select(casos).where(casos.c.tenant_id == demo_id)).mappings():
            assert ids["unidades"][caso["unidade_id"]] == demo_id
            for coluna in ("id_usuario_responsavel", "id_orientador", "id_estagiario",
                           "id_colaborador", "id_criado_por"):
                assert ids["usuarios"][caso[coluna]] == demo_id, coluna
        links = metadata.tables["casos_atendidos"]
        for link in conn.execute(select(links)).mappings():
            assert ids["casos"][link["id_caso"]] == ids["atendidos"][link["id_atendido"]] == link["tenant_id"]
        vinculos = metadata.tables["usuarios_unidades"]
        for v in conn.execute(select(vinculos)).mappings():
            assert ids["usuarios"][v["usuario_id"]] == ids["unidades"][v["unidade_id"]] == v["tenant_id"]
        # Nomes distintos: um vazamento entre os NPJs aparece na tela.
        atendidos = metadata.tables["atendidos"]
        nomes = {}
        for a in conn.execute(select(atendidos.c.nome, atendidos.c.tenant_id)):
            nomes.setdefault(a.tenant_id, set()).add(a.nome)
        assert len(nomes[demo_id]) == 20 and not nomes[demo_id] & nomes[1]


def test_dois_npjs_reexecucao_nao_duplica_nem_troca_senha(engine):
    seed_database(engine, senha="123456", tenants=DEMOS)
    antes = snapshot(engine)
    assert not seed_database(engine, senha="OutraSenha123!", tenants=DEMOS)
    assert snapshot(engine) == antes


def test_npj_demo_sozinho_nao_toca_a_daj(engine):
    criados = seed_database(engine, senha="123456", tenants=("npj-demo",))
    assert criados["usuarios"] == 4 and criados["casos"] == 2
    with engine.connect() as conn:
        for tabela in metadata.sorted_tables:
            if "tenant_id" in tabela.c and tabela.name != "unidades":
                assert not conn.execute(select(tabela).where(tabela.c.tenant_id == 1)).first(), tabela.name


def test_cpfs_unicos_entre_os_dois_npjs(engine):
    seed_database(engine, senha="123456", tenants=DEMOS)
    with engine.connect() as conn:
        cpfs = [cpf for nome in ("usuarios", "atendidos")
                for cpf in conn.execute(select(metadata.tables[nome].c.cpf)).scalars()]
    assert len(cpfs) == len(set(cpfs)) == 8 + 60


def test_email_do_npj_demo_em_uso_na_daj_aborta_sem_gravar(engine):
    seed_database(engine, senha="123456")
    usuarios = metadata.tables["usuarios"]
    with engine.begin() as conn:
        conn.execute(usuarios.update().where(usuarios.c.email == "orient@ufmg.br")
                     .values(email="orient@npjdemo.br"))
    antes = snapshot(engine)
    with pytest.raises(ValueError, match="outro NPJ: orient@npjdemo.br"):
        seed_database(engine, senha="123456", tenants=("npj-demo",))
    assert snapshot(engine) == antes


@pytest.mark.parametrize("tenants", [(), "npj-demo", ("npj-real",), ("daj-ufmg", "npj-real")])
def test_recusa_tenant_fora_da_demonstracao(engine, tenants):
    antes = snapshot(engine)
    with pytest.raises(ValueError):
        seed_database(engine, senha="123456", tenants=tenants)
    assert snapshot(engine) == antes


def test_daj_ausente_nao_e_criada_pelo_seed():
    engine = create_engine("sqlite://")
    metadata.create_all(engine)
    with pytest.raises(ValueError, match="daj-ufmg.*migrations"):
        seed_database(engine, senha="123456")
    with engine.connect() as conn:
        assert not conn.execute(select(metadata.tables["tenants"])).first()


@pytest.mark.parametrize("argv,esperado", [
    ([], DEMOS),
    (["--unidade", "BH"], ("daj-ufmg",)),
    (["--tenant", "npj-demo"], ("npj-demo",)),
    (["--tenant", "daj-ufmg", "--tenant", "npj-demo", "--unidade", "BH"], DEMOS),
])
def test_cli_escolhe_os_tenants(monkeypatch, argv, esperado):
    import scripts.seed_database as modulo
    from collections import Counter
    from unittest.mock import MagicMock

    for chave, valor in {"FLASK_ENV": "development", "DB_USER": "u", "DB_PASSWORD": "p",
                         "DB_HOST": "h", "DB_NAME": "n"}.items():
        monkeypatch.setenv(chave, valor)
    monkeypatch.setattr(modulo, "load_dotenv", lambda *_: None)
    monkeypatch.setattr(modulo, "create_engine", MagicMock())
    chamada = MagicMock(return_value=Counter())
    monkeypatch.setattr(modulo, "seed_database", chamada)
    assert main(argv) == 0
    assert chamada.call_args.kwargs["tenants"] == esperado


def test_cli_recusa_tenant_desconhecido():
    with pytest.raises(SystemExit) as exc:
        main(["--tenant", "npj-real"])
    assert exc.value.code == 2
