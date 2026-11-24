"""DJEN fictício do ambiente de demonstração (`DEMO_MODE=true`).

Na demo pública, o cliente do DJEN usa este transporte no lugar da rede: nada
sai para a API real, e nenhuma publicação verdadeira (com nomes de partes)
entra num ambiente em que qualquer visitante faz login.

- Processo com CNJ de demonstração (segmento de justiça 0, que não existe):
  devolve um histórico fixo de publicações inventadas, de uma intimação até a
  sentença.
- OAB de demonstração (número iniciado por 9900): devolve publicações dentro
  da janela consultada, de um processo que não está cadastrado. Elas caem em
  "Publicações sem caso", para o visitante ver a triagem.
- Qualquer outra consulta (CNJ ou OAB reais, nome de parte): resposta vazia,
  sem erro.

Os identificadores são derivados do número consultado, então repetir a busca
não duplica publicações.
"""

from __future__ import annotations

import json
import urllib.parse
import zlib
from datetime import date, timedelta

from gestaolegal.integrations.djen_client import RespostaHTTP
from gestaolegal.utils.tempo import hoje_brasilia

# Faixa alta, longe dos ids reais do DJEN.
BASE_ID = 9_000_000_000_000
PREFIXO_OAB_DEMO = "9900"
TRIBUNAL = "DEMO"
ORGAO = "1ª Vara Cível da Comarca de Demonstração"
CLASSE = "PROCEDIMENTO COMUM CÍVEL"
AVISO = "Texto fictício, gerado pelo ambiente de demonstração do Gestão Legal."

# (dias antes de hoje, tipo de comunicação, tipo de documento, texto)
HISTORICO_PROCESSO = (
    (
        45,
        "Intimação",
        "Despacho",
        "Intime-se a parte autora para, no prazo de 15 (quinze) dias, emendar a "
        "petição inicial, juntando comprovante de residência atualizado.",
    ),
    (
        25,
        "Intimação",
        "Decisão",
        "Designo audiência de conciliação para o dia {audiencia}, às 14h, a "
        "realizar-se por videoconferência. Intimem-se as partes.",
    ),
    (
        4,
        "Intimação",
        "Sentença",
        "Ante o exposto, JULGO PROCEDENTE o pedido inicial, extinguindo o processo "
        "com resolução do mérito, nos termos do art. 487, I, do CPC. Sem custas, "
        "em razão da gratuidade de justiça. Publique-se. Intimem-se.",
    ),
)

# (dias antes do fim da janela, tipo de documento, texto)
PUBLICACOES_OAB = (
    (
        1,
        "Despacho",
        "Manifeste-se a parte ré sobre a contestação, no prazo legal.",
    ),
    (
        3,
        "Ato ordinatório",
        "Fica a advogada intimada a recolher as custas iniciais ou comprovar o "
        "pedido de gratuidade de justiça.",
    ),
)


def cnj_de_demonstracao(numero: str) -> bool:
    """CNJ de 20 dígitos com o segmento de justiça (J) igual a 0."""
    return len(numero) == 20 and numero.isdigit() and numero[13] == "0"


def _mascara(numero: str) -> str:
    n = numero
    return f"{n[:7]}-{n[7:9]}.{n[9:13]}.{n[13]}.{n[14:16]}.{n[16:]}"


def _id(chave: str, indice: int) -> int:
    return BASE_ID + zlib.crc32(chave.encode()) * 10 + indice


def _cnj_da_oab(numero_oab: str) -> str:
    """Processo fictício, não cadastrado, de onde vêm as publicações da OAB."""
    sequencial = f"{zlib.crc32(numero_oab.encode()) % 10_000_000:07d}"
    ano = str(hoje_brasilia().year)
    base = int(f"{sequencial}{ano}0130001")
    digito = 98 - (base * 100) % 97
    return f"{sequencial}{digito:02d}{ano}0130001"


def _item(
    id_djen: int,
    numero: str,
    data: date,
    tipo_comunicacao: str,
    tipo_documento: str,
    texto: str,
    advogado: tuple[str, str] | None,
) -> dict:
    advogados = []
    if advogado:
        advogados.append(
            {
                "advogado": {
                    "nome": "Advogada de Demonstração",
                    "numero_oab": advogado[0],
                    "uf_oab": advogado[1],
                }
            }
        )
    return {
        "id": id_djen,
        "hash": f"demo-{id_djen}",
        "numero_processo": numero,
        "numeroprocessocommascara": _mascara(numero),
        "data_disponibilizacao": data.isoformat(),
        "siglaTribunal": TRIBUNAL,
        "nomeOrgao": ORGAO,
        "tipoComunicacao": tipo_comunicacao,
        "tipoDocumento": tipo_documento,
        "nomeClasse": CLASSE,
        "texto": f"<p>{texto}</p><p><em>{AVISO}</em></p>",
        "link": None,
        "destinatarios": [
            {"nome": "PARTE AUTORA DE DEMONSTRAÇÃO", "polo": "A"},
            {"nome": "PARTE RÉ DE DEMONSTRAÇÃO", "polo": "P"},
        ],
        "destinatarioadvogados": advogados,
        "ativo": True,
    }


def publicacoes_do_processo(numero: str, hoje: date | None = None) -> list[dict]:
    if not cnj_de_demonstracao(numero):
        return []
    hoje = hoje or hoje_brasilia()
    audiencia = (hoje + timedelta(days=20)).strftime("%d/%m/%Y")
    return [
        _item(
            _id(numero, i),
            numero,
            hoje - timedelta(days=dias),
            tipo_com,
            tipo_doc,
            texto.format(audiencia=audiencia),
            None,
        )
        for i, (dias, tipo_com, tipo_doc, texto) in enumerate(HISTORICO_PROCESSO)
    ]


def publicacoes_da_oab(
    numero_oab: str, uf: str, inicio: date | None, fim: date | None
) -> list[dict]:
    if not numero_oab.startswith(PREFIXO_OAB_DEMO):
        return []
    fim = fim or hoje_brasilia()
    numero = _cnj_da_oab(numero_oab)
    itens = []
    for i, (dias, tipo_doc, texto) in enumerate(PUBLICACOES_OAB):
        data = fim - timedelta(days=dias)
        if inicio is not None and data < inicio:
            continue
        itens.append(
            _item(
                _id(f"oab:{numero_oab}", i),
                numero,
                data,
                "Intimação",
                tipo_doc,
                texto,
                (numero_oab, uf.upper()),
            )
        )
    return itens


def _data(valor: str | None) -> date | None:
    try:
        return date.fromisoformat(valor) if valor else None
    except ValueError:
        return None


def transporte_demo(url: str, timeout: float) -> RespostaHTTP:
    """Transporte do `DJENClient` que responde sem acessar a rede."""
    params = {
        k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(url).query).items()
    }
    pagina = int(params.get("pagina", "1") or 1)
    itens: list[dict] = []
    if pagina == 1:
        if "numeroProcesso" in params:
            numero = "".join(c for c in params["numeroProcesso"] if c.isdigit())
            itens = publicacoes_do_processo(numero)
        elif "numeroOab" in params:
            itens = publicacoes_da_oab(
                params["numeroOab"],
                params.get("ufOab", ""),
                _data(params.get("dataDisponibilizacaoInicio")),
                _data(params.get("dataDisponibilizacaoFim")),
            )
        if "siglaTribunal" in params:
            itens = [i for i in itens if i["siglaTribunal"] == params["siglaTribunal"]]
    corpo = json.dumps({"status": "success", "count": len(itens), "items": itens})
    return RespostaHTTP(200, {"content-type": "application/json"}, corpo.encode())
