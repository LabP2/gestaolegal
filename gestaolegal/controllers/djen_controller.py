"""Rotas do DJEN (docs/plano-djen.md, §5).

Montado em `/api`: as rotas ficam em `/api/djen/...`, mais
`/api/processos/<id>/djen/buscar`. Todas filtram pela unidade ativa e
respondem 403 quando o NPJ está com o DJEN desligado (`tenants.djen_ativo`).
"""

from datetime import date
from functools import wraps
from typing import Any

from flask import Blueprint, request

from gestaolegal.common import PageParams
from gestaolegal.exceptions import ValidationException
from gestaolegal.services.djen_service import (
    PAPEIS_GESTAO,
    PAPEIS_OABS,
    PAPEIS_PARTICIPANTE,
    PAPEIS_UNIDADE,
    DJENService,
)
from gestaolegal.utils.api_decorators import authenticated, authorized
from gestaolegal.utils.api_response import success_response
from gestaolegal.utils.request_context import RequestContext

djen_controller = Blueprint("djen_api", __name__)

PAPEIS_LEITURA = PAPEIS_UNIDADE + PAPEIS_PARTICIPANTE


def djen_habilitado(func):
    """403 quando o DJEN está desligado para o NPJ. Vem depois da autenticação."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        DJENService().exigir_ativo()
        return func(*args, **kwargs)

    return wrapper


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


def _oab(valor: str | None) -> str | None:
    """`123456/MG`, `123456MG` ou `MG123456` -> `123456/MG`."""
    if not valor:
        return None
    digitos = "".join(c for c in valor if c.isdigit())
    letras = "".join(c for c in valor if c.isalpha()).upper()
    if not digitos or len(letras) != 2:
        raise ValidationException("OAB inválida (ex.: 123456/MG)", field="oab")
    return f"{digitos}/{letras}"


@djen_controller.route("/djen/publicacoes", methods=["GET"])
@authorized(*PAPEIS_LEITURA)
@djen_habilitado
def listar_publicacoes():
    page = request.args.get("page", default=1, type=int)
    per_page = min(request.args.get("per_page", default=20, type=int), 100)
    caso_id = request.args.get("caso_id", default=None, type=int)
    filtros: dict[str, Any] = {
        "inicio": _data("inicio"),
        "fim": _data("fim"),
        "tribunal": _texto("tribunal", 30),
        "tipo": _texto("tipo", 100),
        "oab": _oab(_texto("oab", 20)),
        "situacao": _texto("situacao", 12),
        "caso_id": caso_id,
        "q": _texto("q", 200),
    }
    result = DJENService().listar(
        RequestContext.get_current_user(),
        RequestContext.get_unidade_ativa(),
        PageParams(page=max(page, 1), per_page=max(per_page, 1)),
        filtros,
    )
    return success_response(data=result.to_dict())


@djen_controller.route("/djen/publicacoes/<int:id>", methods=["GET"])
@authorized(*PAPEIS_LEITURA)
@djen_habilitado
def detalhe_publicacao(id: int):
    dados = DJENService().detalhe(
        id, RequestContext.get_current_user(), RequestContext.get_unidade_ativa()
    )
    return success_response(data=dados)


@djen_controller.route("/djen/publicacoes/<int:id>/vincular", methods=["POST"])
@authorized(*PAPEIS_GESTAO)
@djen_habilitado
def vincular_publicacao(id: int):
    corpo = request.get_json(silent=True) or {}
    dados = DJENService().vincular(
        id,
        corpo.get("processo_id") if isinstance(corpo, dict) else None,
        RequestContext.get_current_user(),
        RequestContext.get_unidade_ativa(),
    )
    return success_response(data=dados, message="Publicação vinculada ao processo")


@djen_controller.route("/djen/publicacoes/<int:id>/descartar", methods=["POST"])
@authorized(*PAPEIS_GESTAO)
@djen_habilitado
def descartar_publicacao(id: int):
    dados = DJENService().descartar(
        id, RequestContext.get_current_user(), RequestContext.get_unidade_ativa()
    )
    return success_response(data=dados, message="Publicação descartada")


def _corpo() -> dict[str, Any]:
    corpo = request.get_json(silent=True)
    if not isinstance(corpo, dict):
        raise ValidationException("Corpo da requisição inválido")
    return corpo


@djen_controller.route("/djen/oabs", methods=["GET"])
@authorized(*PAPEIS_OABS)
@djen_habilitado
def listar_oabs():
    dados = DJENService().listar_oabs(RequestContext.get_unidade_ativa())
    return success_response(data=dados)


@djen_controller.route("/djen/oabs/sugestoes", methods=["GET"])
@authorized(*PAPEIS_OABS)
@djen_habilitado
def sugestoes_oab():
    dados = DJENService().sugestoes_oab(RequestContext.get_unidade_ativa())
    return success_response(data=dados)


@djen_controller.route("/djen/oabs", methods=["POST"])
@authorized(*PAPEIS_OABS)
@djen_habilitado
def criar_oab():
    dados = DJENService().criar_oab(
        _corpo(), RequestContext.get_current_user(), RequestContext.get_unidade_ativa()
    )
    return success_response(data=dados, message="OAB cadastrada", status_code=201)


@djen_controller.route("/djen/oabs/<int:id>", methods=["PUT"])
@authorized(*PAPEIS_OABS)
@djen_habilitado
def atualizar_oab(id: int):
    dados = DJENService().atualizar_oab(
        id,
        _corpo(),
        RequestContext.get_current_user(),
        RequestContext.get_unidade_ativa(),
    )
    return success_response(data=dados, message="OAB atualizada")


@djen_controller.route("/djen/oabs/<int:id>", methods=["DELETE"])
@authorized(*PAPEIS_OABS)
@djen_habilitado
def remover_oab(id: int):
    DJENService().remover_oab(
        id, RequestContext.get_current_user(), RequestContext.get_unidade_ativa()
    )
    return success_response(message="OAB removida")


@djen_controller.route("/djen/status", methods=["GET"])
@authorized(*PAPEIS_LEITURA)
@djen_habilitado
def status():
    service = DJENService()
    dados = service.status()
    dados["filtros"] = service.opcoes_de_filtro(RequestContext.get_unidade_ativa())
    return success_response(data=dados)


@djen_controller.route("/processos/<int:id>/djen/buscar", methods=["POST"])
@authorized(*PAPEIS_GESTAO)
@djen_habilitado
def buscar_processo(id: int):
    resultado = DJENService().buscar_processo(
        id, RequestContext.get_current_user(), RequestContext.get_unidade_ativa()
    )
    return success_response(data=resultado, message="Busca no DJEN concluída")

