import json
from typing import Literal

from pydantic import Field, model_validator

from gestaolegal.models.base_model import BaseModel


class AssistidoPessoaJuridicaInput(BaseModel):
    enquadramento: Literal["mei", "microempresa", "pequeno_porte", "outros"]
    especificacao_enquadramento: str | None = Field(default=None, max_length=200)
    socios: list[str] = Field(default_factory=list, max_length=20)
    situacao_receita: Literal["Ativa", "Baixada", "Outras"] | None = None

    @model_validator(mode="after")
    def validar_dados_juridicos(self):
        if self.enquadramento == "outros":
            self.especificacao_enquadramento = (
                self.especificacao_enquadramento or ""
            ).strip()
            if not self.especificacao_enquadramento:
                raise ValueError("Especifique o enquadramento da PJ")
        else:
            self.especificacao_enquadramento = None
        if self.enquadramento == "mei":
            self.socios = []
        else:
            self.socios = [nome.strip() for nome in self.socios]
            if not self.socios or any(
                not nome or len(nome) > 80 for nome in self.socios
            ):
                raise ValueError(
                    "Informe os nomes dos sócios (até 80 caracteres por nome)"
                )
            if len(json.dumps(self.socios, ensure_ascii=False)) > 1000:
                raise ValueError(
                    "Os nomes dos sócios excedem o limite de 1000 caracteres"
                )
        return self


class AssistidoCreateInput(BaseModel):
    assistido_pessoa_juridica: AssistidoPessoaJuridicaInput | None = None
    sexo: str
    profissao: str
    raca: str
    rg: str
    grau_instrucao: str
    salario: float
    beneficio: str
    qual_beneficio: str | None = None
    contribui_inss: str
    qtd_pessoas_moradia: int
    renda_familiar: float
    participacao_renda: str
    tipo_moradia: str
    possui_outros_imoveis: bool
    quantos_imoveis: int | None = None
    possui_veiculos: bool
    possui_veiculos_obs: str | None = None
    quantos_veiculos: int | None = None
    ano_veiculo: str | None = None
    doenca_grave_familia: str
    pessoa_doente: str | None = None
    pessoa_doente_obs: str | None = None
    gastos_medicacao: float | None = None
    obs: str | None = None


class AssistidoUpdateInput(BaseModel):
    assistido_pessoa_juridica: AssistidoPessoaJuridicaInput | None = None
    sexo: str | None = None
    profissao: str | None = None
    raca: str | None = None
    rg: str | None = None
    grau_instrucao: str | None = None
    salario: float | None = None
    beneficio: str | None = None
    qual_beneficio: str | None = None
    contribui_inss: str | None = None
    qtd_pessoas_moradia: int | None = None
    renda_familiar: float | None = None
    participacao_renda: str | None = None
    tipo_moradia: str | None = None
    possui_outros_imoveis: bool | None = None
    quantos_imoveis: int | None = None
    possui_veiculos: bool | None = None
    possui_veiculos_obs: str | None = None
    quantos_veiculos: int | None = None
    ano_veiculo: str | None = None
    doenca_grave_familia: str | None = None
    pessoa_doente: str | None = None
    pessoa_doente_obs: str | None = None
    gastos_medicacao: float | None = None
    obs: str | None = None
