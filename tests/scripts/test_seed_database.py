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
    assert criados["usuarios"] == 6
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
            "prof@ufmg.br": "prof",
            "colab_proj@ufmg.br": "colab_proj",
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
        assert len(cpfs) == len(set(cpfs)) == 46
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
    assert criados["usuarios"] == 12
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
            "prof@ufmg.br": "prof", "colab_proj@ufmg.br": "colab_proj",
        }
        assert por_tenant[demo["id"]] == {
            "admin@npjdemo.br": "admin", "orient@npjdemo.br": "orient",
            "estag_direito@npjdemo.br": "estag_direito", "colab_ext@npjdemo.br": "colab_ext",
            "prof@npjdemo.br": "prof", "colab_proj@npjdemo.br": "colab_proj",
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
    assert criados["usuarios"] == 6 and criados["casos"] == 2
    with engine.connect() as conn:
        for tabela in metadata.sorted_tables:
            if "tenant_id" in tabela.c and tabela.name != "unidades":
                assert not conn.execute(select(tabela).where(tabela.c.tenant_id == 1)).first(), tabela.name


def test_cpfs_unicos_entre_os_dois_npjs(engine):
    seed_database(engine, senha="123456", tenants=DEMOS)
    with engine.connect() as conn:
        cpfs = [cpf for nome in ("usuarios", "atendidos")
                for cpf in conn.execute(select(metadata.tables[nome].c.cpf)).scalars()]
    assert len(cpfs) == len(set(cpfs)) == 12 + 60


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


def _digito_cnj(digitos):
    """Dígito verificador CNJ (Resolução 65/2008, anexo VIII), módulo 97."""
    base = digitos[:7] + digitos[9:] + "00"
    return 98 - int(base) % 97


def test_processos_com_cnj_ficticio_sem_pendencia_djen(engine):
    seed_database(engine, senha="123456", hoje=date(2026, 10, 13), tenants=DEMOS)
    with engine.connect() as conn:
        processos = metadata.tables["processos"]
        rows = conn.execute(select(processos)).mappings().all()
    assert len(rows) == 6
    numeros = set()
    for p in rows:
        digitos = "".join(c for c in p["numero"] if c.isdigit())
        assert p["numero_cnj"] == digitos and len(digitos) == 20
        # Segmento 0 não existe: o número nunca é de um processo real.
        assert digitos[13] == "0"
        assert int(digitos[7:9]) == _digito_cnj(digitos)
        assert p["djen_pendente"] is False or p["djen_pendente"] == 0
        numeros.add((p["tenant_id"], p["numero"]))
    assert len(numeros) == 6


def test_atendido_do_caso_e_parte_ativa_do_processo(engine):
    seed_database(engine, senha="123456", tenants=DEMOS)
    with engine.connect() as conn:
        partes = metadata.tables["processo_partes"]
        processos = metadata.tables["processos"]
        links = metadata.tables["casos_atendidos"]
        rows = conn.execute(
            select(partes.c.polo, partes.c.tenant_id, processos.c.tenant_id.label("tp"),
                   links.c.id_atendido.label("do_caso"), partes.c.id_atendido)
            .select_from(partes.join(processos, processos.c.id == partes.c.id_processo)
                         .join(links, links.c.id_caso == processos.c.id_caso))
        ).mappings().all()
    assert len(rows) == 6
    for r in rows:
        assert r["polo"] == "ativo"
        assert r["tenant_id"] == r["tp"]
        assert r["id_atendido"] == r["do_caso"]


def test_oab_do_orientador_pausada_em_cada_npj(engine):
    seed_database(engine, senha="123456", tenants=DEMOS)
    with engine.connect() as conn:
        oabs = metadata.tables["djen_oabs"]
        usuarios = metadata.tables["usuarios"]
        rows = conn.execute(
            select(oabs, usuarios.c.urole, usuarios.c.tenant_id.label("tu"))
            .join(usuarios, usuarios.c.id == oabs.c.id_usuario)
        ).mappings().all()
    assert {(r["numero_oab"], r["uf_oab"]) for r in rows} == {("990001", "MG"), ("990002", "MG")}
    for r in rows:
        # Pausada: a rotina do DJEN não consulta uma OAB que pode ser de alguém.
        assert not r["ativo"]
        assert r["urole"] == "orient" and r["tenant_id"] == r["tu"]


def test_admin_da_plataforma_criado_uma_vez(engine):
    criados = seed_database(engine, senha="123456", tenants=("npj-demo",))
    assert criados["plataforma_admins"] == 1
    seed_database(engine, senha="OutraSenha123!", tenants=DEMOS)
    with engine.connect() as conn:
        (admin,) = conn.execute(select(metadata.tables["plataforma_admins"])).mappings()
    assert admin["email"] == "plataforma@npjdemo.br" and admin["ativo"]
    assert bcrypt.checkpw(b"123456", admin["senha"].encode())


def test_banco_semeado_antes_do_cnj_ganha_numero_e_contas_novas(engine):
    seed_database(engine, senha="123456")
    processos, partes = metadata.tables["processos"], metadata.tables["processo_partes"]
    usuarios = metadata.tables["usuarios"]
    with engine.begin() as conn:
        conn.execute(processos.update().values(numero=None, numero_cnj=None))
        conn.execute(partes.delete())
        novos = select(usuarios.c.id).where(usuarios.c.urole.in_(("prof", "colab_proj")))
        vinculos = metadata.tables["usuarios_unidades"]
        conn.execute(vinculos.delete().where(vinculos.c.usuario_id.in_(novos)))
        conn.execute(usuarios.delete().where(usuarios.c.urole.in_(("prof", "colab_proj"))))
    criados = seed_database(engine, senha="123456")
    assert criados["processo_partes"] == 4 and criados["usuarios"] == 2
    with engine.connect() as conn:
        assert all(p["numero_cnj"] for p in conn.execute(select(processos)).mappings())


def test_cnj_demonstracao_recusa_fora_do_formato():
    from scripts.seed_database import cnj_demonstracao

    assert cnj_demonstracao(7001, 2026, 7) == "0007001-%02d.2026.0.13.0007" % _digito_cnj(
        "0007001" + "00" + "2026" + "0" + "13" + "0007")
    for args in ((0, 2026, 1), (10_000_000, 2026, 1), (1, 2026, 10_000)):
        with pytest.raises(ValueError):
            cnj_demonstracao(*args)


# Senhas por NPJ e do admin da plataforma (valores fictícios).

def _senhas_por_dominio(engine):
    with engine.connect() as conn:
        usuarios = conn.execute(select(metadata.tables["usuarios"])).mappings().all()
        (admin,) = conn.execute(select(metadata.tables["plataforma_admins"])).mappings()
    return usuarios, admin


def test_senha_por_npj_e_da_plataforma(engine):
    seed_database(engine, senha="BaseFicticia", tenants=DEMOS,
                  senhas={"daj-ufmg": "Ficticia@1", "npj-demo": "Ficticia@2"},
                  senha_plataforma="Ficticia@3")
    usuarios, admin = _senhas_por_dominio(engine)
    esperadas = {"ufmg.br": b"Ficticia@1", "npjdemo.br": b"Ficticia@2"}
    assert {u["email"].split("@")[1] for u in usuarios} == set(esperadas)
    for u in usuarios:
        senha = esperadas[u["email"].split("@")[1]]
        assert bcrypt.checkpw(senha, u["senha"].encode()), u["email"]
        assert not bcrypt.checkpw(b"BaseFicticia", u["senha"].encode())
    assert bcrypt.checkpw(b"Ficticia@3", admin["senha"].encode())
    assert not bcrypt.checkpw(b"BaseFicticia", admin["senha"].encode())


def test_npj_sem_senha_propria_e_plataforma_caem_em_senha(engine):
    seed_database(engine, senha="BaseFicticia", tenants=DEMOS, senhas={"npj-demo": "Ficticia@2"})
    usuarios, admin = _senhas_por_dominio(engine)
    for u in usuarios:
        senha = b"Ficticia@2" if u["email"].endswith("@npjdemo.br") else b"BaseFicticia"
        assert bcrypt.checkpw(senha, u["senha"].encode()), u["email"]
    assert bcrypt.checkpw(b"BaseFicticia", admin["senha"].encode())


def test_reexecucao_com_senhas_novas_nao_troca_senhas(engine):
    seed_database(engine, senha="BaseFicticia", tenants=DEMOS)
    assert not seed_database(engine, senha="BaseFicticia", tenants=DEMOS,
                             senhas={"daj-ufmg": "Ficticia@1", "npj-demo": "Ficticia@2"},
                             senha_plataforma="Ficticia@3")
    usuarios, admin = _senhas_por_dominio(engine)
    for registro in (*usuarios, admin):
        assert bcrypt.checkpw(b"BaseFicticia", registro["senha"].encode())


@pytest.mark.parametrize("kwargs,variavel", [
    ({"senhas": {"daj-ufmg": "12345"}}, "SEED_PASSWORD_DAJ_UFMG"),
    ({"senhas": {"npj-demo": "x" * 73}}, "SEED_PASSWORD_NPJ_DEMO"),
    ({"senhas": {"npj-demo": "ç" * 37}}, "SEED_PASSWORD_NPJ_DEMO"),  # 74 bytes
    ({"senha_plataforma": "12345"}, "SEED_PLATAFORMA_PASSWORD"),
    ({"senha_plataforma": ""}, "SEED_PLATAFORMA_PASSWORD"),
])
def test_senhas_fora_do_tamanho_nao_gravam(engine, kwargs, variavel):
    antes = snapshot(engine)
    with pytest.raises(ValueError, match=variavel):
        seed_database(engine, senha="BaseFicticia", tenants=DEMOS, **kwargs)
    assert snapshot(engine) == antes


def test_senha_para_npj_fora_da_demonstracao(engine):
    with pytest.raises(ValueError, match="npj-real"):
        seed_database(engine, senha="BaseFicticia", senhas={"npj-real": "Ficticia@1"})


def test_variavel_de_senha_derivada_do_slug():
    from scripts.seed_database import variavel_senha_npj
    assert variavel_senha_npj("daj-ufmg") == "SEED_PASSWORD_DAJ_UFMG"
    assert variavel_senha_npj("npj-demo") == "SEED_PASSWORD_NPJ_DEMO"


def test_senhas_do_ambiente_com_fallback():
    from scripts.seed_database import senhas_do_ambiente
    assert senhas_do_ambiente("BaseFicticia", {}) == (
        {"daj-ufmg": "BaseFicticia", "npj-demo": "BaseFicticia"}, "BaseFicticia")
    assert senhas_do_ambiente("BaseFicticia", {
        "SEED_PASSWORD_DAJ_UFMG": "Ficticia@1", "SEED_PASSWORD_NPJ_DEMO": "",
        "SEED_PLATAFORMA_PASSWORD": "Ficticia@3",
    }) == ({"daj-ufmg": "Ficticia@1", "npj-demo": "BaseFicticia"}, "Ficticia@3")


@pytest.fixture
def cli(monkeypatch):
    import scripts.seed_database as modulo
    from collections import Counter
    from unittest.mock import MagicMock

    for chave, valor in {"FLASK_ENV": "development", "DB_USER": "u", "DB_PASSWORD": "p",
                         "DB_HOST": "h", "DB_NAME": "n"}.items():
        monkeypatch.setenv(chave, valor)
    for chave in ("SEED_PASSWORD", "SEED_PASSWORD_DAJ_UFMG", "SEED_PASSWORD_NPJ_DEMO",
                  "SEED_PLATAFORMA_PASSWORD"):
        monkeypatch.delenv(chave, raising=False)
    monkeypatch.setattr(modulo, "load_dotenv", lambda *_: None)
    monkeypatch.setattr(modulo, "create_engine", MagicMock())
    chamada = MagicMock(return_value=Counter())
    monkeypatch.setattr(modulo, "seed_database", chamada)
    return chamada


def test_cli_sem_variaveis_novas_usa_seed_password(cli, monkeypatch):
    monkeypatch.setenv("SEED_PASSWORD", "BaseFicticia")
    assert main([]) == 0
    kwargs = cli.call_args.kwargs
    assert kwargs["senha"] == "BaseFicticia"
    assert kwargs["senhas"] == {"daj-ufmg": "BaseFicticia", "npj-demo": "BaseFicticia"}
    assert kwargs["senha_plataforma"] == "BaseFicticia"


def test_cli_sem_nenhuma_variavel_usa_padrao(cli):
    assert main([]) == 0
    kwargs = cli.call_args.kwargs
    assert kwargs["senha"] == "123456"
    assert set(kwargs["senhas"].values()) == {"123456"}
    assert kwargs["senha_plataforma"] == "123456"


def test_cli_le_senha_por_npj_e_da_plataforma(cli, monkeypatch):
    monkeypatch.setenv("SEED_PASSWORD_DAJ_UFMG", "Ficticia@1")
    monkeypatch.setenv("SEED_PASSWORD_NPJ_DEMO", "Ficticia@2")
    monkeypatch.setenv("SEED_PLATAFORMA_PASSWORD", "Ficticia@3")
    assert main([]) == 0
    kwargs = cli.call_args.kwargs
    assert kwargs["senhas"] == {"daj-ufmg": "Ficticia@1", "npj-demo": "Ficticia@2"}
    assert kwargs["senha_plataforma"] == "Ficticia@3"


@pytest.mark.parametrize("variavel", ["SEED_PASSWORD", "SEED_PASSWORD_DAJ_UFMG",
                                      "SEED_PASSWORD_NPJ_DEMO", "SEED_PLATAFORMA_PASSWORD"])
def test_cli_recusa_senha_curta(cli, monkeypatch, capsys, variavel):
    monkeypatch.setenv(variavel, "12345")
    assert main([]) == 1
    cli.assert_not_called()
    assert variavel in capsys.readouterr().err
