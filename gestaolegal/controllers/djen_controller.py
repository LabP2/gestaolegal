"""Rotas do DJEN (docs/plano-djen.md, §5).

Montado em `/api`: as rotas ficam em `/api/djen/...`, mais
`/api/processos/<id>/djen/buscar`. Todas filtram pela unidade ativa e
respondem 403 quando o NPJ está com o DJEN desligado (`tenants.djen_ativo`).
"""

from datetime import date
from functools import wraps
from typing import Any

from flask import Blueprint, Response, request, stream_with_context

from gestaolegal.common import PageParams
from gestaolegal.exceptions import ValidationException
from gestaolegal.services.djen_service import (
    PAPEIS_EXEMPLOS,
    PAPEIS_GESTAO,
    PAPEIS_OABS,
    PAPEIS_PARTICIPANTE,
    PAPEIS_ROTINA,
    PAPEIS_UNIDADE,
    DJENService,
    link_certidao,
)
from gestaolegal.utils.api_decorators import authorized
from gestaolegal.utils.api_response import success_response
from gestaolegal.utils.request_context import RequestContext, contexto_tenant

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
        raise ValidationException(
            "Data inválida (use AAAA-MM-DD)", field=nome
        ) from erro


def _texto(nome: str, limite: int = 100) -> str | None:
    valor = (request.args.get(nome) or "").strip()
    return valor[:limite] or None


def _tribunais() -> list[str]:
    # Aceita links antigos com um tribunal e parâmetros repetidos ou separados por vírgula.
    valores = [sigla.strip() for valor in request.args.getlist("tribunal")
               for sigla in valor.split(",") if sigla.strip()]
    if len(valores) > 100 or any(len(sigla) > 30 for sigla in valores):
        raise ValidationException("Filtro de tribunais inválido", field="tribunal")
    return list(dict.fromkeys(valores))


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
    processo_id = request.args.get("processo_id", default=None, type=int)
    filtros: dict[str, Any] = {
        "inicio": _data("inicio"),
        "fim": _data("fim"),
        "tribunal": _tribunais(),
        "tipo": _texto("tipo", 100),
        "oab": _texto("oab", 30),
        "nome_parte": _texto("nome_parte", 150),
        "polo": _texto("polo", 12),
        "numero_processo": _texto("numero_processo", 30),
        "situacao": _texto("situacao", 12),
        "caso_id": caso_id,
        "processo_id": processo_id,
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


@djen_controller.route("/djen/sincronizar", methods=["POST"])
@authorized(*PAPEIS_ROTINA)
@djen_habilitado
def sincronizar():
    """Roda a rotina agora, só para o NPJ de quem chama.

    Como o botão "Buscar publicações agora" do processo, é uma ação manual:
    depende da chave do NPJ (`djen_ativo`), não de `DJEN_SYNC_ENABLED`, que
    trava apenas a execução agendada.
    """
    registro = DJENService().sincronizar()
    return success_response(data=registro, message="Rotina do DJEN concluída")


@djen_controller.route("/processos/<int:id>/djen/buscar", methods=["POST"])
@authorized(*PAPEIS_GESTAO)
@djen_habilitado
def buscar_processo(id: int):
    resultado = DJENService().buscar_processo(
        id, RequestContext.get_current_user(), RequestContext.get_unidade_ativa()
    )
    return success_response(data=resultado, message="Busca no DJEN concluída")


@djen_controller.route("/djen/busca-parte", methods=["GET"])
@authorized(*PAPEIS_GESTAO)
@djen_habilitado
def busca_parte():
    """Consulta o DJEN por nome da parte e persiste todas as páginas recebidas.

    `nome` pode se repetir (o nome do atendido e as variações); `tribunal`
    também (uma consulta por tribunal; nenhum = todos).
    """
    dados = DJENService().busca_parte(
        request.args.getlist("nome"),
        request.args.get("de"),
        request.args.get("ate"),
        request.args.getlist("tribunal"),
        RequestContext.get_current_user(),
        RequestContext.get_unidade_ativa(),
    )
    return success_response(data=dados)


@djen_controller.route("/djen/busca-parte/importar", methods=["POST"])
@authorized(*PAPEIS_GESTAO)
@djen_habilitado
def importar_busca_parte():
    dados = DJENService().importar_busca(
        _corpo(), RequestContext.get_current_user(), RequestContext.get_unidade_ativa()
    )
    return success_response(data=dados, message="Publicações importadas")


@djen_controller.route("/djen/busca-parte/nao-pertinentes", methods=["POST"])
@authorized(*PAPEIS_GESTAO)
@djen_habilitado
def nao_pertinentes_busca_parte():
    """Marca publicações da busca como não pertinentes (banco de exemplos).

    Usa as publicações já salvas; não cria processo nem vínculo.
    """
    dados = DJENService().marcar_nao_pertinentes(
        _corpo(), RequestContext.get_current_user()
    )
    return success_response(
        data=dados, message="Publicações marcadas como irrelevantes"
    )


@djen_controller.route("/djen/exemplos/resumo", methods=["GET"])
@authorized(*PAPEIS_EXEMPLOS)
@djen_habilitado
def resumo_exemplos():
    return success_response(data=DJENService().resumo_exemplos())


@djen_controller.route("/djen/exemplos/exportar", methods=["GET"])
@authorized(*PAPEIS_EXEMPLOS)
@djen_habilitado
def exportar_exemplos():
    """Arquivo JSON Lines com os exemplos rotulados do NPJ.

    `incluir_nao_revisadas=1` acrescenta as não revisadas.
    """
    incluir = (request.args.get("incluir_nao_revisadas") or "").strip().lower() in (
        "1",
        "true",
        "sim",
    )
    conteudo = DJENService().exportar_exemplos(incluir_nao_revisadas=incluir)
    tenant_id = RequestContext.get_tenant()

    def linhas():
        # A autenticação encerra seu contexto antes de o servidor consumir
        # o stream. Restaure somente o NPJ capturado no token, sem mantê-lo
        # ativo entre chunks ou requisições.
        while True:
            with contexto_tenant(tenant_id):
                try:
                    linha = next(conteudo)
                except StopIteration:
                    return
            yield linha

    nome = f"djen-exemplos-{date.today().isoformat()}.jsonl"
    return Response(
        stream_with_context(linhas()),
        mimetype="application/x-ndjson",
        headers={
            "Content-Disposition": f'attachment; filename="{nome}"',
            "Cache-Control": "no-store",
        },
    )


@djen_controller.route("/djen/acervo", methods=["GET"])
@authorized(*PAPEIS_GESTAO)
@djen_habilitado
def listar_acervo():
    filtros = {
        k: _texto(k) for k in ("rotulo", "origem", "situacao", "situacao_operacional", "fonte", "sugestao")
    }
    filtros.update(inicio=_data("inicio"), fim=_data("fim"), nome_parte=_texto("nome_parte", 150), numero_processo=_texto("numero_processo", 30), oab=_texto("oab", 30))
    filtros['polo'] = _texto('polo', 12)
    filtros['tribunal'] = _tribunais()
    filtros['contexto_id'] = request.args.get('contexto_id', type=int)
    filtros['texto_integral'] = request.args.get('texto_integral') == '1'
    nomes = [nome.strip() for nome in request.args.getlist('nomes') if nome.strip()]
    if len(nomes) + bool(filtros.get('nome_parte')) > 20 or any(not 3 <= len(nome) <= 150 for nome in nomes):
        raise ValidationException('Informe até 20 nomes; variações devem ter de 3 a 150 caracteres', field='nomes')
    filtros['nomes'] = nomes
    dados = DJENService().acervo.listar(
        RequestContext.get_unidade_ativa(),
        filtros,
        max(1, request.args.get("page", 1, type=int)),
        max(1, min(100, request.args.get("per_page", 20, type=int))),
    )
    return success_response(data=dados)


@djen_controller.route("/djen/acervo/<int:id>", methods=["GET"])
@authorized(*PAPEIS_GESTAO)
@djen_habilitado
def detalhe_acervo(id):
    from gestaolegal.exceptions import NotFoundException

    dados = DJENService().acervo.detalhe(id, RequestContext.get_unidade_ativa())
    if dados is None:
        raise NotFoundException(resource="Publicação", resource_id=id)
    dados["link_certidao"] = link_certidao(dados.get("hash"))
    return success_response(data=dados)


@djen_controller.route("/djen/acervo/classificar", methods=["POST"])
@authorized(*PAPEIS_GESTAO)
@djen_habilitado
def classificar_acervo():
    return success_response(
        data=DJENService().classificar_acervo(
            _corpo(),
            RequestContext.get_current_user(),
            RequestContext.get_unidade_ativa(),
        )
    )


@djen_controller.route("/djen/acervo/descartar", methods=["POST"])
@authorized(*PAPEIS_GESTAO)
@djen_habilitado
def descartar_acervo():
    return success_response(
        data=DJENService().descartar_acervo(
            _corpo(),
            RequestContext.get_current_user(),
            RequestContext.get_unidade_ativa(),
        )
    )


@djen_controller.route("/djen/monitoramentos", methods=["GET", "POST"])
@authorized(*PAPEIS_GESTAO)
@djen_habilitado
def monitoramentos():
    from gestaolegal.services.djen_monitoramento_service import DjenMonitoramentoService
    service = DjenMonitoramentoService()
    user = RequestContext.get_current_user()
    if request.method == "POST":
        return success_response(data=service.criar(_corpo(), user, RequestContext.get_unidade_ativa()), status_code=201)
    return success_response(data=service.listar(user))


@djen_controller.route("/djen/monitoramentos/<int:id>", methods=["PATCH", "DELETE"])
@authorized(*PAPEIS_GESTAO)
@djen_habilitado
def alterar_monitoramento(id):
    from gestaolegal.services.djen_monitoramento_service import DjenMonitoramentoService
    DjenMonitoramentoService().alterar(id, {} if request.method == "DELETE" else _corpo(),
        RequestContext.get_current_user(), remover=request.method == "DELETE")
    return success_response(message="Monitoramento atualizado")


@djen_controller.route("/djen/monitoramentos/buscar", methods=["POST"])
@authorized(*PAPEIS_GESTAO)
@djen_habilitado
def buscar_monitoramento():
    from gestaolegal.services.djen_monitoramento_service import DjenMonitoramentoService
    return success_response(data=DjenMonitoramentoService().buscar(_corpo(),
        RequestContext.get_current_user(), RequestContext.get_unidade_ativa()))


@djen_controller.route("/djen/monitoramentos/logs", methods=["GET"])
@authorized(*PAPEIS_GESTAO)
@djen_habilitado
def logs_monitoramento():
    from gestaolegal.services.djen_monitoramento_service import DjenMonitoramentoService
    return success_response(data=DjenMonitoramentoService().logs(RequestContext.get_current_user(), request.args))


@djen_controller.route("/djen/monitoramentos/execucoes", methods=["GET"])
@authorized(*PAPEIS_GESTAO)
@djen_habilitado
def execucoes_monitoramento():
    from gestaolegal.services.djen_monitoramento_service import DjenMonitoramentoService
    return success_response(data=DjenMonitoramentoService().execucoes(RequestContext.get_current_user(), request.args))


@djen_controller.route('/djen/contextos', methods=['GET', 'POST'])
@authorized(*PAPEIS_GESTAO)
@djen_habilitado
def contextos_djen():
    from gestaolegal.services.djen_contexto_service import DjenContextoService
    servico = DjenContextoService()
    unidade = RequestContext.get_unidade_ativa()
    return success_response(data=servico.criar(_corpo(), unidade) if request.method == 'POST' else servico.listar(unidade))


@djen_controller.route('/djen/contextos/<int:cid>/classificar', methods=['POST'])
@authorized(*PAPEIS_GESTAO)
@djen_habilitado
def classificar_contexto(cid):
    from gestaolegal.services.djen_contexto_service import DjenContextoService
    return success_response(data=DjenContextoService().classificar(cid, _corpo(),
        RequestContext.get_unidade_ativa(), RequestContext.get_current_user().id))


@djen_controller.route('/djen/contextos/<int:cid>/desfazer', methods=['POST'])
@authorized(*PAPEIS_GESTAO)
@djen_habilitado
def desfazer_classificacao_contexto(cid):
    from gestaolegal.services.djen_contexto_service import DjenContextoService
    return success_response(data=DjenContextoService().desfazer(cid, _corpo(),
        RequestContext.get_unidade_ativa(), RequestContext.get_current_user().id))


@djen_controller.route('/djen/contextos/<int:cid>/treinar', methods=['POST'])
@authorized(*PAPEIS_GESTAO)
@djen_habilitado
def treinar_contexto(cid):
    from gestaolegal.services.djen_contexto_service import DjenContextoService
    return success_response(data=DjenContextoService().solicitar_treino(cid, RequestContext.get_unidade_ativa()), status_code=202)


@djen_controller.route('/djen/contextos/previa', methods=['POST'])
@authorized(*PAPEIS_GESTAO)
@djen_habilitado
def previa_novo_contexto():
    from gestaolegal.services.djen_contexto_service import DjenContextoService
    return success_response(data=DjenContextoService().previa(_corpo(), RequestContext.get_unidade_ativa()))


@djen_controller.route('/djen/contextos/<int:cid>', methods=['PUT'])
@authorized(*PAPEIS_GESTAO)
@djen_habilitado
def editar_contexto(cid):
    from gestaolegal.services.djen_contexto_service import DjenContextoService
    return success_response(data=DjenContextoService().editar(cid, _corpo(), RequestContext.get_unidade_ativa()))


@djen_controller.route('/djen/contextos/<int:cid>', methods=['DELETE'])
@authorized(*PAPEIS_GESTAO)
@djen_habilitado
def excluir_contexto(cid):
    from gestaolegal.services.djen_contexto_service import DjenContextoService
    return success_response(data=DjenContextoService().excluir(cid, RequestContext.get_unidade_ativa()))


@djen_controller.route('/djen/contextos/<int:cid>/previa', methods=['POST'])
@authorized(*PAPEIS_GESTAO)
@djen_habilitado
def previa_edicao_contexto(cid):
    from gestaolegal.services.djen_contexto_service import DjenContextoService
    return success_response(data=DjenContextoService().previa(_corpo(), RequestContext.get_unidade_ativa(), cid))


@djen_controller.route('/djen/contextos/<int:cid>/treinos', methods=['GET'])
@authorized(*PAPEIS_GESTAO)
@djen_habilitado
def historico_treinos(cid):
    from gestaolegal.services.djen_contexto_service import DjenContextoService
    pagina = request.args.get('page', 1, type=int)
    if pagina is None or pagina < 1:
        raise ValidationException('Página inválida')
    return success_response(data=DjenContextoService().historico_treinos(cid, RequestContext.get_unidade_ativa(), pagina))
