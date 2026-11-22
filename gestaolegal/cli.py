"""Comandos de linha de comando do app (`flask --app gestaolegal:create_app() ...`).

`flask plataforma criar-admin --email ... --nome ...` cria o administrador da
plataforma, que não tem tela de cadastro: é o bootstrap da instalação
(docs/plano-multitenant.md §6.1). Em Docker:

    docker compose run --rm api flask --app 'gestaolegal:create_app()' \\
        plataforma criar-admin --email voce@exemplo.br --nome "Seu Nome"

A senha é pedida no terminal, sem eco, e não aparece no histórico do shell.

`flask djen sincronizar [--tenant SLUG]` roda a captura do DJEN para os NPJs
com a chave ligada (docs/plano-djen.md, §4). Sai sem fazer nada com
`DJEN_SYNC_ENABLED` desligado. O agendamento (cron no host) está no README.

`flask djen semear-demo [--tenant npj-demo]` só funciona com `DEMO_MODE=true`:
liga o DJEN do NPJ de demonstração, ativa as OABs dele e roda uma captura no
DJEN fictício (gestaolegal/integrations/djen_demo.py), para a demo já abrir
com publicações. O reset da demo (scripts/reset_demo.sh) chama este comando.
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


djen_cli = AppGroup("djen", help="Integração com o DJEN (docs/plano-djen.md).")


def sincronizar_djen(
    slug: str | None = None,
    janela_dias: int | None = None,
    max_processos: int | None = None,
    echo=click.echo,
) -> dict[str, str]:
    """Roda a rotina do DJEN para cada NPJ com a chave ligada.

    Devolve {slug: status}. NPJs pulados aparecem com o motivo. A falha de um
    NPJ não interrompe os outros; cada um grava a sua linha em
    `djen_sincronizacoes`.
    """
    import logging

    from gestaolegal.config import Config
    from gestaolegal.repositories.tenant_repository import TenantRepository
    from gestaolegal.services.djen_service import DJENService
    from gestaolegal.utils.request_context import contexto_tenant, sem_tenant

    logger = logging.getLogger("gestaolegal.djen")
    if not Config.DJEN_SYNC_ENABLED:
        echo("DJEN_SYNC_ENABLED desligado: nada a fazer.")
        return {}

    with current_app.test_request_context():
        with sem_tenant("djen: listar NPJs ativos"):
            todos = TenantRepository().listar_para_djen()
        close_session()

    if slug is not None:
        todos = [t for t in todos if t.slug == slug]
        if not todos:
            raise click.ClickException(f"NPJ não encontrado: {slug}")

    resultado: dict[str, str] = {}
    for tenant in todos:
        if not tenant.ativo:
            motivo = "NPJ inativo"
        elif not tenant.djen_ativo:
            motivo = "DJEN desligado para o NPJ"
        else:
            motivo = None
        if motivo:
            logger.info(f"DJEN: {tenant.slug} pulado ({motivo})")
            echo(f"{tenant.slug}: pulado ({motivo})")
            resultado[tenant.slug] = f"pulado: {motivo}"
            continue
        with current_app.test_request_context():
            try:
                with contexto_tenant(tenant.id):
                    registro = DJENService().sincronizar(janela_dias, max_processos)
                close_session()
            except Exception as e:  # um NPJ não derruba os outros
                close_session(e)
                logger.exception(f"DJEN: falha ao sincronizar {tenant.slug}")
                echo(f"{tenant.slug}: falhou ({e})")
                resultado[tenant.slug] = "falhou"
                continue
        echo(
            f"{tenant.slug}: {registro['status']} — {registro['novas']} nova(s), "
            f"{registro['atualizadas']} atualizada(s), {registro['vinculadas']} vinculada(s)"
        )
        resultado[tenant.slug] = registro["status"]
    return resultado


@djen_cli.command("sincronizar")
@click.option("--tenant", "slug", default=None, help="Slug de um NPJ só.")
@click.option("--janela-dias", type=int, default=None, help="Padrão: DJEN_JANELA_DIAS.")
@click.option("--max-processos", type=int, default=None, help="Padrão: DJEN_MAX_PROCESSOS.")
def sincronizar(slug: str | None, janela_dias: int | None, max_processos: int | None) -> None:
    """Captura as publicações do DJEN (rotina agendada por cron no host)."""
    sincronizar_djen(slug, janela_dias, max_processos)


def semear_djen_demo(slug: str = "npj-demo", echo=click.echo) -> dict | None:
    """Liga o DJEN do NPJ de demonstração e captura as publicações fictícias.

    Recusa (sem erro) fora do `DEMO_MODE`: em produção, ligar o DJEN de um NPJ
    é decisão da plataforma, e a captura iria à API real.
    """
    from gestaolegal.repositories.tenant_repository import TenantRepository
    from gestaolegal.services.djen_service import DJENService, demo_ligado
    from gestaolegal.utils.request_context import contexto_tenant, sem_tenant

    if not demo_ligado():
        echo("DEMO_MODE desligado: nada a fazer.")
        return None

    with current_app.test_request_context():
        try:
            repo = TenantRepository()
            with sem_tenant("djen: ligar o DJEN do NPJ de demonstração"):
                tenant_id = repo.ligar_djen_demonstracao(slug)
            if tenant_id is None:
                raise click.ClickException(f"NPJ não encontrado: {slug}")
            repo.session.commit()
            close_session()
        except Exception as e:
            close_session(e)
            raise

    with current_app.test_request_context():
        try:
            with contexto_tenant(tenant_id):
                registro = DJENService().sincronizar()
            close_session()
        except Exception as e:
            close_session(e)
            raise
    echo(
        f"{slug}: DJEN ligado; {registro['novas']} publicação(ões) fictícia(s), "
        f"{registro['vinculadas']} vinculada(s)"
    )
    return registro


@djen_cli.command("semear-demo")
@click.option("--tenant", "slug", default="npj-demo", help="Slug do NPJ de demonstração.")
def semear_demo(slug: str) -> None:
    """Liga o DJEN fictício no NPJ de demonstração (só com DEMO_MODE=true)."""
    semear_djen_demo(slug)
