"""Cliente da API pública do DJEN (Comunica PJe).

`GET {DJEN_API_URL}/api/v1/comunicacao?<filtros>` — sem autenticação, sem
contrato documentado (docs/plano-djen.md, §1). O cliente:

- usa `urllib.request` da biblioteca padrão, atrás de uma função de transporte
  que os testes substituem (nenhum teste fala com a rede);
- pagina, com timeout de 30 s e `User-Agent` do sistema;
- respeita o limite de taxa: espera quando `x-ratelimit-remaining` ≤ 1 e reage
  a 429 com backoff;
- devolve dataclasses e nunca toca no banco.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

URL_PADRAO = "https://comunicaapi.pje.jus.br"
CAMINHO = "/api/v1/comunicacao"
USER_AGENT = "GestaoLegal/3.0 (+integracao DJEN)"
TIMEOUT_S = 30.0
ITENS_POR_PAGINA = 100
MAX_PAGINAS = 50
MAX_TENTATIVAS = 4
# O contador do limite voltou ao máximo em menos de um minuto (plano, §1).
ESPERA_LIMITE_S = 60.0
BACKOFF_429_S = 15.0


class DJENError(RuntimeError):
    """Falha de rede, resposta inesperada ou limite de taxa esgotado."""


@dataclass
class RespostaHTTP:
    status: int
    headers: Mapping[str, str]
    corpo: bytes


# (url, timeout) -> resposta. Erros de rede levantam DJENError.
Transporte = Callable[[str, float], RespostaHTTP]


def transporte_urllib(url: str, timeout: float) -> RespostaHTTP:
    requisicao = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:  # noqa: S310
            return RespostaHTTP(
                resposta.status, {k.lower(): v for k, v in resposta.headers.items()},
                resposta.read(),
            )
    except urllib.error.HTTPError as erro:
        return RespostaHTTP(
            erro.code, {k.lower(): v for k, v in (erro.headers or {}).items()},
            erro.read() or b"",
        )
    except (urllib.error.URLError, TimeoutError, OSError) as erro:
        raise DJENError(f"Falha de rede ao consultar o DJEN: {erro}") from erro


# Pontos de substituição para os testes (conftest troca por um transporte que
# falha, para que nenhum teste chegue à rede por engano).
_transporte: Transporte = transporte_urllib
_dormir: Callable[[float], None] = time.sleep


def definir_transporte(transporte: Transporte | None) -> None:
    global _transporte
    _transporte = transporte or transporte_urllib


def definir_dormir(dormir: Callable[[float], None] | None) -> None:
    global _dormir
    _dormir = dormir or time.sleep


@dataclass
class Comunicacao:
    """Uma publicação do DJEN, com os campos que o sistema usa (plano, §1)."""

    id_djen: int
    numero_processo: str
    data_disponibilizacao: date
    hash: str | None = None
    numero_processo_mascara: str | None = None
    sigla_tribunal: str | None = None
    nome_orgao: str | None = None
    tipo_comunicacao: str | None = None
    tipo_documento: str | None = None
    nome_classe: str | None = None
    texto: str | None = None
    link: str | None = None
    destinatarios: list[dict[str, Any]] = field(default_factory=list)
    advogados: list[dict[str, Any]] = field(default_factory=list)
    ativo: bool = True
    motivo_cancelamento: str | None = None


def _texto(valor: Any, limite: int | None = None) -> str | None:
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    return texto[:limite] if limite else texto


def converter_item(item: Mapping[str, Any]) -> Comunicacao:
    """Item cru da API -> Comunicacao. Levanta DJENError se faltar o essencial."""
    try:
        id_djen = int(item["id"])
        numero = "".join(ch for ch in str(item.get("numero_processo") or "") if ch.isdigit())
        data_disp = date.fromisoformat(str(item["data_disponibilizacao"])[:10])
    except (KeyError, TypeError, ValueError) as erro:
        raise DJENError(f"Item do DJEN com formato inesperado: {erro}") from erro
    if not numero:
        raise DJENError(f"Item {id_djen} do DJEN sem número de processo")

    destinatarios = [
        {"nome": _texto(d.get("nome"), 300), "polo": _texto(d.get("polo"), 2)}
        for d in item.get("destinatarios") or []
        if isinstance(d, Mapping)
    ]
    advogados = []
    for registro in item.get("destinatarioadvogados") or []:
        advogado = registro.get("advogado") if isinstance(registro, Mapping) else None
        if not isinstance(advogado, Mapping):
            continue
        advogados.append(
            {
                "nome": _texto(advogado.get("nome"), 300),
                "numero_oab": _texto(advogado.get("numero_oab"), 20),
                "uf_oab": _texto(advogado.get("uf_oab"), 2),
            }
        )
    ativo = item.get("ativo")
    return Comunicacao(
        id_djen=id_djen,
        numero_processo=numero[:20],
        data_disponibilizacao=data_disp,
        hash=_texto(item.get("hash"), 100),
        numero_processo_mascara=_texto(item.get("numeroprocessocommascara"), 30),
        sigla_tribunal=_texto(item.get("siglaTribunal"), 30),
        nome_orgao=_texto(item.get("nomeOrgao"), 300),
        tipo_comunicacao=_texto(item.get("tipoComunicacao"), 100),
        tipo_documento=_texto(item.get("tipoDocumento"), 100),
        nome_classe=_texto(item.get("nomeClasse"), 300),
        texto=item.get("texto") if isinstance(item.get("texto"), str) else None,
        link=_texto(item.get("link"), 1000),
        destinatarios=destinatarios,
        advogados=advogados,
        ativo=True if ativo is None else bool(ativo),
        motivo_cancelamento=_texto(item.get("motivo_cancelamento")),
    )


class DJENClient:
    def __init__(
        self,
        base_url: str | None = None,
        transporte: Transporte | None = None,
        dormir: Callable[[float], None] | None = None,
        itens_por_pagina: int = ITENS_POR_PAGINA,
        max_paginas: int = MAX_PAGINAS,
        max_tentativas: int = MAX_TENTATIVAS,
    ):
        self.base_url = (base_url or URL_PADRAO).rstrip("/")
        self._transporte = transporte
        self._dormir = dormir
        self.itens_por_pagina = itens_por_pagina
        self.max_paginas = max_paginas
        self.max_tentativas = max_tentativas
        # Quantas requisições foram feitas (para log e testes).
        self.requisicoes = 0

    # --- consultas -----------------------------------------------------------

    def buscar_por_processo(self, numero_cnj: str) -> list[Comunicacao]:
        """Histórico completo do processo (não precisa de datas)."""
        return self._paginar({"numeroProcesso": numero_cnj})

    def buscar_por_oab(
        self, numero_oab: str, uf_oab: str, inicio: date, fim: date
    ) -> list[Comunicacao]:
        return self._paginar(
            {
                "numeroOab": numero_oab,
                "ufOab": uf_oab.upper(),
                "dataDisponibilizacaoInicio": inicio.isoformat(),
                "dataDisponibilizacaoFim": fim.isoformat(),
            }
        )

    # --- infraestrutura ------------------------------------------------------

    def _paginar(self, filtros: dict[str, str]) -> list[Comunicacao]:
        itens: list[Comunicacao] = []
        vistos: set[int] = set()
        for pagina in range(1, self.max_paginas + 1):
            corpo = self._get({**filtros, "pagina": str(pagina),
                               "itensPorPagina": str(self.itens_por_pagina)})
            brutos = corpo.get("items") or []
            if not isinstance(brutos, list):
                raise DJENError("Resposta do DJEN sem lista de itens")
            for bruto in brutos:
                comunicacao = converter_item(bruto)
                if comunicacao.id_djen not in vistos:
                    vistos.add(comunicacao.id_djen)
                    itens.append(comunicacao)
            total = corpo.get("count")
            if len(brutos) < self.itens_por_pagina:
                break
            if isinstance(total, int) and pagina * self.itens_por_pagina >= total:
                break
        else:
            logger.warning(f"DJEN: consulta parou no limite de {self.max_paginas} páginas")
        return itens

    def _get(self, params: dict[str, str]) -> dict[str, Any]:
        url = f"{self.base_url}{CAMINHO}?{urllib.parse.urlencode(params)}"
        transporte = self._transporte or _transporte
        dormir = self._dormir or _dormir
        for tentativa in range(1, self.max_tentativas + 1):
            self.requisicoes += 1
            resposta = transporte(url, TIMEOUT_S)
            if resposta.status == 429:
                espera = _retry_after(resposta.headers) or BACKOFF_429_S * tentativa
                logger.warning(f"DJEN: 429 (tentativa {tentativa}); aguardando {espera:.0f}s")
                if tentativa < self.max_tentativas:
                    dormir(espera)
                continue
            if resposta.status >= 500:
                logger.warning(f"DJEN: erro {resposta.status} (tentativa {tentativa})")
                if tentativa < self.max_tentativas:
                    dormir(BACKOFF_429_S * tentativa)
                continue
            if resposta.status != 200:
                raise DJENError(f"DJEN respondeu {resposta.status}")
            self._respeitar_limite(resposta.headers, dormir)
            try:
                corpo = json.loads(resposta.corpo.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as erro:
                raise DJENError("Resposta do DJEN não é JSON") from erro
            if not isinstance(corpo, dict):
                raise DJENError("Resposta do DJEN com formato inesperado")
            return corpo
        raise DJENError(f"DJEN indisponível depois de {self.max_tentativas} tentativas")

    @staticmethod
    def _respeitar_limite(headers: Mapping[str, str], dormir: Callable[[float], None]) -> None:
        restante = _inteiro(headers.get("x-ratelimit-remaining"))
        if restante is not None and restante <= 1:
            logger.info(f"DJEN: limite de taxa quase no fim; aguardando {ESPERA_LIMITE_S:.0f}s")
            dormir(ESPERA_LIMITE_S)


def _inteiro(valor: str | None) -> int | None:
    try:
        return int(str(valor).strip()) if valor is not None else None
    except ValueError:
        return None


def _retry_after(headers: Mapping[str, str]) -> float | None:
    segundos = _inteiro(headers.get("retry-after"))
    return float(min(segundos, 300)) if segundos is not None and segundos >= 0 else None
