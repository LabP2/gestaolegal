"""Executa a rotina do DJEN, o mesmo que `flask djen sincronizar`.

Uso (no container da API, com o .env carregado):

    docker compose run --rm api python scripts/sincronizar_djen.py [--tenant SLUG]

Sai sem chamar a API se DJEN_SYNC_ENABLED estiver desligado. Ligar em QA ou
produção exige decisão explícita: a rotina gera notificações para usuários
reais. Agendamento: README, seção "Rotina do DJEN".
"""

import sys


def main(argv: list[str] | None = None) -> int:
    from gestaolegal import create_app
    from gestaolegal.cli import sincronizar

    app = create_app()
    with app.app_context():
        sincronizar.main(args=argv if argv is not None else sys.argv[1:],
                         prog_name="sincronizar_djen", standalone_mode=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
