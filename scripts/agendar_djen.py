"""Worker diário DJEN: 04h (semana), 10h e 16h (janela curta), São Paulo.

Executar uma instância dedicada. Recomeçar o worker recupera o último horário
vencido do dia; o lock do banco impede execução simultânea no mesmo NPJ.
"""

import time
from datetime import datetime
from zoneinfo import ZoneInfo


def horario_devido(agora):
    return next((h for h in (16, 10, 4) if agora.hour >= h), None)


def main():
    from gestaolegal import create_app
    from gestaolegal.cli import sincronizar_djen
    from gestaolegal.config import Config

    app = create_app()
    ultima = None
    while True:
        agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
        hora = horario_devido(agora)
        chave = (agora.date(), hora)
        if Config.DJEN_SYNC_ENABLED and hora is not None and chave != ultima:
            with app.app_context():
                sincronizar_djen(
                    janela_dias=Config.DJEN_JANELA_DIAS
                    if hora == 4
                    else Config.DJEN_JANELA_DIURNA_DIAS
                )
            ultima = chave
        time.sleep(30)


if __name__ == "__main__":
    main()
