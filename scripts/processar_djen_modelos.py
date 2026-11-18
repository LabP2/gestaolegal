"""Fila de treino e inferência limitada por lote. Não consulta a API do DJEN.

Cada execução usa um subprocesso com prazo de 10 min (treino) / 60 s (inferência).
Pedidos sobrevivem a reinícios; execuções abandonadas viram erro após 15 min.
"""

import argparse
import logging
import subprocess
import sys
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def executar_item(app, tenant, cid, unidade, token=None):
    from gestaolegal.services.djen_contexto_service import DjenContextoService
    from gestaolegal.utils.request_context import contexto_tenant

    with app.test_request_context(), contexto_tenant(tenant):
        servico = DjenContextoService()
        if token:
            return servico.executar_treino(cid, unidade, token)
        return servico.processar_previsoes(cid, unidade)


def ciclo(app, executar=subprocess.run):
    from gestaolegal.repositories.tenant_repository import TenantRepository
    from gestaolegal.services.djen_contexto_service import DjenContextoService
    from gestaolegal.utils.request_context import contexto_tenant, sem_tenant

    with app.test_request_context(), sem_tenant("worker de modelos: NPJs habilitados"):
        tenants = TenantRepository().listar_para_djen()
    for tenant in tenants:
        if not tenant.ativo or not tenant.djen_ativo:
            continue
        with app.test_request_context(), contexto_tenant(tenant.id):
            contextos = DjenContextoService().contextos_do_worker()
        for ctx in contextos:
            cid, unidade, token = ctx["id"], ctx["unidade_id"], ctx["treino_token"]
            if ctx["treino_status"] == "executando":
                if ctx["treino_iniciado_em"] < datetime.now() - timedelta(minutes=15):
                    with app.test_request_context(), contexto_tenant(tenant.id):
                        DjenContextoService().falhar_treino(
                            cid,
                            token,
                            "Execução interrompida. Solicite o treino novamente.",
                        )
                continue
            comando = [
                sys.executable,
                "-m",
                "scripts.processar_djen_modelos",
                "--tenant",
                str(tenant.id),
                "--contexto",
                str(cid),
                "--unidade",
                str(unidade),
            ]
            treino = ctx["treino_status"] == "na_fila"
            if treino:
                comando += ["--token", token]
            else:
                with app.test_request_context(), contexto_tenant(tenant.id):
                    s = DjenContextoService()
                    modelo = s.ultimo_modelo(cid)
                    if not modelo or not s.lote_previsoes(cid, modelo["id"], limite=1):
                        continue
            try:
                executar(comando, check=True, timeout=600 if treino else 60)
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
                logger.exception("Worker de modelos: falha no contexto %s", cid)
                if treino:
                    with app.test_request_context(), contexto_tenant(tenant.id):
                        DjenContextoService().falhar_treino(
                            cid,
                            token,
                            "Treino interrompido ou excedeu o limite de 10 minutos. Solicite novamente.",
                        )


def main():
    from gestaolegal import create_app

    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", type=int)
    parser.add_argument("--contexto", type=int)
    parser.add_argument("--unidade", type=int)
    parser.add_argument("--token")
    args = parser.parse_args()
    app = create_app()
    if args.tenant is not None:
        if args.contexto is None or args.unidade is None:
            parser.error("--contexto e --unidade são obrigatórios")
        executar_item(app, args.tenant, args.contexto, args.unidade, args.token)
        return
    while True:
        try:
            ciclo(app)
        except Exception:
            logger.exception("Ciclo de modelos falhou; nova tentativa em 15 segundos")
        time.sleep(15)


if __name__ == "__main__":
    main()
