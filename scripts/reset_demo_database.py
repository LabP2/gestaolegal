"""Apaga e recria exclusivamente o banco confirmado por DEMO_DB_NAME.

Use scripts/reset_demo.sh para também parar a API durante a operação.

O DROP apaga todos os NPJs (tenants) do banco. Por isso, `--check` e o próprio
reset recusam quando há tenant com slug fora de DEMO_TENANT_SLUGS (lista
separada por vírgulas; padrão e mínimo: os NPJs de demonstração do seed).
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.seed_database import SLUGS_DEMO, seed_database
SYSTEM_DATABASES = {"mysql", "sys", "information_schema", "performance_schema"}


def configuration():
    load_dotenv(ROOT / ".env")
    if os.environ.get("FLASK_ENV", "development") not in {"development", "testing"}:
        raise ValueError("Reset disponível apenas com FLASK_ENV=development ou testing.")
    for key in ("DB_USER", "DB_PASSWORD", "DB_HOST", "DB_NAME", "DEMO_DB_NAME"):
        if not os.environ.get(key):
            raise ValueError(f"Configure {key} no ambiente ou .env.")
    name = os.environ["DB_NAME"]
    if name != os.environ["DEMO_DB_NAME"] or name.lower() in SYSTEM_DATABASES:
        raise ValueError("DEMO_DB_NAME deve confirmar exatamente DB_NAME, fora dos bancos de sistema.")
    password = os.environ.get("SEED_PASSWORD", "123456")
    if not 6 <= len(password.encode("utf-8")) <= 72:
        raise ValueError("SEED_PASSWORD deve ter entre 6 e 72 bytes em UTF-8.")
    url = URL.create("mysql+pymysql", username=os.environ["DB_USER"],
                     password=os.environ["DB_PASSWORD"], host=os.environ["DB_HOST"],
                     port=int(os.environ.get("DB_PORT", "3306")), database=name)
    config = Config(str(ROOT / "migrations/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.attributes["database_url"] = url
    # Detecta migrations ausentes ou heads divergentes antes de apagar dados.
    if ScriptDirectory.from_config(config).get_current_head() is None:
        raise ValueError("Nenhuma migration encontrada.")
    return url, password, config


def slugs_permitidos() -> frozenset[str]:
    bruto = os.environ.get("DEMO_TENANT_SLUGS")
    if bruto is None:
        return frozenset(SLUGS_DEMO)
    slugs = frozenset(s.strip() for s in bruto.split(",") if s.strip())
    faltando = [slug for slug in SLUGS_DEMO if slug not in slugs]
    if faltando:
        # O reset recria esses NPJs; sem eles na lista, o próximo --check recusaria.
        raise ValueError("DEMO_TENANT_SLUGS deve incluir " + ", ".join(faltando) + ".")
    return slugs


def tenants_nao_permitidos(conn, database: str, permitidos) -> list[str]:
    """Slugs do banco fora da lista. Banco ou tabela inexistente: nada a perder."""
    existe = conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = :db AND table_name = 'tenants'"), {"db": database}).scalar()
    if not existe:
        return []
    nome = conn.dialect.identifier_preparer.quote_identifier(database)
    slugs = conn.execute(text(f"SELECT slug FROM {nome}.tenants")).scalars().all()
    return sorted(set(slugs) - set(permitidos))


def exigir_somente_tenants_de_demo(conn, database: str, permitidos) -> None:
    fora = tenants_nao_permitidos(conn, database, permitidos)
    if fora:
        raise ValueError("O banco tem NPJs fora de DEMO_TENANT_SLUGS: " + ", ".join(fora)
                         + ". O reset apagaria esses dados; nada foi alterado.")


def verificar_tenants(url, permitidos) -> None:
    # Sem banco na URL: o banco de demo pode ainda não existir. (`URL.set`
    # ignora None e manteria o banco.)
    server = create_engine(url._replace(database=None))
    try:
        with server.connect() as conn:
            exigir_somente_tenants_de_demo(conn, url.database, permitidos)
    except SQLAlchemyError:
        # A mensagem do driver pode trazer credenciais; o reset não começou.
        raise ValueError("não foi possível ler os NPJs do banco; o reset não foi iniciado.") from None
    finally:
        server.dispose()


def reset(url, password, config, permitidos=None):
    permitidos = slugs_permitidos() if permitidos is None else permitidos
    server = create_engine(url.set(database=None), isolation_level="AUTOCOMMIT")
    try:
        with server.connect() as conn:
            # O lock vive nesta conexão, inclusive durante migrations e seed.
            lock = "demo-reset:" + hashlib.sha256(url.database.encode()).hexdigest()[:48]
            if conn.execute(text("SELECT GET_LOCK(:name, 0)"), {"name": lock}).scalar() != 1:
                raise ValueError("Outro reset deste banco já está em execução.")
            try:
                # Repetida aqui, com o lock, para valer também sem o --check.
                exigir_somente_tenants_de_demo(conn, url.database, permitidos)
                name = server.dialect.identifier_preparer.quote_identifier(url.database)
                print(f"Recriando banco {name}...", flush=True)
                conn.exec_driver_sql(f"DROP DATABASE IF EXISTS {name}")
                conn.exec_driver_sql(f"CREATE DATABASE {name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                command.upgrade(config, "head")
                engine = create_engine(url)
                try:
                    seed_database(engine, senha=password, tenants=SLUGS_DEMO)
                finally:
                    engine.dispose()
                print("Reset de demonstração concluído.", flush=True)
            finally:
                conn.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": lock})
    finally:
        server.dispose()


def main():
    try:
        settings = configuration()
        permitidos = slugs_permitidos()
        if sys.argv[1:] == ["--check"]:
            verificar_tenants(settings[0], permitidos)
            print("Configuração do reset validada.")
        elif sys.argv[1:]:
            raise ValueError("Uso: reset_demo_database.py [--check]")
        else:
            reset(*settings, permitidos)
    except ValueError as exc:
        print(f"reset-demo: {exc}", file=sys.stderr)
        return 1
    except Exception:
        # Exceções SQL podem conter credenciais ou parâmetros privados.
        print("reset-demo: falha ao recriar o banco, aplicar migrations ou executar seed. "
              "O reset não é transacional; corrija a causa e execute novamente.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
