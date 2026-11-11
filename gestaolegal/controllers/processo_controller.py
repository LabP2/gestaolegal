"""Lista geral de processos e processo sem caso (docs/plano-processos-avulsos.md).

Montado em `/api/processos`. As rotas de processo dentro do caso continuam em
`/api/caso/<id>/processos`; estas valem para os dois tipos e filtram pela
unidade do processo (`processos.unidade_id`).
"""

from datetime import date
from typing import Any

from flask import Blueprint, request

from gestaolegal.common import PageParams
from gestaolegal.exceptions import ValidationException
from gestaolegal.models.processo_input import (
    ParteInput,
    ProcessoSemCasoInput,
    ProcessoUpdateInput,
)
from gestaolegal.services.processo_service import (
    PAPEIS_PARTICIPANTE,
    PAPEIS_SEM_CASO,
    ProcessoService,
)
from gestaolegal.utils.api_decorators import authorized
from gestaolegal.utils.api_response import success_response
from gestaolegal.utils.request_context import RequestContext

processo_controller = Blueprint("processo_api", __name__)

PAPEIS_LEITURA = PAPEIS_SEM_CASO + PAPEIS_PARTICIPANTE


def _data(nome: str) -> date | None:
    valor = (request.args.get(nome) or "").strip()
    if not valor:
        return None
    try:
        return date.fromisoformat(valor)
    except ValueError as erro:
        raise ValidationException("Data inválida (use AAAA-MM-DD)", field=nome) from erro


def _texto(nome: str, limite: int = 100) -> str | None:
    valor = (request.args.get(nome) or "").strip()
    return valor[:limite] or None


def _corpo() -> dict[str, Any]:
    corpo = request.get_json(silent=True)
    if not isinstance(corpo, dict):
        raise ValidationException("Corpo da requisição inválido")
    return corpo


@processo_controller.route("", methods=["GET"])
@authorized(*PAPEIS_LEITURA)
def listar():
    page = request.args.get("page", default=1, type=int)
    per_page = min(request.args.get("per_page", default=20, type=int), 100)
    resultado = ProcessoService().listar(
        RequestContext.get_current_user(),
        RequestContext.get_unidade_ativa(),
        PageParams(page=max(page, 1), per_page=max(per_page, 1)),
        parte=_texto("parte"),
        numero=_texto("numero", 30),
        distribuicao_de=_data("distribuicao_de"),
        distribuicao_ate=_data("distribuicao_ate"),
        status=_texto("status", 10),
        com_caso=_texto("com_caso", 10),
    )
    return success_response(data=resultado.to_dict())


@processo_controller.route("", methods=["POST"])
@authorized(*PAPEIS_SEM_CASO)
def criar():
    dados = ProcessoSemCasoInput.model_validate(_corpo())
    processo = ProcessoService().criar_sem_caso(
        dados, RequestContext.get_current_user(), RequestContext.get_unidade_ativa()
    )
    return success_response(
        data=processo, message="Processo criado com sucesso", status_code=201
    )


@processo_controller.route("/<int:id>", methods=["GET"])
@authorized(*PAPEIS_LEITURA)
def detalhe(id: int):
    dados = ProcessoService().detalhe(
        id, RequestContext.get_current_user(), RequestContext.get_unidade_ativa()
    )
    return success_response(data=dados)


@processo_controller.route("/<int:id>", methods=["PUT"])
@authorized(*PAPEIS_LEITURA)
def atualizar(id: int):
    corpo = _corpo()
    partes_brutas = corpo.pop("partes", None)
    partes = None
    if partes_brutas is not None:
        if not isinstance(partes_brutas, list):
            raise ValidationException("Partes inválidas", field="partes")
        partes = [ParteInput.model_validate(p) for p in partes_brutas]
    dados = ProcessoService().atualizar(
        id,
        ProcessoUpdateInput.model_validate(corpo),
        partes,
        RequestContext.get_current_user(),
        RequestContext.get_unidade_ativa(),
    )
    return success_response(data=dados, message="Processo atualizado com sucesso")


@processo_controller.route("/<int:id>", methods=["DELETE"])
@authorized(*PAPEIS_LEITURA)
def excluir(id: int):
    ProcessoService().excluir(
        id, RequestContext.get_current_user(), RequestContext.get_unidade_ativa()
    )
    return success_response(message="Processo inativado com sucesso")
