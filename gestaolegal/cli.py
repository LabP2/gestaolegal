"""Comandos de linha de comando do app (`flask --app gestaolegal:create_app() ...`).

`flask plataforma criar-admin --email ... --nome ...` cria o administrador da
plataforma, que não tem tela de cadastro: é o bootstrap da instalação
(docs/plano-multitenant.md §6.1). Em Docker:

    docker compose run --rm api flask --app 'gestaolegal:create_app()' \\
        plataforma criar-admin --email voce@exemplo.br --nome "Seu Nome"

A senha é pedida no terminal, sem eco, e não aparece no histórico do shell.
"""

import click
from flask import current_app
from flask.cli import AppGroup

from gestaolegal.database.session import close_session
from gestaolegal.exceptions import ValidationException

plataforma_cli = AppGroup("plataforma", help="Administração da plataforma.")


@plataforma_cli.command("criar-admin")
@click.option("--email", required=True, help="E-mail de login do administrador.")
@click.option("--nome", required=True, help="Nome do administrador.")
@click.password_option("--senha", help="Senha (pedida no terminal se omitida).")
def criar_admin(email: str, nome: str, senha: str) -> None:
    """Cria um administrador da plataforma."""
    from gestaolegal.services.plataforma_service import PlataformaService

    # Um contexto de requisição faz os repositórios dividirem a mesma sessão,
    # como numa chamada da API; close_session grava ou desfaz no fim.
    with current_app.test_request_context():
        try:
            admin_id = PlataformaService().criar_admin(nome, email, senha)
        except ValidationException as e:
            close_session(e)
            raise click.ClickException(e.message) from e
        except Exception as e:
            close_session(e)
            raise
        close_session()
    click.echo(f"Administrador da plataforma criado: {email} (id {admin_id})")
