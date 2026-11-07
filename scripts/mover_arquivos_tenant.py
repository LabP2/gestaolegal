"""Move os anexos privados para a pasta do tenant (multitenant, PR 8).

Até a multitenancy, os anexos ficavam em `<raiz>/<categoria>/<ref>`. Agora
ficam em `<raiz>/<tenant_id>/<categoria>/<ref>` (docs/plano-multitenant.md,
§8, decisão D9), e a API não lê mais o layout antigo: fallback seria o caminho
por onde um NPJ leria a pasta de outro. Todos os anexos de antes são da
DAJ/UFMG, o tenant 1.

O script só mexe no volume. O banco não muda: `caminho` e `link_arquivo`
continuam relativos à categoria, e é a API que acrescenta a pasta do tenant.

Cada arquivo é movido com `os.rename`, que é atômico e instantâneo dentro do
mesmo volume. Nada é copiado nem sobrescrito:

    movido      estava no layout antigo e foi para a pasta do tenant
    conflito    já existe um arquivo com o mesmo nome no destino; nada é feito
    ignorado    symlink no layout antigo; fica onde está (a API o recusaria)

Diretórios que ficam vazios no layout antigo são removidos. Rodar de novo não
move nada: é idempotente.

**Executar contra o volume de QA ou de produção é decisão humana.** A ordem
na implantação é: parar a API, rodar com `--dry-run`, conferir o relatório,
rodar sem `--dry-run`, subir a API nova. Com a API antiga no ar depois da
movimentação, os downloads dela falham; com a nova no ar antes, os dela.

Uso:
    uv run python scripts/mover_arquivos_tenant.py --raiz-privada /data/gestaolegal/uploads --dry-run
    uv run python scripts/mover_arquivos_tenant.py --raiz-privada /data/gestaolegal/uploads

O código de saída é o número de conflitos e erros (0 = tudo no lugar).
"""

import argparse
import os
import sys
from dataclasses import dataclass, field

# Mesmas categorias de `Config.PRIVATE_FILE_CATEGORIES`. Ficam aqui para o
# script não depender do `.env` (o `Config` exige variáveis no import).
CATEGORIAS = ("casos", "eventos", "arquivos")
TENANT_INICIAL_ID = 1


@dataclass
class Relatorio:
    movidos: list[str] = field(default_factory=list)
    conflitos: list[str] = field(default_factory=list)
    ignorados: list[str] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)

    @property
    def falhas(self) -> int:
        return len(self.conflitos) + len(self.erros)


def _arquivos(origem: str):
    """Caminhos relativos de tudo que está sob `origem`, sem seguir symlink."""
    for pasta, subpastas, nomes in os.walk(origem, followlinks=False):
        for nome in sorted(nomes) + sorted(
            s for s in subpastas if os.path.islink(os.path.join(pasta, s))
        ):
            yield os.path.relpath(os.path.join(pasta, nome), origem)


def _remover_vazios(origem: str) -> None:
    for pasta, _subpastas, _nomes in os.walk(origem, topdown=False):
        try:
            os.rmdir(pasta)
        except OSError:
            pass  # não está vazia: sobrou conflito ou symlink


def mover(raiz: str, tenant_id: int = TENANT_INICIAL_ID, dry_run: bool = False) -> Relatorio:
    raiz = os.path.realpath(raiz)
    if not os.path.isdir(raiz):
        raise SystemExit(f"Raiz privada não encontrada: {raiz}")
    relatorio = Relatorio()

    for categoria in CATEGORIAS:
        origem = os.path.join(raiz, categoria)
        destino = os.path.join(raiz, str(tenant_id), categoria)
        if os.path.islink(origem):
            relatorio.ignorados.append(f"{categoria} (a própria categoria é symlink)")
            continue
        if not os.path.isdir(origem):
            continue

        for rel in _arquivos(origem):
            de = os.path.join(origem, rel)
            para = os.path.join(destino, rel)
            rotulo = f"{categoria}/{rel}"
            if os.path.islink(de):
                relatorio.ignorados.append(rotulo)
            elif os.path.lexists(para):
                relatorio.conflitos.append(rotulo)
            elif dry_run:
                relatorio.movidos.append(rotulo)
            else:
                try:
                    os.makedirs(os.path.dirname(para), exist_ok=True)
                    os.rename(de, para)
                    relatorio.movidos.append(rotulo)
                except OSError as e:
                    relatorio.erros.append(f"{rotulo}: {e}")

        if not dry_run:
            _remover_vazios(origem)

    return relatorio


def _imprimir(relatorio: Relatorio, dry_run: bool) -> None:
    verbo = "a mover" if dry_run else "movidos"
    print(f"{verbo}: {len(relatorio.movidos)}")
    for grupo, itens in (
        ("conflitos (destino já existe; nada feito)", relatorio.conflitos),
        ("ignorados (symlink)", relatorio.ignorados),
        ("erros", relatorio.erros),
    ):
        print(f"{grupo}: {len(itens)}")
        for item in itens:
            print(f"  {item}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--raiz-privada",
        default=os.environ.get("PRIVATE_FILES_ROOT", "/data/gestaolegal/uploads"),
        help="Raiz dos anexos (padrão: PRIVATE_FILES_ROOT).",
    )
    parser.add_argument(
        "--tenant-id", type=int, default=TENANT_INICIAL_ID,
        help="Tenant dono dos anexos do layout antigo (padrão: 1, DAJ/UFMG).",
    )
    parser.add_argument(
        "--dry-run", "--check", action="store_true", dest="dry_run",
        help="Só relata o que faria; não move nada.",
    )
    args = parser.parse_args(argv)
    if args.tenant_id < 1:
        parser.error("--tenant-id precisa ser positivo")

    relatorio = mover(args.raiz_privada, args.tenant_id, args.dry_run)
    _imprimir(relatorio, args.dry_run)
    return relatorio.falhas


if __name__ == "__main__":
    sys.exit(main())
