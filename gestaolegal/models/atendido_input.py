from dataclasses import dataclass
from datetime import date

from pydantic import Field, field_validator

from gestaolegal.models.base_model import BaseModel
from gestaolegal.models.endereco import Endereco


@dataclass
class ListAtendido:
    id: int
    nome: str
    cpf: str | None
    telefone: str | None
    celular: str | None
    email: str | None
    data_nascimento: date | None
    status: bool
    is_assistido: bool
    sem_triagem: bool

    endereco: Endereco | None


class AtendidoCreateInput(BaseModel):
    nome: str
    data_nascimento: date
    cpf: str
    cnpj: str | None = None
    telefone: str | None = None
    celular: str
    email: str = ""
    estado_civil: str
    como_conheceu: str
    indicacao_orgao: str | None = None
    procurou_outro_local: str
    procurou_qual_local: str | None = None
    obs: str | None = None
    pj_constituida: str
    repres_legal: bool | None = None
    nome_repres_legal: str | None = None
    cpf_repres_legal: str | None = None
    contato_repres_legal: str | None = None
    rg_repres_legal: str | None = None
    nascimento_repres_legal: date | None = None
    pretende_constituir_pj: str | None = None

    logradouro: str
    numero: str
    complemento: str | None = None
    bairro: str
    cep: str
    cidade: str
    estado: str


class AtendidoUpdateInput(BaseModel):
    nome: str | None = None
    data_nascimento: date | None = None
    cpf: str | None = None
    cnpj: str | None = None
    telefone: str | None = None
    celular: str | None = None
    email: str | None = None
    estado_civil: str | None = None
    como_conheceu: str | None = None
    indicacao_orgao: str | None = None
    procurou_outro_local: str | None = None
    procurou_qual_local: str | None = None
    obs: str | None = None
    pj_constituida: str | None = None
    repres_legal: bool | None = None
    nome_repres_legal: str | None = None
    cpf_repres_legal: str | None = None
    contato_repres_legal: str | None = None
    rg_repres_legal: str | None = None
    nascimento_repres_legal: date | None = None
    pretende_constituir_pj: str | None = None

    logradouro: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    cep: str | None = None
    cidade: str | None = None
    estado: str | None = None


class AtendidoSimplificadoInput(BaseModel):
    """Parte cadastrada sem triagem (processo sem caso): só nome, documento e
    observação. Marca `sem_triagem`."""

    nome: str = Field(min_length=1, max_length=80)
    cpf: str | None = Field(default=None, max_length=14)
    cnpj: str | None = Field(default=None, max_length=18)
    obs: str | None = None

    @field_validator("nome", "cpf", "cnpj", "obs", mode="before")
    @classmethod
    def aparar(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value
