"""Respostas sintéticas da API do DJEN para os testes.

Montadas a partir da estrutura real (docs/plano-djen.md, §1), com nomes,
números e órgãos inventados. Nenhum teste fala com a rede.
"""

import json
from collections.abc import Callable
from urllib.parse import parse_qs, urlparse

from sqlalchemy import update

from gestaolegal.database import session as db_session_module
from gestaolegal.database.tables import (
    djen_comunicacoes,
    djen_sincronizacoes,
    eventos,
    metadata,
    notificacao,
    processos,
    tenants,
)
from gestaolegal.integrations.djen_client import DJENError, RespostaHTTP
from gestaolegal.utils.cnj import mascarar_cnj
from gestaolegal.utils.request_context import sem_tenant

HTML_PUBLICACAO = (
    "<!DOCTYPE html><html><head><style>body{font-family:Comic Sans}</style>"
    "<title>Intimação</title></head><body>"
    "<p>Fica a parte <b>intimada</b> do despacho: &ccedil;&atilde;o.</p>"
    '<p onclick="alert(1)">Prazo de 15 dias.</p>'
    '<img src="x" onerror="alert(2)"><a href="javascript:alert(3)">link</a>'
    "<script>alert(4)</script></body></html>"
)


def item_djen(
    id_djen: int,
    numero: str,
    data: str = "2026-11-03",
    texto: str = HTML_PUBLICACAO,
    ativo: bool = True,
    oab: tuple[str, str] = ("123456", "MG"),
    tipo: str = "Intimação",
    tribunal: str = "TJMG",
    motivo_cancelamento: str | None = None,
) -> dict:
    return {
        "id": id_djen,
        "data_disponibilizacao": data,
        "siglaTribunal": tribunal,
        "tipoComunicacao": tipo,
        "nomeOrgao": "1ª Vara Cível da Comarca Fictícia",
        "idOrgao": 999,
        "texto": texto,
        "numero_processo": numero,
        "meio": "D",
        "link": f"https://tribunal.exemplo.invalid/documento/{id_djen}",
        "tipoDocumento": "Despacho",
        "nomeClasse": "Procedimento Comum Cível",
        "codigoClasse": "7",
        "numeroComunicacao": 1,
        "ativo": ativo,
        "hash": f"hashficticio{id_djen}",
        "status": "P" if ativo else "C",
        "motivo_cancelamento": motivo_cancelamento,
        "data_cancelamento": None,
        "datadisponibilizacao": "03/11/2026",
        "meiocompleto": "Diário de Justiça Eletrônico Nacional",
        "numeroprocessocommascara": mascarar_cnj(numero),
        "destinatarios": [
            {"comunicacao_id": id_djen, "nome": "Fulana de Tal Fictícia", "polo": "A"},
            {"comunicacao_id": id_djen, "nome": "Empresa Imaginária Ltda", "polo": "P"},
        ],
        "destinatarioadvogados": [
            {
                "id": 1,
                "comunicacao_id": id_djen,
                "advogado_id": 1,
                "created_at": "2026-11-03 00:00:00",
                "updated_at": "2026-11-03 00:00:00",
                "advogado": {
                    "id": 1,
                    "nome": "Advogada Fictícia",
                    "numero_oab": oab[0],
                    "uf_oab": oab[1],
                },
            }
        ],
    }


def resposta(itens: list[dict], status: int = 200, restante: int = 19, count: int | None = None):
    corpo = {
        "status": "success",
        "message": "Sucesso",
        "count": len(itens) if count is None else count,
        "items": itens,
    }
    return RespostaHTTP(
        status,
        {"x-ratelimit-limit": "20", "x-ratelimit-remaining": str(restante)},
        json.dumps(corpo).encode(),
    )


class TransporteFalso:
    """Responde por filtro: número do processo ou OAB. Registra as chamadas."""

    def __init__(self) -> None:
        self.por_processo: dict[str, list[dict]] = {}
        self.por_oab: dict[tuple[str, str], list[dict]] = {}
        # Busca manual por parte: nome exato -> itens.
        self.por_parte: dict[str, list[dict]] = {}
        self.falhar: set[str] = set()  # números ou "numero/UF" que dão erro de rede
        self.chamadas: list[dict[str, str]] = []
        self.extra: Callable[[dict[str, str]], RespostaHTTP | None] | None = None

    def __call__(self, url: str, timeout: float) -> RespostaHTTP:
        params = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        self.chamadas.append(params)
        if self.extra:
            r = self.extra(params)
            if r is not None:
                return r
        if "numeroProcesso" in params:
            chave = params["numeroProcesso"]
            if chave in self.falhar:
                raise DJENError("rede indisponível (simulado)")
            return resposta(self.por_processo.get(chave, []))
        if "numeroOab" in params:
            chave = f"{params['numeroOab']}/{params['ufOab']}"
            if chave in self.falhar:
                raise DJENError("rede indisponível (simulado)")
            return resposta(self.por_oab.get((params["numeroOab"], params["ufOab"]), []))
        if "nomeParte" in params:
            if params["nomeParte"] in self.falhar:
                raise DJENError("rede indisponível (simulado)")
            itens = self.por_parte.get(params["nomeParte"], [])
            if "siglaTribunal" in params:
                itens = [i for i in itens if i["siglaTribunal"] == params["siglaTribunal"]]
            return resposta(itens)
        return resposta([])


def ligar_djen(tenant_id: int, ligado: bool = True) -> None:
    session = db_session_module.get_session()
    try:
        with sem_tenant("teste: chave do DJEN"):
            session.execute(
                update(tenants).where(tenants.c.id == tenant_id).values(djen_ativo=ligado)
            )
            session.commit()
    finally:
        session.close()


def limpar_djen() -> None:
    """Apaga o que os testes do DJEN gravaram e desliga a chave."""
    session = db_session_module.get_session()
    try:
        with sem_tenant("teste: limpeza do DJEN"):
            session.execute(
                notificacao.delete().where(notificacao.c.tipo == "djen")
            )
            if "origem" in eventos.c:
                ids = [
                    r[0]
                    for r in session.execute(
                        eventos.select()
                        .with_only_columns(eventos.c.id)
                        .where(eventos.c.origem == "djen")
                    )
                ]
                if ids:
                    arquivos = metadata.tables["arquivosEvento"]
                    session.execute(arquivos.delete().where(arquivos.c.id_evento.in_(ids)))
                    session.execute(eventos.delete().where(eventos.c.id.in_(ids)))
            if "djen_oabs" in metadata.tables:
                session.execute(metadata.tables["djen_oabs"].delete())
            if "djen_exemplos" in metadata.tables:
                session.execute(metadata.tables["djen_exemplos"].delete())
            session.execute(djen_comunicacoes.delete())
            for nome in ('djen_contexto_historico', 'djen_publicacao_contextos', 'djen_modelos', 'djen_contextos', 'djen_monitoramentos', 'djen_publicacao_unidades', 'djen_consulta_resultados', 'djen_consultas', 'djen_classificacao_historico', 'djen_classificacoes', 'djen_publicacoes'):
                session.execute(metadata.tables[nome].delete())
            session.execute(djen_sincronizacoes.delete())
            session.execute(update(tenants).values(djen_ativo=False))
            # Processos de outros testes não podem ocupar a fila da rotina.
            session.execute(update(processos).values(djen_pendente=False))
            session.commit()
    finally:
        session.close()
