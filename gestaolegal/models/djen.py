"""Publicações do DJEN e o registro das sincronizações (docs/plano-djen.md)."""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

SituacaoComunicacao = Literal["vinculada", "pendente", "descartada"]
SITUACOES: tuple[str, ...] = ("vinculada", "pendente", "descartada")


@dataclass
class ComunicacaoDJEN:
    id: int
    id_djen: int
    numero_processo: str
    data_disponibilizacao: date
    situacao: str
    unidade_id: int
    capturada_em: datetime
    hash: str | None = None
    numero_processo_mascara: str | None = None
    sigla_tribunal: str | None = None
    nome_orgao: str | None = None
    tipo_comunicacao: str | None = None
    tipo_documento: str | None = None
    nome_classe: str | None = None
    texto_html: str | None = None
    texto_plano: str | None = None
    link: str | None = None
    destinatarios: list[dict[str, Any]] | None = None
    advogados: list[dict[str, Any]] | None = None
    ativo: bool = True
    motivo_cancelamento: str | None = None
    id_processo: int | None = None
    id_caso: int | None = None
    data_situacao: datetime | None = None
    oab_origem: str | None = None
    atualizada_em: datetime | None = None
    id_vinculado_por: int | None = None


@dataclass
class ComunicacaoListItem:
    """Linha da lista: sem o texto integral."""

    id: int
    data_disponibilizacao: date
    numero_processo: str
    situacao: str
    ativo: bool
    numero_processo_mascara: str | None = None
    sigla_tribunal: str | None = None
    nome_orgao: str | None = None
    tipo_comunicacao: str | None = None
    tipo_documento: str | None = None
    nome_classe: str | None = None
    id_processo: int | None = None
    id_caso: int | None = None
    oab_origem: str | None = None
    resumo: str | None = None


@dataclass
class SincronizacaoDJEN:
    id: int
    inicio: datetime
    status: str
    novas: int = 0
    atualizadas: int = 0
    vinculadas: int = 0
    fim: datetime | None = None
    parametros: dict[str, Any] | None = None
    mensagem: str | None = None


@dataclass
class ResultadoCaptura:
    """Contagem de uma captura (rotina ou botão)."""

    novas: int = 0
    atualizadas: int = 0
    vinculadas: int = 0
    erros: list[str] = field(default_factory=list)

    def somar(self, outro: "ResultadoCaptura") -> None:
        self.novas += outro.novas
        self.atualizadas += outro.atualizadas
        self.vinculadas += outro.vinculadas
        self.erros.extend(outro.erros)


@dataclass
class OabMonitorada:
    """Linha de `djen_oabs`: uma OAB que a rotina consulta no DJEN."""

    id: int
    numero_oab: str
    uf_oab: str
    ativo: bool
    unidade_id: int
    criado_em: datetime
    id_usuario: int | None = None
    id_criado_por: int | None = None
    usuario_nome: str | None = None
    unidade_nome: str | None = None

    @property
    def rotulo(self) -> str:
        return f"{self.numero_oab}/{self.uf_oab}"
