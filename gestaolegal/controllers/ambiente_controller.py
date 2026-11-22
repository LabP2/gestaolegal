"""Informações públicas do ambiente, lidas pelo front antes do login."""

from flask import Blueprint, current_app

from gestaolegal.utils.api_response import success_response

ambiente_controller = Blueprint("ambiente_api", __name__)


@ambiente_controller.route("", methods=["GET"])
def ambiente():
    # Pública por desenho: expõe só o booleano, nada de configuração ou versão.
    return success_response(data={"demo": bool(current_app.config.get("DEMO_MODE"))})
