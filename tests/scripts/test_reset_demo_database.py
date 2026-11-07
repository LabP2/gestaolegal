from unittest.mock import MagicMock

import pytest
from sqlalchemy.engine import URL

from scripts import reset_demo_database as resetter


@pytest.fixture
def demo_env(monkeypatch):
    monkeypatch.setattr(resetter, "load_dotenv", lambda *_: None)
    for key, value in {
        "FLASK_ENV": "testing", "DB_USER": "demo", "DB_PASSWORD": "p@ss%word",
        "DB_HOST": "db", "DB_PORT": "3307", "DB_NAME": "demo",
        "DEMO_DB_NAME": "demo", "SEED_PASSWORD": "123456",
    }.items():
        monkeypatch.setenv(key, value)


def test_configuration(demo_env):
    url, password, config = resetter.configuration()
    assert url.database == "demo"
    assert url.port == 3307
    assert url.password == "p@ss%word"
    assert password == "123456"
    assert config.attributes["database_url"] == url


@pytest.mark.parametrize("key,value", [
    ("FLASK_ENV", "production"), ("FLASK_ENV", "demo"),
    ("DEMO_DB_NAME", "other"), ("DEMO_DB_NAME", ""),
    ("DB_PASSWORD", ""), ("SEED_PASSWORD", "12345"),
    ("SEED_PASSWORD", "x" * 73),
])
def test_rejects_invalid_configuration(demo_env, monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(ValueError):
        resetter.configuration()


@pytest.mark.parametrize("name", resetter.SYSTEM_DATABASES)
def test_rejects_system_database(demo_env, monkeypatch, name):
    monkeypatch.setenv("DB_NAME", name)
    monkeypatch.setenv("DEMO_DB_NAME", name)
    with pytest.raises(ValueError):
        resetter.configuration()


@pytest.fixture
def operations(monkeypatch):
    server, engine = MagicMock(), MagicMock()
    conn = server.connect.return_value.__enter__.return_value
    conn.execute.return_value.scalar.return_value = 1
    server.dialect.identifier_preparer.quote_identifier.side_effect = lambda n: f"`{n}`"
    factory = MagicMock(side_effect=[server, engine])
    monkeypatch.setattr(resetter, "create_engine", factory)
    upgrade, seed = MagicMock(), MagicMock()
    monkeypatch.setattr(resetter.command, "upgrade", upgrade)
    monkeypatch.setattr(resetter, "seed_database", seed)
    steps = MagicMock()
    steps.attach_mock(conn.exec_driver_sql, "ddl")
    steps.attach_mock(upgrade, "migrate")
    steps.attach_mock(seed, "seed")
    return server, engine, conn, upgrade, seed, steps


def test_reset_order_and_cleanup(operations):
    server, engine, conn, upgrade, seed, steps = operations
    url = URL.create("mysql+pymysql", database="demo")
    config = object()
    resetter.reset(url, "123456", config)
    assert [c[0] for c in steps.mock_calls] == ["ddl", "ddl", "migrate", "seed"]
    assert conn.exec_driver_sql.call_args_list[0].args == ("DROP DATABASE IF EXISTS `demo`",)
    upgrade.assert_called_once_with(config, "head")
    seed.assert_called_once_with(engine, senha="123456", tenants=resetter.SLUGS_DEMO)
    assert "RELEASE_LOCK" in str(conn.execute.call_args.args[0])
    engine.dispose.assert_called_once()
    server.dispose.assert_called_once()


def test_busy_lock_does_not_drop(operations):
    server, _, conn, upgrade, seed, _ = operations
    conn.execute.return_value.scalar.return_value = 0
    with pytest.raises(ValueError, match="Outro reset"):
        resetter.reset(URL.create("mysql+pymysql", database="demo"), "123456", object())
    conn.exec_driver_sql.assert_not_called()
    upgrade.assert_not_called()
    seed.assert_not_called()
    server.dispose.assert_called_once()


def test_migration_failure_stops_before_seed(operations):
    server, _, conn, upgrade, seed, _ = operations
    upgrade.side_effect = RuntimeError("migration falhou")
    with pytest.raises(RuntimeError):
        resetter.reset(URL.create("mysql+pymysql", database="demo"), "123456", object())
    seed.assert_not_called()
    assert "RELEASE_LOCK" in str(conn.execute.call_args.args[0])
    server.dispose.assert_called_once()


@pytest.mark.parametrize("fail_at,expected", [
    ("", ["check", "stop", "reset", "start"]),
    ("check", ["check"]),
    ("stop", ["check", "stop"]),
    ("reset", ["check", "stop", "reset"]),
])
def test_wrapper_sequence(tmp_path, monkeypatch, fail_at, expected):
    import os
    import shutil
    import subprocess

    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy(resetter.ROOT / "scripts/reset_demo.sh", scripts)
    binary = tmp_path / "docker"
    binary.write_text('''#!/usr/bin/env bash
set -eu
case "$*" in
  *--check) step=check ;;
  *" stop "*) step=stop ;;
  *" start "*) step=start ;;
  *) step=reset ;;
esac
printf '%s\\n' "$step" >> "$TEST_LOG"
if [ "$step" = "$FAIL_AT" ]; then exit 1; fi
''')
    binary.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
    monkeypatch.setenv("TEST_LOG", str(tmp_path / "calls"))
    monkeypatch.setenv("FAIL_AT", fail_at)
    result = subprocess.run(["bash", str(scripts / "reset_demo.sh")], cwd="/tmp",
                            capture_output=True, text=True)
    assert (result.returncode == 0) == (not fail_at), result.stderr
    assert (tmp_path / "calls").read_text().splitlines() == expected


def _resultado(scalar=None, slugs=()):
    result = MagicMock()
    result.scalar.return_value = scalar
    result.scalars.return_value.all.return_value = list(slugs)
    return result


def _banco_com(conn, slugs, tabela_existe=True):
    """Faz o MySQL simulado responder ao lock e à leitura de `tenants`."""
    consultas = []

    def execute(stmt, params=None):
        sql = str(stmt)
        consultas.append(sql)
        if "information_schema" in sql:
            assert params == {"db": "demo"}
            return _resultado(scalar=1 if tabela_existe else 0)
        if "FROM `demo`.tenants" in sql:
            return _resultado(slugs=slugs)
        return _resultado(scalar=1)  # GET_LOCK / RELEASE_LOCK

    conn.execute.side_effect = execute
    conn.dialect.identifier_preparer.quote_identifier.side_effect = lambda n: f"`{n}`"
    return consultas


def test_slugs_permitidos_padrao_sao_os_npjs_de_demonstracao(monkeypatch):
    monkeypatch.delenv("DEMO_TENANT_SLUGS", raising=False)
    assert resetter.slugs_permitidos() == {"daj-ufmg", "npj-demo"}
    monkeypatch.setenv("DEMO_TENANT_SLUGS", " daj-ufmg, npj-demo ,npj-ensaio ")
    assert resetter.slugs_permitidos() == {"daj-ufmg", "npj-demo", "npj-ensaio"}


@pytest.mark.parametrize("valor", ["", " , ", "daj-ufmg", "npj-demo,npj-real"])
def test_slugs_permitidos_precisam_incluir_os_npjs_recriados(monkeypatch, valor):
    monkeypatch.setenv("DEMO_TENANT_SLUGS", valor)
    with pytest.raises(ValueError, match="DEMO_TENANT_SLUGS deve incluir"):
        resetter.slugs_permitidos()


def test_tenants_nao_permitidos_sem_tabela_nao_le_slugs():
    conn = MagicMock()
    consultas = _banco_com(conn, ["npj-real"], tabela_existe=False)
    assert resetter.tenants_nao_permitidos(conn, "demo", {"daj-ufmg"}) == []
    assert not any("tenants" in sql and "information_schema" not in sql for sql in consultas)


def test_tenants_nao_permitidos_lista_os_slugs_fora():
    conn = MagicMock()
    _banco_com(conn, ["npj-real", "daj-ufmg", "outro-npj"])
    assert resetter.tenants_nao_permitidos(conn, "demo", {"daj-ufmg", "npj-demo"}) == [
        "npj-real", "outro-npj"]


def test_reset_recusa_banco_com_npj_fora_da_lista(operations):
    server, _, conn, upgrade, seed, _ = operations
    _banco_com(conn, ["daj-ufmg", "npj-demo", "npj-real"])
    with pytest.raises(ValueError, match="npj-real"):
        resetter.reset(URL.create("mysql+pymysql", database="demo"), "123456", object(),
                       frozenset({"daj-ufmg", "npj-demo"}))
    conn.exec_driver_sql.assert_not_called()
    upgrade.assert_not_called()
    seed.assert_not_called()
    assert "RELEASE_LOCK" in str(conn.execute.call_args.args[0])
    server.dispose.assert_called_once()


def test_reset_segue_com_apenas_npjs_de_demonstracao(operations):
    _, _, conn, upgrade, seed, steps = operations
    _banco_com(conn, ["daj-ufmg", "npj-demo"])
    resetter.reset(URL.create("mysql+pymysql", database="demo"), "123456", object(),
                   frozenset({"daj-ufmg", "npj-demo"}))
    assert [c[0] for c in steps.mock_calls] == ["ddl", "ddl", "migrate", "seed"]


def test_check_recusa_banco_com_npj_fora_da_lista(demo_env, monkeypatch, capsys):
    server = MagicMock()
    conn = server.connect.return_value.__enter__.return_value
    _banco_com(conn, ["daj-ufmg", "npj-real"])
    factory = MagicMock(return_value=server)
    monkeypatch.setattr(resetter, "create_engine", factory)
    monkeypatch.setattr(resetter.sys, "argv", ["reset_demo_database.py", "--check"])
    assert resetter.main() == 1
    assert "npj-real" in capsys.readouterr().err
    assert factory.call_args.args[0].database is None
    server.dispose.assert_called_once()


def test_check_aceita_banco_so_com_npjs_de_demonstracao(demo_env, monkeypatch, capsys):
    server = MagicMock()
    _banco_com(server.connect.return_value.__enter__.return_value, ["daj-ufmg", "npj-demo"])
    monkeypatch.setattr(resetter, "create_engine", MagicMock(return_value=server))
    monkeypatch.setattr(resetter.sys, "argv", ["reset_demo_database.py", "--check"])
    assert resetter.main() == 0
    assert "validada" in capsys.readouterr().out


def test_check_sem_conexao_falha_antes_de_parar_a_api(demo_env, monkeypatch, capsys):
    from sqlalchemy.exc import OperationalError

    server = MagicMock()
    server.connect.side_effect = OperationalError("SELECT", {}, Exception("senha=p@ss%word"))
    monkeypatch.setattr(resetter, "create_engine", MagicMock(return_value=server))
    monkeypatch.setattr(resetter.sys, "argv", ["reset_demo_database.py", "--check"])
    assert resetter.main() == 1
    erro = capsys.readouterr().err
    assert "NPJs do banco" in erro and "p@ss%word" not in erro
    server.dispose.assert_called_once()
