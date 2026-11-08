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
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError, OperationalError

ROOT = Path(__file__).resolve().parents[2]
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
