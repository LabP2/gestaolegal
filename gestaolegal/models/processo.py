from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gestaolegal.models.caso import Caso
    from gestaolegal.models.user import UserInfo


@dataclass
class Processo:
    especie: str
    id_caso: int | None
    status: bool
    id_criado_por: int

    id: int | None = None
    numero: str | None = None
    identificacao: str | None = None
    vara: str | None = None
    link: str | None = None
    probabilidade: str | None = None
    posicao_assistido: str | None = None
    valor_causa_inicial: float | None = None
    valor_causa_atual: float | None = None
    data_distribuicao: date | None = None
    data_transito_em_julgado: date | None = None
    obs: str | None = None
    numero_cnj: str | None = None
    djen_pendente: bool = False
    djen_consultado_em: datetime | None = None
    unidade_id: int | None = None
    caso: "Caso | None" = None
    criado_por: "UserInfo | None" = None


@dataclass
class ParteProcesso:
    """Parte de um processo: de `processo_partes` ou, no processo de caso, do
    caso (`casos_atendidos`, sem polo)."""

    id_atendido: int
    nome: str
    origem: str  # processo | caso
    polo: str | None = None
    sem_triagem: bool = False
    id: int | None = None  # linha de `processo_partes`


@dataclass
class ProcessoListItem:
    """Linha de `GET /api/processos`."""

    id: int
    especie: str
    status: bool
    unidade_id: int
    id_caso: int | None = None
    numero: str | None = None
    numero_cnj: str | None = None
    identificacao: str | None = None
    vara: str | None = None
    data_distribuicao: date | None = None
    partes: list[str] | None = None
    total_publicacoes: int = 0
