from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from pydantic import Field, field_validator

from gestaolegal.models.base_model import BaseModel

if TYPE_CHECKING:
    pass


class ProcessoNumeroInput(BaseModel):
    numero: str | None = Field(default=None, max_length=25)

    @field_validator("numero", mode="before")
    @classmethod
    def normalizar_numero(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value


class ProcessoCreateInput(ProcessoNumeroInput):
    especie: str
    identificacao: str | None = None
    vara: str | None = None
    link: str | None = None
    probabilidade: str | None = None
    posicao_assistido: str | None = None
    valor_causa_inicial: Decimal | None = Field(
        default=None, max_digits=15, decimal_places=2
    )
    valor_causa_atual: Decimal | None = Field(
        default=None, max_digits=15, decimal_places=2
    )
    data_distribuicao: date | None = None
    data_transito_em_julgado: date | None = None
    obs: str | None = None
    id_caso: int | None = None
    status: bool = True


class ProcessoUpdateInput(ProcessoNumeroInput):
    especie: str | None = None
    identificacao: str | None = None
    vara: str | None = None
    link: str | None = None
    probabilidade: str | None = None
    posicao_assistido: str | None = None
    valor_causa_inicial: Decimal | None = Field(
        default=None, max_digits=15, decimal_places=2
    )
    valor_causa_atual: Decimal | None = Field(
        default=None, max_digits=15, decimal_places=2
    )
    data_distribuicao: date | None = None
    data_transito_em_julgado: date | None = None
    obs: str | None = None
    id_caso: int | None = None
    status: bool | None = None


class ParteInput(BaseModel):
    id_atendido: int
    polo: Literal["ativo", "passivo", "outro"] | None = None


class ProcessoSemCasoInput(ProcessoCreateInput):
    """`POST /api/processos`: processo sem caso, com ao menos uma parte."""

    partes: list[ParteInput] = Field(min_length=1)

    @field_validator("id_caso")
    @classmethod
    def sem_caso(cls, value: int | None) -> int | None:
        if value is not None:
            raise ValueError("Processo sem caso não recebe id_caso")
        return value


class ProcessoDjenInput(ProcessoSemCasoInput):
    """Importação explícita do DJEN permite identificar as partes posteriormente."""

    partes: list[ParteInput] = Field(default_factory=list)
