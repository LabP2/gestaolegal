from dataclasses import dataclass, field


@dataclass
class AssistidoPessoaJuridica:
    id_assistido: int
    enquadramento: str
    id: int | None = None
    especificacao_enquadramento: str | None = None
    socios: list[str] = field(default_factory=list)
    situacao_receita: str | None = None
    sede_bh: bool | None = None
    area_atuacao: str | None = None
    negocio_nascente: bool | None = None
    orgao_registro: str | None = None
    faturamento_anual: float | None = None
    tem_funcionarios: str | None = None
    regiao_sede_bh: str | None = None
    regiao_sede_outros: str | None = None
    ultimo_balanco_neg: str | None = None
    resultado_econ_neg: str | None = None
    qtd_funcionarios: str | None = None
