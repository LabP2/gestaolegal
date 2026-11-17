"""Ensaio G1–G5 em MySQL novo; nunca recebe URL de banco existente.

MULTITENANT_MYSQL_TEST=1 uv run pytest tests/database/test_multitenant_mysql.py -v
Cria um container com nome/porta exclusivos e dados em tmpfs; remove no finally.
"""

import os
import runpy
import secrets
import subprocess
import time
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, Table, create_engine, inspect, select, text
from sqlalchemy import bindparam as sa_bindparam
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError, OperationalError

ROOT = Path(__file__).resolve().parents[2]
DJEN = "d3e4f5a6b7c8"
AVULSOS = "f1a2b3c4d5e6"
pytestmark = pytest.mark.skipif(
    os.environ.get("MULTITENANT_MYSQL_TEST") != "1",
    reason="MySQL descartável: habilite MULTITENANT_MYSQL_TEST=1",
)


def _docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


@pytest.fixture
def mysql_descartavel():
    nome = f"gl-multitenant-test-{secrets.token_hex(6)}"
    senha = secrets.token_hex(24)
    engine = None
    # Se run falhar depois de criar o container, o finally também o remove.
    try:
        _docker("run", "-d", "--name", nome, "--label", "purpose=multitenant-test",
                "--tmpfs", "/var/lib/mysql:rw,size=2g", "-p", "127.0.0.1::3306",
                "-e", f"MYSQL_ROOT_PASSWORD={senha}", "-e", "MYSQL_DATABASE=mt_test",
                "mysql:8.0.42")
        porta = int(_docker("port", nome, "3306/tcp").rsplit(":", 1)[1])
        url = URL.create("mysql+pymysql", username="root", password=senha,
                         host="127.0.0.1", port=porta, database="mt_test")
        engine = create_engine(url, connect_args={"connect_timeout": 2})
        limite = time.monotonic() + 180
        while True:
            try:
                with engine.connect() as conn:
                    assert conn.execute(text("SELECT VERSION()")).scalar().startswith("8.0.42")
                break
            except OperationalError:
                if time.monotonic() >= limite:
                    pytest.fail("MySQL descartável não aceitou conexão TCP em 180s")
                time.sleep(1)
        cfg = Config(str(ROOT / "migrations/alembic.ini"))
        cfg.set_main_option("script_location", str(ROOT / "migrations"))
        cfg.attributes["database_url"] = url
        yield engine, cfg
    finally:
        if engine is not None:
            engine.dispose()
        subprocess.run(["docker", "rm", "-f", "-v", nome], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _schema(engine):
    insp = inspect(engine)
    return {
        tabela: {
            "colunas": [(c["name"], str(c["type"]), c["nullable"], str(c["default"]))
                        for c in insp.get_columns(tabela)],
            "fks": sorted((f["name"], f["constrained_columns"], f["referred_table"],
                           f["referred_columns"], f["options"])
                          for f in insp.get_foreign_keys(tabela)),
            "indices": sorted((i["name"], i["column_names"], bool(i["unique"]))
                              for i in insp.get_indexes(tabela)),
            "pk": insp.get_pk_constraint(tabela),
        }
        for tabela in sorted(insp.get_table_names())
    }


def test_migrations_com_dois_npjs(mysql_descartavel):
    from scripts.seed_database import seed_database

    engine, cfg = mysql_descartavel
    command.upgrade(cfg, "b1c2d3e4f5a6")
    seed_database(engine, senha="123456", tenants=("daj-ufmg", "npj-demo"))
    with engine.begin() as conn:
        unidade = conn.execute(text("SELECT id FROM unidades WHERE tenant_id=2 LIMIT 1")).scalar_one()
        escala, unidade_original = conn.execute(
            text("SELECT id, unidade_id FROM plantao WHERE tenant_id=1 LIMIT 1")
        ).one()
        conn.execute(text("UPDATE plantao SET unidade_id=:u WHERE id=:id"), {"u": unidade, "id": escala})
    # G2: preflight aborta antes de qualquer DDL.
    antes = _schema(engine)
    with pytest.raises(RuntimeError, match=r"plantao.unidade_id -> unidades: 1 registro"):
        command.upgrade(cfg, "head")
    assert _schema(engine) == antes
    with engine.begin() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "b1c2d3e4f5a6"
        conn.execute(text("UPDATE plantao SET unidade_id=:u WHERE id=:id"), {"u": unidade_original, "id": escala})
    command.upgrade(cfg, "head")
    # G1: conferir o esquema migrado, não o create_all do metadata.
    m2 = runpy.run_path(str(ROOT / "migrations/versions/b1c2d3e4f5a6_tenant_id.py"))
    m3 = runpy.run_path(str(ROOT / "migrations/versions/c2d3e4f5a6b7_fks_compostas.py"))
    insp = inspect(engine)
    assert len(m2["TABELAS"]) == 28
    for tabela in m2["TABELAS"]:
        assert next(c for c in insp.get_columns(tabela) if c["name"] == "tenant_id")["nullable"] is False
    for tabela, coluna, pai, _, _ in m3["FKS"]:
        assert any(f["constrained_columns"] == ["tenant_id", coluna]
                   and f["referred_table"] == pai and f["referred_columns"] == ["tenant_id", "id"]
                   for f in insp.get_foreign_keys(tabela))
    # G3: INSERT e UPDATE cruzados falham mesmo sem guarda de aplicação.
    plantao = Table("plantao", MetaData(), autoload_with=engine)
    with engine.connect() as conn:
        linha = dict(conn.execute(select(plantao).where(plantao.c.id == escala)).mappings().one())
    linha.pop("id")
    linha["unidade_id"] = unidade
    for stmt in (plantao.insert().values(**linha), plantao.update().where(plantao.c.id == escala).values(unidade_id=unidade)):
        with pytest.raises(IntegrityError) as erro, engine.begin() as conn:
            conn.execute(stmt)
        assert erro.value.orig.args[0] == 1452
    # G4: igualdade inclui nomes dos índices e ações das FKs.
    antes = _schema(engine)
    command.downgrade(cfg, "b1c2d3e4f5a6")
    command.upgrade(cfg, "head")
    assert _schema(engine) == antes
    fk = next(f for f in inspect(engine).get_foreign_keys("arquivosCaso")
              if f["constrained_columns"] == ["tenant_id", "id_caso"])
    assert fk["options"]["ondelete"] == "CASCADE"
    # G5: M2 não pode ser removida com dados do segundo NPJ.
    with pytest.raises(RuntimeError, match="Remova-os antes do downgrade"):
        command.downgrade(cfg, "a0b1c2d3e4f5")
    command.upgrade(cfg, "head")
    assert not seed_database(engine, senha="123456", tenants=("daj-ufmg", "npj-demo"))


def test_api_com_fks_mysql(mysql_descartavel, monkeypatch, tmp_path):
    """Fluxos reais dos services com guarda e FKs ligadas, sem SMTP."""
    from scripts.seed_database import seed_database
    from sqlalchemy.orm import sessionmaker

    engine, cfg = mysql_descartavel
    command.upgrade(cfg, "head")
    seed_database(engine, senha="123456", tenants=("daj-ufmg", "npj-demo"))
    for nome in ("DB_USER", "DB_PASSWORD", "DB_HOST", "DB_NAME", "JWT_SECRET_KEY"):
        monkeypatch.setenv(nome, "teste-descartavel")
    monkeypatch.setenv("FLASK_ENV", "testing")
    from gestaolegal import create_app
    from gestaolegal.config import Config as AppConfig
    from gestaolegal.database import session as db
    from gestaolegal.database.guarda_tenant import instalar_guarda
    from gestaolegal.services.plataforma_service import PlataformaService

    instalar_guarda(engine)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=engine))

    class TestConfig(AppConfig):
        TESTING = True
        MAIL_SUPPRESS_SEND = True
        PRIVATE_FILES_ROOT = str(tmp_path)
        JWT_SECRET_KEY = "somente-para-teste-descartavel-sem-uso-real"

    app = create_app(TestConfig)
    client = app.test_client()

    def dados(response, status=200):
        assert response.status_code == status, response.get_data(as_text=True)
        return (response.get_json(silent=True) or {}).get("data")

    def login(email, senha="123456"):
        token = dados(client.post("/api/auth/login", json={"email": email, "password": senha}))["token"]
        h = {"Authorization": f"Bearer {token}"}
        me = dados(client.get("/api/user/me", headers=h))
        return {**h, "X-Unidade-Id": str(me["unidades"][0]["id"])}, me

    a, ma = login("admin@ufmg.br")
    b, mb = login("admin@npjdemo.br")
    for dono, atacante, usuario in ((a, b, ma), (b, a, mb)):
        dados(client.get("/api/atendido/", headers={**atacante, "X-Unidade-Id": dono["X-Unidade-Id"]}), 403)
        atendido = dados(client.get("/api/atendido/", headers=dono))["items"][0]
        dados(client.get(f'/api/atendido/{atendido["id"]}', headers=atacante), 404)
        dados(client.delete(f'/api/user/{usuario["id"]}', headers=atacante), 404)
        dados(client.post("/api/caso/", headers=atacante, json={
            "area_direito": "civel", "situacao_deferimento": "ativo",
            "id_usuario_responsavel": usuario["id"], "ids_clientes": [atendido["id"]],
        }), 400)
    with app.test_request_context():
        PlataformaService().criar_admin("Revisor fictício", "review@example.test", "12345678")
        db.get_session().commit()
    token = dados(client.post("/api/plataforma/auth/login", json={
        "email": "review@example.test", "password": "12345678",
    }))["token"]
    ph = {"Authorization": f"Bearer {token}"}
    dados(client.get("/api/atendido/", headers={**ph, "X-Unidade-Id": a["X-Unidade-Id"]}), 401)
    dados(client.get("/api/plataforma/tenants", headers=a), 401)
    criado = dados(client.post("/api/plataforma/tenants", headers=ph, json={
        "nome": "NPJ Fictício", "sigla": "REV", "slug": "revisao-ficticia",
        "unidade_nome": "Sede", "unidade_sigla": "SD",
        "admin_nome": "Admin Fictício", "admin_email": "novo@example.test",
    }), 201)
    link = criado["link_primeiro_acesso"].rsplit("/", 1)[-1]
    url_ativo = f'/api/plataforma/tenants/{criado["tenant"]["id"]}/ativo'
    dados(client.patch(url_ativo, headers=ph, json={"ativo": False}))
    dados(client.get(f"/api/auth/reset-password/{link}/validate"), 400)
    dados(client.post("/api/auth/reset-password", json={"token": link, "password": "12345678"}), 400)
    dados(client.patch(url_ativo, headers=ph, json={"ativo": True}))
    dados(client.post("/api/auth/reset-password", json={"token": link, "password": "12345678"}))
    novo, _ = login("novo@example.test", "12345678")
    dados(client.patch(url_ativo, headers=ph, json={"ativo": False}))
    dados(client.get("/api/user/me", headers=novo), 401)
    dados(client.post("/api/auth/login", json={"email": "novo@example.test", "password": "12345678"}), 401)


def test_migration_djen(mysql_descartavel):
    """DJEN (d3e4f5a6b7c8): numero_cnj dos existentes, chave desligada, ida e volta.

    Vai só até a revisão do DJEN: o downgrade a partir do head passaria antes
    pela migration dos processos sem caso, e o esquema "depois" não seria o
    desta migration.
    """
    from scripts.seed_database import seed_database

    engine, cfg = mysql_descartavel
    command.upgrade(cfg, "c2d3e4f5a6b7")
    seed_database(engine, senha="123456", tenants=("daj-ufmg", "npj-demo"))
    with engine.begin() as conn:
        ids = conn.execute(text("SELECT id FROM processos ORDER BY id LIMIT 2")).scalars().all()
        conn.execute(text("UPDATE processos SET numero = '1000001-11.2026.8.13.0001' WHERE id = :id"), {"id": ids[0]})
        conn.execute(text("UPDATE processos SET numero = 'ANTIGO 123/99' WHERE id = :id"), {"id": ids[1]})
    antes = _schema(engine)
    command.upgrade(cfg, DJEN)
    with engine.connect() as conn:
        cnj = dict(conn.execute(text("SELECT id, numero_cnj FROM processos WHERE id IN :ids")
                                .bindparams(sa_bindparam("ids", expanding=True)), {"ids": ids}).all())
        assert cnj == {ids[0]: "10000011120268130001", ids[1]: None}
        assert conn.execute(text("SELECT COUNT(*) FROM processos WHERE djen_pendente = 1")).scalar() == 0
        assert conn.execute(text("SELECT COUNT(*) FROM tenants WHERE djen_ativo = 1")).scalar() == 0
    depois = _schema(engine)
    # Ida e volta: o downgrade devolve o esquema anterior e o upgrade o refaz.
    command.downgrade(cfg, "c2d3e4f5a6b7")
    assert _schema(engine) == antes
    command.upgrade(cfg, DJEN)
    assert _schema(engine) == depois
    # A FK composta impede publicação de um NPJ apontar para caso de outro.
    with engine.connect() as conn:
        caso_outro = conn.execute(text("SELECT id FROM casos WHERE tenant_id = 2 LIMIT 1")).scalar_one()
        unidade_daj = conn.execute(text("SELECT id FROM unidades WHERE tenant_id = 1 LIMIT 1")).scalar_one()
    with pytest.raises(IntegrityError) as erro, engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO djen_comunicacoes (tenant_id, id_djen, numero_processo, data_disponibilizacao,"
            " situacao, capturada_em, unidade_id, id_caso) VALUES (1, 1, '1', CURDATE(), 'vinculada',"
            " NOW(), :u, :c)"), {"u": unidade_daj, "c": caso_outro})
    assert erro.value.orig.args[0] == 1452
    # djen_oabs: a mesma OAB nos dois NPJs (unicidade por tenant), mas nunca
    # com a unidade do outro NPJ.
    with engine.connect() as conn:
        unidade_outro = conn.execute(text("SELECT id FROM unidades WHERE tenant_id = 2 LIMIT 1")).scalar_one()
    with engine.begin() as conn:
        for tenant, unidade in ((1, unidade_daj), (2, unidade_outro)):
            conn.execute(text(
                "INSERT INTO djen_oabs (tenant_id, numero_oab, uf_oab, unidade_id, criado_em)"
                " VALUES (:t, '123456', 'MG', :u, NOW())"), {"t": tenant, "u": unidade})
    with pytest.raises(IntegrityError) as erro, engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO djen_oabs (tenant_id, numero_oab, uf_oab, unidade_id, criado_em)"
            " VALUES (1, '654321', 'MG', :u, NOW())"), {"u": unidade_outro})
    assert erro.value.orig.args[0] == 1452
    with pytest.raises(IntegrityError) as erro, engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO djen_oabs (tenant_id, numero_oab, uf_oab, unidade_id, criado_em)"
            " VALUES (1, '123456', 'MG', :u, NOW())"), {"u": unidade_daj})
    assert erro.value.orig.args[0] == 1062
    # Evento do DJEN (sem autor) impede o downgrade, que não apaga eventos.
    with engine.begin() as conn:
        caso, unidade = conn.execute(
            text("SELECT id, unidade_id FROM casos WHERE tenant_id = 1 LIMIT 1")).one()
        conn.execute(text(
            "INSERT INTO eventos (tenant_id, id_caso, tipo, data_evento, data_criacao, status,"
            " unidade_id, origem) VALUES (1, :c, 'Intimação', CURDATE(), NOW(), 1, :u, 'djen')"),
            {"c": caso, "u": unidade})
    with pytest.raises(RuntimeError, match="Remova-os antes do downgrade"):
        command.downgrade(cfg, "c2d3e4f5a6b7")
    assert _schema(engine) == depois


def _colunas_atendido(engine) -> dict[str, tuple]:
    with engine.connect() as conn:
        return {
            r[0]: tuple(r[1:])
            for r in conn.execute(text(
                "SELECT COLUMN_NAME, COLUMN_TYPE, CHARACTER_SET_NAME, COLLATION_NAME, IS_NULLABLE "
                "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'atendidos'"))
        }


def test_migration_processos_avulsos(mysql_descartavel):
    """Processos sem caso (f1a2b3c4d5e6): unidade do caso, nulidade dos dados do
    atendido sem mudar charset, FKs compostas e ida e volta.

    Vai só até a própria revisão: o esquema "depois" não inclui as migrations
    seguintes (banco de exemplos), que têm teste próprio.
    """
    from scripts.seed_database import seed_database

    engine, cfg = mysql_descartavel
    command.upgrade(cfg, DJEN)
    seed_database(engine, senha="123456", tenants=("daj-ufmg", "npj-demo"))
    antes = _schema(engine)
    colunas_antes = _colunas_atendido(engine)
    command.upgrade(cfg, AVULSOS)
    with engine.connect() as conn:
        # Todo processo herdou a unidade do próprio caso.
        assert conn.execute(text(
            "SELECT COUNT(*) FROM processos p JOIN casos c ON c.id = p.id_caso "
            "AND c.tenant_id = p.tenant_id WHERE p.unidade_id = c.unidade_id")).scalar() == \
            conn.execute(text("SELECT COUNT(*) FROM processos")).scalar() > 0
        assert conn.execute(text("SELECT COUNT(*) FROM atendidos WHERE sem_triagem <> 0")).scalar() == 0
    colunas = _colunas_atendido(engine)
    for coluna in ("data_nascimento", "cpf", "celular", "email", "estado_civil",
                   "como_conheceu", "procurou_outro_local", "pj_constituida"):
        # Só a nulidade muda; tipo, charset e collation (latin1 legado) ficam.
        assert colunas_antes[coluna][3] == "NO" and colunas[coluna][3] == "YES", coluna
        assert colunas[coluna][:3] == colunas_antes[coluna][:3], coluna
    assert {k: v for k, v in colunas.items() if k != "sem_triagem"}.keys() == colunas_antes.keys()
    depois = _schema(engine)
    insp = inspect(engine)
    assert next(c for c in insp.get_columns("processos") if c["name"] == "id_caso")["nullable"] is True
    assert any(f["constrained_columns"] == ["tenant_id", "unidade_id"] and f["referred_table"] == "unidades"
               for f in insp.get_foreign_keys("processos"))

    # FKs compostas: processo sem caso e parte nunca cruzam NPJs.
    with engine.connect() as conn:
        unidade_daj = conn.execute(text("SELECT id FROM unidades WHERE tenant_id = 1 LIMIT 1")).scalar_one()
        unidade_outro = conn.execute(text("SELECT id FROM unidades WHERE tenant_id = 2 LIMIT 1")).scalar_one()
        usuario = conn.execute(text("SELECT id FROM usuarios WHERE tenant_id = 1 LIMIT 1")).scalar_one()
        atendido_outro = conn.execute(text("SELECT id FROM atendidos WHERE tenant_id = 2 LIMIT 1")).scalar_one()
    novo_processo = (
        "INSERT INTO processos (tenant_id, especie, status, id_criado_por, unidade_id) "
        "VALUES (1, 'Ação', 1, :u, :unidade)"
    )
    with pytest.raises(IntegrityError) as erro, engine.begin() as conn:
        conn.execute(text(novo_processo), {"u": usuario, "unidade": unidade_outro})
    assert erro.value.orig.args[0] == 1452
    with engine.begin() as conn:
        processo = conn.execute(text(novo_processo), {"u": usuario, "unidade": unidade_daj}).lastrowid
        parte = conn.execute(text(
            "INSERT INTO atendidos (tenant_id, nome, status, sem_triagem, unidade_id) "
            "VALUES (1, 'Parte Fictícia', 1, 1, :unidade)"), {"unidade": unidade_daj}).lastrowid
        conn.execute(text(
            "INSERT INTO processo_partes (tenant_id, id_processo, id_atendido, polo) "
            "VALUES (1, :p, :a, 'passivo')"), {"p": processo, "a": parte})
        conn.execute(text(
            "INSERT INTO atendido_nomes (tenant_id, id_atendido, nome) VALUES (1, :a, 'UFMG')"),
            {"a": parte})
    for sql, valores in (
        ("INSERT INTO processo_partes (tenant_id, id_processo, id_atendido) VALUES (1, :p, :a)",
         {"p": processo, "a": atendido_outro}),
        ("INSERT INTO atendido_nomes (tenant_id, id_atendido, nome) VALUES (1, :a, 'X')",
         {"a": atendido_outro}),
    ):
        with pytest.raises(IntegrityError) as erro, engine.begin() as conn:
            conn.execute(text(sql), valores)
        assert erro.value.orig.args[0] == 1452
    with pytest.raises(IntegrityError) as erro, engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO atendido_nomes (tenant_id, id_atendido, nome) VALUES (1, :a, 'UFMG')"),
            {"a": parte})
    assert erro.value.orig.args[0] == 1062

    # O downgrade recusa antes de qualquer DDL enquanto houver processo sem
    # caso ou parte sem triagem.
    with pytest.raises(RuntimeError, match="Remova-os antes do downgrade"):
        command.downgrade(cfg, DJEN)
    assert _schema(engine) == depois
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM atendido_nomes"))
        conn.execute(text("DELETE FROM processo_partes"))
        conn.execute(text("DELETE FROM processos WHERE id = :p"), {"p": processo})
        conn.execute(text("DELETE FROM atendidos WHERE id = :a"), {"a": parte})
    command.downgrade(cfg, DJEN)
    assert _schema(engine) == antes
    assert _colunas_atendido(engine) == colunas_antes
    command.upgrade(cfg, AVULSOS)
    assert _schema(engine) == depois


def test_migration_djen_acervo(mysql_descartavel):
    """Esquema novo, unicode, unicidade por NPJ, FKs e downgrade descartável."""
    from scripts.seed_database import seed_database
    engine, cfg = mysql_descartavel
    command.upgrade(cfg, AVULSOS)
    seed_database(engine, senha="123456", tenants=("daj-ufmg", "npj-demo"))
    antes = _schema(engine)
    command.upgrade(cfg, "head")
    depois = _schema(engine)
    assert set(depois) - set(antes) == {"djen_publicacoes", "djen_classificacoes", "djen_classificacao_historico", "djen_consultas", "djen_consulta_resultados", "djen_monitoramentos", "djen_publicacao_unidades"}
    texto = "Intimação — prazo ≥ 15 dias 📎"
    novo = "INSERT INTO djen_publicacoes (tenant_id, id_djen, numero_processo, data_disponibilizacao, texto_plano, capturada_em) VALUES (:t, 1, '00000000020268130001', '2026-11-05', :texto, NOW())"
    with engine.begin() as conn:
        p1 = conn.execute(text(novo), {"t": 1, "texto": texto}).lastrowid
        p2 = conn.execute(text(novo), {"t": 2, "texto": texto}).lastrowid
        assert conn.execute(text("SELECT texto_plano FROM djen_publicacoes WHERE tenant_id=1")).scalar_one() == texto
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text(novo), {"t": 1, "texto": texto})
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text("INSERT INTO djen_classificacoes (tenant_id, id_publicacao, rotulo, origem) VALUES (1, :p, 'relevante', 'classificacao')"), {"p": p2})
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO djen_classificacoes (tenant_id, id_publicacao, rotulo, origem) VALUES (1, :p, 'relevante', 'classificacao')"), {"p": p1})
    command.downgrade(cfg, AVULSOS)
    assert _schema(engine) == antes
    command.upgrade(cfg, "head")
    assert _schema(engine) == depois


def test_acervo_concorrente_mysql(mysql_descartavel):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from datetime import date
    from flask import Flask
    from sqlalchemy.orm import Session
    from scripts.seed_database import seed_database
    from gestaolegal.repositories.djen_acervo_repository import DjenAcervoRepository
    from gestaolegal.utils.request_context import contexto_tenant
    engine, cfg = mysql_descartavel
    command.upgrade(cfg, 'head')
    seed_database(engine, senha='123456', tenants=('daj-ufmg', 'npj-demo'))
    app = Flask(__name__)
    barreira = Barrier(2)
    def gravar():
        with app.test_request_context(), contexto_tenant(1), Session(engine) as session:
            repo = object.__new__(DjenAcervoRepository)
            repo.session = session
            barreira.wait(timeout=10)
            pid = repo.guardar(dict(id_djen=98123, numero_processo='00000000020268130001', data_disponibilizacao=date(2026,11,5), texto_plano='Texto sintético 📎'))
            session.commit()
            return pid
    with ThreadPoolExecutor(max_workers=2) as executor:
        ids = list(executor.map(lambda _: gravar(), range(2)))
    assert ids[0] == ids[1]
    with engine.connect() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM djen_publicacoes')).scalar_one() == 1
        assert conn.execute(text('SELECT COUNT(*) FROM djen_classificacoes')).scalar_one() == 1


def test_monitoramento_migra_acesso_e_oabs(mysql_descartavel):
    from scripts.seed_database import seed_database
    engine,cfg=mysql_descartavel
    command.upgrade(cfg,'b3c4d5e6f7a8')
    seed_database(engine,senha='123456',tenants=('daj-ufmg','npj-demo'))
    with engine.begin() as conn:
        pid=conn.execute(text("INSERT INTO djen_publicacoes (tenant_id,id_djen,numero_processo,data_disponibilizacao,capturada_em) VALUES (1,880001,'00000000020268130001','2026-11-01',NOW())")).lastrowid
        qid=conn.execute(text("INSERT INTO djen_consultas (tenant_id,origem,parametros,inicio,status,unidade_id) VALUES (1,'parte','{}',NOW(),'ok',1)")).lastrowid
        conn.execute(text("INSERT INTO djen_consulta_resultados (tenant_id,id_consulta,id_publicacao) VALUES (1,:q,:p)"),{'q':qid,'p':pid})
        conn.execute(text("INSERT INTO djen_oabs (tenant_id,numero_oab,uf_oab,ativo,criado_em,unidade_id) VALUES (1,'123456','MG',0,NOW(),1)"))
    command.upgrade(cfg,'head')
    with engine.begin() as conn:
        assert conn.execute(text('SELECT id_publicacao,unidade_id,origem FROM djen_publicacao_unidades WHERE tenant_id=1')).one()==(pid,1,'parte')
        assert conn.execute(text('SELECT valor,ativo FROM djen_monitoramentos WHERE tenant_id=1')).one()==('123456/MG',0)
        conn.execute(text('DELETE FROM djen_consulta_resultados WHERE tenant_id=1'))
        conn.execute(text('DELETE FROM djen_consultas WHERE tenant_id=1'))
        assert conn.execute(text('SELECT COUNT(*) FROM djen_publicacao_unidades WHERE tenant_id=1')).scalar()==1
        assert conn.execute(text('SELECT COUNT(*) FROM djen_publicacoes WHERE tenant_id=1')).scalar()==1
