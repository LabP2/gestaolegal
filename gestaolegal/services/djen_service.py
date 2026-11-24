"""Captura e consulta das publicações do DJEN (docs/plano-djen.md, §4).

Dois caminhos de entrada:

- a rotina (`flask djen sincronizar`), que roda **sem request**: o comando
  itera os NPJs com `djen_ativo` e chama `sincronizar()` dentro de
  `contexto_tenant(id)`, um NPJ de cada vez;
- o botão "Buscar publicações agora" da tela do processo
  (`buscar_processo()`), uma única consulta pelo número.

Em nenhum dos dois há unidade ativa: a unidade de cada INSERT vem do caso do
processo (ou, sem caso, da OAB por onde a publicação chegou).
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any

from gestaolegal.common import PageParams, PaginatedResult
from gestaolegal.config import Config
from gestaolegal.exceptions import (
    BusinessLogicException,
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from gestaolegal.integrations import djen_html
from gestaolegal.integrations.djen_client import Comunicacao, DJENClient, DJENError
from gestaolegal.models.caso import Caso
from gestaolegal.models.evento import Evento
from gestaolegal.models.djen import (
    SITUACOES,
    ComunicacaoDJEN,
    ComunicacaoListItem,
    OabMonitorada,
    ResultadoCaptura,
)
from gestaolegal.models.processo import Processo
from gestaolegal.models.processo_input import ParteInput, ProcessoDjenInput
from gestaolegal.models.user import UserInfo
from gestaolegal.repositories.caso_repository import CasoRepository
from gestaolegal.repositories.djen_repository import (
    DjenComunicacaoRepository,
    DjenOabRepository,
    DjenSincronizacaoRepository,
)
from gestaolegal.repositories.djen_acervo_repository import DjenAcervoRepository
from gestaolegal.utils.request_context import RequestContext
from gestaolegal.repositories.evento_repository import EventoRepository
from gestaolegal.repositories.atendido_repository import AtendidoRepository
from gestaolegal.repositories.processo_repository import ProcessoRepository
from gestaolegal.repositories.tenant_repository import TenantRepository
from gestaolegal.services.notificacao_service import NotificacaoService
from gestaolegal.services.referencias import exigir_existente
from gestaolegal.utils.cnj import mascarar_cnj
from gestaolegal.utils.tempo import agora_utc, hoje_brasilia, utc_para_brasilia

logger = logging.getLogger(__name__)

# Permissões (plano, §7).
PAPEIS_GESTAO = ("admin", "prof", "orient")  # sem caso, vincular, descartar
PAPEIS_UNIDADE = PAPEIS_GESTAO + ("colab_proj",)  # lista de toda a unidade
PAPEIS_PARTICIPANTE = ("estag_direito", "colab_ext")  # só casos de que participam

# Só o admin do NPJ mantém a lista de OABs monitoradas (plano, Decisões, 1).
PAPEIS_OABS = ("admin",)
PAPEIS_ROTINA = ("admin",)  # rodar a rotina do NPJ pela tela
# De quem o `usuarios.oab` aparece como sugestão na tela das OABs.
PAPEIS_SUGESTAO_OAB = ("orient", "prof", "admin")
UFS = frozenset(
    "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split()
)

MSG_DESLIGADO = "A busca no DJEN não está habilitada para este NPJ."

# Busca manual por parte (docs/plano-processos-avulsos.md, §3).
BUSCA_PARTE_MAX_DIAS = 30
BUSCA_PARTE_MAX_NOMES = 5
# Uma consulta por nome e por tribunal: limita a conta nome x tribunal.
BUSCA_PARTE_MAX_TRIBUNAIS = 10
BUSCA_PARTE_MAX_PAGINAS = 10  # 1000 publicações por nome
IMPORTACAO_MAX_ITENS = 100
ESPECIE_IMPORTADA = "Outros"

# Marca de "exemplo ainda não lido" em `_rotular`.
_CONSULTAR = object()

# Banco de exemplos rotulados (docs/plano-processos-avulsos.md, "Banco de
# exemplos"). Só o admin vê as contagens e exporta.
PAPEIS_EXEMPLOS = ("admin",)
ROTULOS_EXPLICITOS = ("relevante", "irrelevante")
# Campos do exemplo no arquivo exportado (JSON Lines), nesta ordem.
CAMPOS_EXPORTACAO = (
    "id_djen",
    "rotulo",
    "origem",
    "data_disponibilizacao",
    "numero_processo",
    "sigla_tribunal",
    "nome_orgao",
    "nome_classe",
    "tipo_comunicacao",
    "tipo_documento",
    "termo_busca",
    "destinatarios",
    "texto_plano",
    "rotulado_em",
    "id_rotulado_por",
)


def dias_uteis_entre(inicio: date, fim: date) -> int:
    """Dias úteis (seg–sex) depois de `inicio` até `fim`, inclusive."""
    dias = 0
    atual = inicio
    while atual < fim:
        atual += timedelta(days=1)
        if atual.weekday() < 5:
            dias += 1
    return dias


def separar_oab(valor: str | None) -> tuple[str, str] | None:
    """`123456/MG`, `MG 123.456` ou `123456MG` -> ("123456", "MG"); senão None.

    `usuarios.oab` é texto livre: o que não couber no padrão não vira sugestão.
    """
    if not valor:
        return None
    digitos = "".join(c for c in valor if c.isdigit())
    letras = "".join(c for c in valor if c.isalpha()).upper()
    if not digitos or len(digitos) > 10 or letras not in UFS:
        return None
    return digitos.lstrip("0") or "0", letras


def demo_ligado() -> bool:
    """`DEMO_MODE` do app em curso (os testes alteram `app.config`)."""
    from flask import current_app, has_app_context

    if has_app_context():
        return bool(current_app.config.get("DEMO_MODE", Config.DEMO_MODE))
    return Config.DEMO_MODE


def cliente_padrao() -> DJENClient:
    """Cliente da API real ou, no ambiente de demonstração, o DJEN fictício."""
    if demo_ligado():
        from gestaolegal.integrations.djen_demo import transporte_demo

        return DJENClient(base_url=Config.DJEN_API_URL, transporte=transporte_demo)
    return DJENClient(base_url=Config.DJEN_API_URL)


def link_certidao(hash_: str | None) -> str | None:
    if not hash_:
        return None
    if hash_.startswith("demo-"):
        return None  # publicação fictícia: não há certidão no DJEN
    return f"{Config.DJEN_API_URL}/api/v1/comunicacao/{hash_}/certidao"


class DJENService:
    def __init__(self, client: DJENClient | None = None):
        self.client = client or cliente_padrao()
        self.repo = DjenComunicacaoRepository()
        self.sincronizacoes = DjenSincronizacaoRepository()
        self.processos = ProcessoRepository()
        self.casos = CasoRepository()
        self.tenants = TenantRepository()
        self.eventos = EventoRepository()
        self.oabs = DjenOabRepository()
        self.acervo = DjenAcervoRepository()
        self._alteracoes_captura = set()
        self._recebidas_antes = set()
        # Avisos da captura em curso, agregados por caso até o commit da fonte:
        # {caso_id: (caso, eventos, executor)}.
        self._avisos: dict[int, tuple[Caso, list[Evento], int | None]] = {}

    @property
    def session(self):
        return self.repo.session

    # --- chave por NPJ ----------------------------------------------------

    def djen_ativo(self) -> bool:
        return self.tenants.djen_ativo(self.repo.tenant_id())

    def exigir_ativo(self) -> None:
        if not self.djen_ativo():
            raise ForbiddenException(MSG_DESLIGADO)

    # --- leitura ------------------------------------------------------------

    @staticmethod
    def _escopo_do_papel(user: UserInfo) -> tuple[tuple[str, ...], int | None]:
        """(situações visíveis, participante) do papel (plano, §7).

        Quem não pode vincular nem ver a caixa "Sem caso" vê só publicações já
        vinculadas a um caso; estagiário e colaborador externo, só as dos
        casos de que participam.
        """
        if user.urole in PAPEIS_GESTAO:
            return SITUACOES, None
        if user.urole in PAPEIS_UNIDADE:
            return ("vinculada",), None
        if user.urole in PAPEIS_PARTICIPANTE:
            return ("vinculada",), user.id
        raise ForbiddenException()

    def listar(
        self,
        user: UserInfo,
        unidade_id: int,
        page_params: PageParams,
        filtros: dict[str, Any],
    ) -> PaginatedResult[ComunicacaoListItem]:
        situacoes, participante = self._escopo_do_papel(user)
        situacao = filtros.get("situacao")
        if situacao and situacao not in SITUACOES:
            raise ValidationException("Situação inválida", field="situacao")
        if situacao and situacao not in situacoes:
            raise ForbiddenException()
        result = self.repo.listar(
            page_params,
            unidade_id=unidade_id,
            situacoes=situacoes,
            participante_id=participante,
            **filtros,
        )
        for item in result.items:
            item.numero_processo_mascara = item.numero_processo_mascara or mascarar_cnj(
                item.numero_processo
            )
            if item.resumo:
                item.resumo = djen_html.resumo(item.resumo, 200)
        return result

    def opcoes_de_filtro(self, unidade_id: int) -> dict[str, list[str]]:
        return {
            "tribunais": self.repo.valores_distintos("sigla_tribunal", unidade_id),
            "tipos": self.repo.valores_distintos("tipo_comunicacao", unidade_id),
        }

    def _visivel(self, id: int, user: UserInfo, unidade_id: int) -> ComunicacaoDJEN:
        """A publicação, se o papel e a unidade permitem vê-la; senão 404."""
        comunicacao = self.repo.find_by_id(id)
        situacoes, participante = self._escopo_do_papel(user)
        if (
            comunicacao is None
            or comunicacao.unidade_id != unidade_id
            or comunicacao.situacao not in situacoes
        ):
            raise NotFoundException(resource="Publicação", resource_id=id)
        if participante is not None:
            caso = (
                self.casos.find_by_id(comunicacao.id_caso)
                if comunicacao.id_caso
                else None
            )
            if caso is None or participante not in (
                caso.id_orientador,
                caso.id_estagiario,
                caso.id_colaborador,
                caso.id_usuario_responsavel,
            ):
                raise NotFoundException(resource="Publicação", resource_id=id)
        return comunicacao

    def detalhe(self, id: int, user: UserInfo, unidade_id: int) -> dict[str, Any]:
        comunicacao = self._visivel(id, user, unidade_id)
        dados = {
            k: v
            for k, v in comunicacao.__dict__.items()
            # O HTML original é de terceiros: o front só recebe o filtrado.
            if k not in ("texto_html", "texto_plano")
        }
        dados["numero_processo_mascara"] = comunicacao.numero_processo_mascara or (
            mascarar_cnj(comunicacao.numero_processo)
        )
        dados["texto_html_seguro"] = djen_html.html_seguro(comunicacao.texto_html)
        dados["link_certidao"] = link_certidao(comunicacao.hash)
        dados["destinatarios"] = comunicacao.destinatarios or []
        dados["advogados"] = comunicacao.advogados or []
        dados["pode_vincular"] = user.urole in PAPEIS_GESTAO
        return dados

    def status(self) -> dict[str, Any]:
        ultima = self.sincronizacoes.ultima()
        rotina = {
            "janela_dias": Config.DJEN_JANELA_DIAS,
            "max_processos": Config.DJEN_MAX_PROCESSOS,
        }
        if ultima is None:
            return {"ultima": None, "atrasada": True, "rotina": rotina}
        referencia = utc_para_brasilia(ultima.fim or ultima.inicio).date()
        return {
            "ultima": ultima.__dict__,
            "atrasada": dias_uteis_entre(referencia, hoje_brasilia()) > 2,
            "rotina": rotina,
        }

    # --- captura ------------------------------------------------------------

    def _casar(self, numero_cnj: str) -> Processo | None:
        """Processo ativo do tenant com o número. Ambíguo não casa."""
        encontrados = self.processos.find_by_numero_cnj(numero_cnj)
        if len(encontrados) == 1:
            return encontrados[0]
        if len(encontrados) > 1:
            logger.warning(
                f"DJEN: {len(encontrados)} processos com o número {numero_cnj}; "
                "publicação fica sem vínculo automático"
            )
        return None

    def _caso_do_processo(self, processo: Processo) -> Caso | None:
        """Caso do processo; None no processo sem caso."""
        if processo.id_caso is None:
            return None
        return self.casos.find_by_id(processo.id_caso)

    def registrar(
        self,
        item: Comunicacao,
        resultado: ResultadoCaptura,
        *,
        processo: Processo | None = None,
        unidade_padrao: int | None = None,
        oab_origem: str | None = None,
        executor_id: int | None = None,
        exemplo: bool = True,
        somente_com_processo: bool = False,
    ) -> None:
        """Upsert por `id_djen` no tenant ativo (idempotente).

        `processo` vem da busca pelo número; sem ele, casa pelo `numero_cnj`.
        Toda captura pode vincular ao processo; descartes e vínculos anteriores são preservados.
        """
        agora = agora_utc()
        pid = self.acervo.guardar(self._dados_publicacao(item))
        existente = self.repo.find_by_id_djen(item.id_djen)
        alvo = processo if processo is not None else self._casar(item.numero_processo)
        if existente is not None:
            mudou = (
                item.id_djen in self._alteracoes_captura
                or existente.ativo != item.ativo
                or (existente.motivo_cancelamento or None)
                != (item.motivo_cancelamento or None)
            )
            if mudou:
                self._alteracoes_captura.discard(item.id_djen)
                self.repo.atualizar(
                    existente.id,
                    {
                        "ativo": item.ativo,
                        "motivo_cancelamento": item.motivo_cancelamento,
                        "atualizada_em": agora,
                    },
                )
                resultado.atualizadas += 1
                if existente.ativo and not item.ativo and existente.id_caso:
                    self._ao_cancelar(existente, executor_id)
            if existente.situacao == "pendente" and alvo is not None:
                self._vincular(existente.id, alvo, self._caso_do_processo(alvo), executor_id,
                    manual=False, exemplo=exemplo)
                resultado.vinculadas += 1
            return

        if alvo is None and somente_com_processo:
            return
        caso = self._caso_do_processo(alvo) if alvo else None
        # Processo sem caso: a unidade é a do próprio processo.
        if caso is not None:
            unidade_id = caso.unidade_id
        elif alvo is not None:
            unidade_id = alvo.unidade_id
        else:
            unidade_id = unidade_padrao
        if unidade_id is None:
            logger.warning(
                f"DJEN: publicação {item.id_djen} sem caso nem unidade de origem; ignorada"
            )
            return

        novo_id = self.repo.criar(
            {
                "id_publicacao": pid,
                "situacao": "pendente",
                "oab_origem": oab_origem,
                "unidade_id": unidade_id,
            }
        )
        resultado.novas += 1
        if alvo is not None:
            self._vincular(
                novo_id, alvo, caso, executor_id, manual=False, exemplo=exemplo
            )
            resultado.vinculadas += 1

    def _vincular(
        self,
        comunicacao_id: int,
        processo: Processo,
        caso: Caso | None,
        executor_id: int | None,
        manual: bool,
        exemplo: bool = True,
        *,
        processos_bloqueados: dict[int, tuple[Processo, Caso | None]] | None = None,
    ) -> Evento | None:
        """Grava o vínculo e cria o evento no caso, na transação em curso.

        O vínculo manual notifica na hora; o da captura agrega os avisos por
        caso até o fim da fonte (`_depois_da_fonte`). Processo sem caso só
        ganha o vínculo: evento e aviso exigem caso
        (docs/plano-processos-avulsos.md, §2).

        Todo vínculo vira exemplo `pertinente` (manual ou automático), salvo
        com `exemplo=False`: a importação da busca por parte grava o seu.
        """
        # A captura pode ter lido o processo antes de ele ganhar um caso.
        # Usa o mesmo bloqueio da associação para não perder eventos nessa corrida.
        # O mapa pertence apenas à transação de um lote de importação.
        # O bloqueio permanece no banco até commit/rollback.
        if processos_bloqueados is not None and processo.id in processos_bloqueados:
            processo, caso = processos_bloqueados[processo.id]
        else:
            atual = self.processos.bloquear(processo.id)
            if atual is None:
                raise ValidationException("Processo não encontrado", field="processo_id")
            processo = atual
            caso = self._caso_do_processo(processo)
            if processos_bloqueados is not None:
                processos_bloqueados[processo.id] = (processo, caso)
        self.repo.atualizar(
            comunicacao_id,
            {
                "id_processo": processo.id,
                "id_caso": caso.id if caso else None,
                "unidade_id": caso.unidade_id if caso else processo.unidade_id,
                "situacao": "vinculada",
                "data_situacao": agora_utc(),
                "id_vinculado_por": executor_id if manual else None,
            },
        )
        if exemplo:
            gravada = self.repo.find_by_id(comunicacao_id)
            assert gravada is not None
            self._rotular(
                self._dados_exemplo(gravada),
                "relevante",
                "vinculo_manual" if manual else "vinculo_automatico",
                executor_id if manual else None,
            )
        if caso is None:
            return None
        evento, novo = self._criar_evento(comunicacao_id, caso, executor_id)
        if novo:
            if manual:
                NotificacaoService().djen_publicacoes(caso, [evento], executor_id)
            else:
                _, lista, _ = self._avisos.setdefault(caso.id, (caso, [], executor_id))
                lista.append(evento)
        return evento

    def associar_processo_ao_caso(
        self, processo: Processo, caso: Caso, executor_id: int
    ) -> int:
        """Materializa o histórico sem alterar classificação ou autoria do vínculo."""
        novos = []
        for comunicacao_id in self.repo.vinculadas_ao_processo(processo.id):
            self.repo.atualizar(comunicacao_id, {"id_caso": caso.id})
            evento, novo = self._criar_evento(comunicacao_id, caso, executor_id)
            if novo:
                novos.append(evento)
        if novos:
            NotificacaoService().djen_publicacoes(caso, novos, executor_id)
        return len(novos)

    def _criar_evento(
        self, comunicacao_id: int, caso: Caso, executor_id: int | None
    ) -> tuple[Evento, bool]:
        """Evento `origem='djen'` da publicação (plano, §4). Um por publicação."""
        existente = self.eventos.find_by_djen_comunicacao(comunicacao_id)
        if existente is not None:
            return existente, False
        comunicacao = self.repo.find_by_id(comunicacao_id)
        assert comunicacao is not None
        cabecalho = " — ".join(
            djen_html.corrigir_caixa(p)
            for p in (comunicacao.nome_orgao, comunicacao.nome_classe)
            if p
        )
        corpo = djen_html.resumo(comunicacao.texto_plano or "", 500)
        # `descricao` e `tipo` de `eventos` são colunas legadas em latin1.
        descricao = (
            djen_html.para_latin1("\n\n".join(p for p in (cabecalho, corpo) if p))
            or None
        )
        evento_id = self.eventos.create(
            {
                "id_caso": caso.id,
                "num_evento": self.eventos.count_by_caso_id(caso.id) + 1,
                "tipo": djen_html.para_latin1(
                    (comunicacao.tipo_comunicacao or "Publicação no DJEN")[:50]
                ),
                "descricao": descricao,
                "data_evento": comunicacao.data_disponibilizacao,
                "data_criacao": agora_utc(),
                "id_criado_por": executor_id,
                "id_usuario_responsavel": caso.id_estagiario or caso.id_orientador,
                "status": True,
                "origem": "djen",
                "id_djen_comunicacao": comunicacao_id,
                "unidade_id": caso.unidade_id,
            }
        )
        evento = self.eventos.find_by_id(evento_id)
        assert evento is not None
        return evento, True

    def _ao_cancelar(
        self, comunicacao: ComunicacaoDJEN, executor_id: int | None
    ) -> None:
        """Publicação cancelada depois do vínculo: o evento fica, com o selo de
        cancelada (lido de `djen_comunicacoes.ativo`), e o caso é avisado."""
        logger.info(f"DJEN: publicação {comunicacao.id} cancelada no DJEN")
        evento = self.eventos.find_by_djen_comunicacao(comunicacao.id)
        caso = (
            self.casos.find_by_id(comunicacao.id_caso) if comunicacao.id_caso else None
        )
        if evento is not None and caso is not None:
            NotificacaoService().djen_cancelada(caso, evento, executor_id)

    def vincular(
        self, id: int, processo_id: Any, user: UserInfo, unidade_id: int
    ) -> dict[str, Any]:
        """Vínculo manual: grava, cria o evento e notifica na mesma transação."""
        if user.urole not in PAPEIS_GESTAO:
            raise ForbiddenException()
        comunicacao = self._visivel(id, user, unidade_id)
        self.acervo.contextos_operacao = {}
        if comunicacao.situacao == "vinculada":
            raise ValidationException("A publicação já está vinculada a um processo")
        if isinstance(processo_id, bool) or not isinstance(processo_id, int):
            raise ValidationException("Informe o processo", field="processo_id")
        processo = self.processos.find_by_id(processo_id)
        if processo is None or processo.unidade_id != unidade_id:
            # Mesma resposta para id inexistente, de outra unidade ou de outro NPJ.
            raise ValidationException("Processo não encontrado", field="processo_id")
        caso = self._caso_do_processo(processo)
        try:
            self._vincular(comunicacao.id, processo, caso, user.id, manual=True)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        logger.info(
            f"DJEN: publicação {id} vinculada ao processo {processo_id} por {user.id}"
        )
        return self.detalhe(id, user, unidade_id)

    def descartar(self, id: int, user: UserInfo, unidade_id: int) -> dict[str, Any]:
        """Descarta e classifica como irrelevante, preservando o acervo."""
        if user.urole not in PAPEIS_GESTAO:
            raise ForbiddenException()
        comunicacao = self._visivel(id, user, unidade_id)
        self.acervo.contextos_operacao = {}
        if comunicacao.situacao == "vinculada":
            raise ValidationException(
                "Publicação vinculada a um caso não pode ser descartada"
            )
        if comunicacao.situacao == "descartada":
            raise ValidationException("A publicação já foi descartada")
        try:
            self.repo.atualizar(
                comunicacao.id,
                {
                    "situacao": "descartada",
                    "data_situacao": agora_utc(),
                    "id_vinculado_por": user.id,
                },
            )
            self._rotular(
                self._dados_exemplo(comunicacao), "irrelevante", "descarte", user.id
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        logger.info(f"DJEN: publicação {id} descartada por {user.id}")
        return self.detalhe(id, user, unidade_id)

    # --- OABs monitoradas ---------------------------------------------------

    @staticmethod
    def _oab_dict(oab: OabMonitorada) -> dict[str, Any]:
        return {**oab.__dict__, "rotulo": oab.rotulo}

    def listar_oabs(self, unidade_id: int) -> list[dict[str, Any]]:
        return [self._oab_dict(o) for o in self.oabs.listar(unidade_id)]

    def _oab_da_unidade(self, id: int, unidade_id: int) -> OabMonitorada:
        oab = self.oabs.find_by_id(id)
        if oab is None or oab.unidade_id != unidade_id:
            raise NotFoundException(resource="OAB", resource_id=id)
        return oab

    @staticmethod
    def _numero_uf(dados: dict[str, Any]) -> tuple[str, str]:
        numero = dados.get("numero_oab")
        uf = dados.get("uf_oab")
        if isinstance(numero, int) and not isinstance(numero, bool):
            numero = str(numero)
        if not isinstance(numero, str):
            raise ValidationException("Informe o número da OAB", field="numero_oab")
        # Aceita pontuação de digitação ("123.456"); qualquer outra coisa é erro.
        digitos = "".join(c for c in numero if c not in " .-").lstrip("0")
        if not (digitos.isascii() and digitos.isdigit()) or len(digitos) > 10:
            raise ValidationException(
                "Número da OAB inválido (só dígitos)", field="numero_oab"
            )
        if not isinstance(uf, str) or uf.strip().upper() not in UFS:
            raise ValidationException("UF da OAB inválida", field="uf_oab")
        return digitos, uf.strip().upper()

    @staticmethod
    def _unidade_escolhida(dados: dict[str, Any], user: UserInfo, padrao: int) -> int:
        if "unidade_id" not in dados or dados["unidade_id"] is None:
            return padrao
        valor = dados["unidade_id"]
        # Só as unidades do próprio admin: id de outra unidade ou de outro NPJ
        # recebe a mesma resposta.
        if (
            isinstance(valor, bool)
            or not isinstance(valor, int)
            or valor not in {u.id for u in user.unidades}
        ):
            raise ValidationException("Unidade não encontrada", field="unidade_id")
        return valor

    @staticmethod
    def _id_usuario(dados: dict[str, Any]) -> int | None:
        valor = dados.get("id_usuario")
        if valor is None:
            return None
        if isinstance(valor, bool) or not isinstance(valor, int):
            raise ValidationException("Usuário não encontrado", field="id_usuario")
        exigir_existente("usuarios", valor, "id_usuario")
        return valor

    def criar_oab(
        self, dados: dict[str, Any], user: UserInfo, unidade_id: int
    ) -> dict[str, Any]:
        numero, uf = self._numero_uf(dados)
        ativo = dados.get("ativo", True)
        if not isinstance(ativo, bool):
            raise ValidationException("Valor inválido", field="ativo")
        registro = {
            "numero_oab": numero,
            "uf_oab": uf,
            "id_usuario": self._id_usuario(dados),
            "unidade_id": self._unidade_escolhida(dados, user, unidade_id),
            "ativo": ativo,
            "criado_em": agora_utc(),
            "id_criado_por": user.id,
        }
        if self.oabs.existe(numero, uf):
            raise ValidationException(
                f"A OAB {numero}/{uf} já está cadastrada", field="numero_oab"
            )
        try:
            novo_id = self.oabs.criar(registro)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        logger.info(f"DJEN: OAB {numero}/{uf} cadastrada por {user.id}")
        oab = self.oabs.find_by_id(novo_id)
        assert oab is not None
        return self._oab_dict(oab)

    def atualizar_oab(
        self, id: int, dados: dict[str, Any], user: UserInfo, unidade_id: int
    ) -> dict[str, Any]:
        atual = self._oab_da_unidade(id, unidade_id)
        mudancas: dict[str, Any] = {}
        if "numero_oab" in dados or "uf_oab" in dados:
            numero, uf = self._numero_uf(
                {
                    "numero_oab": dados.get("numero_oab", atual.numero_oab),
                    "uf_oab": dados.get("uf_oab", atual.uf_oab),
                }
            )
            if self.oabs.existe(numero, uf, ignorar_id=id):
                raise ValidationException(
                    f"A OAB {numero}/{uf} já está cadastrada", field="numero_oab"
                )
            mudancas.update(numero_oab=numero, uf_oab=uf)
        if "id_usuario" in dados:
            mudancas["id_usuario"] = self._id_usuario(dados)
        if "unidade_id" in dados:
            mudancas["unidade_id"] = self._unidade_escolhida(
                dados, user, atual.unidade_id
            )
        if "ativo" in dados:
            if not isinstance(dados["ativo"], bool):
                raise ValidationException("Valor inválido", field="ativo")
            mudancas["ativo"] = dados["ativo"]
        if mudancas:
            try:
                self.oabs.atualizar(id, mudancas)
                self.session.commit()
            except Exception:
                self.session.rollback()
                raise
            logger.info(f"DJEN: OAB {id} alterada por {user.id}: {sorted(mudancas)}")
        oab = self.oabs.find_by_id(id)
        assert oab is not None
        return self._oab_dict(oab)

    def remover_oab(self, id: int, user: UserInfo, unidade_id: int) -> None:
        """Apaga só o cadastro; as publicações já capturadas ficam."""
        oab = self._oab_da_unidade(id, unidade_id)
        try:
            self.oabs.apagar(id)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        logger.info(f"DJEN: OAB {oab.rotulo} removida por {user.id}")

    def sugestoes_oab(self, unidade_id: int) -> list[dict[str, Any]]:
        """`usuarios.oab` de orientadores, professores e admins da unidade.

        É texto livre: só entra o que tiver número e UF reconhecíveis.
        """
        cadastradas = {(o.numero_oab, o.uf_oab) for o in self.oabs.listar()}
        sugestoes = []
        for usuario in self.oabs.usuarios_com_oab(unidade_id, PAPEIS_SUGESTAO_OAB):
            separada = separar_oab(usuario["oab"])
            if separada is None:
                continue
            sugestoes.append(
                {
                    "id_usuario": usuario["id"],
                    "nome": usuario["nome"],
                    "urole": usuario["urole"],
                    "oab": usuario["oab"],
                    "numero_oab": separada[0],
                    "uf_oab": separada[1],
                    "cadastrada": separada in cadastradas,
                }
            )
        return sugestoes

    # --- captura ------------------------------------------------------------

    def _consultar_oab(
        self, oab: OabMonitorada, janela_dias: int, resultado: ResultadoCaptura
    ) -> None:
        fim = hoje_brasilia()
        inicio = fim - timedelta(days=janela_dias)
        for item in self._capturar(
            self.client,
            "oab",
            {"oab": oab.rotulo, "de": inicio.isoformat(), "ate": fim.isoformat()},
            oab.unidade_id,
            None,
            lambda: self.client.buscar_por_oab(oab.numero_oab, oab.uf_oab, inicio, fim),
        ):
            self.registrar(
                item,
                resultado,
                unidade_padrao=oab.unidade_id,
                oab_origem=oab.rotulo,
            )

    def _consultar_processo(
        self, processo: Processo, resultado: ResultadoCaptura, executor_id: int | None
    ) -> None:
        assert processo.numero_cnj
        limite_anterior = self.client.max_paginas
        self.client.max_paginas = None
        try:
            for item in self._capturar(
                self.client,
                "processo",
                {"numero": processo.numero_cnj, "historico_completo": True},
                processo.unidade_id,
                executor_id,
                lambda: self.client.buscar_por_processo(processo.numero_cnj),
            ):
                if item.numero_processo != processo.numero_cnj:
                    continue
                self.registrar(item, resultado, processo=processo, executor_id=executor_id)
        finally:
            self.client.max_paginas = limite_anterior
        self.processos.update(
            processo.id, {"djen_pendente": False, "djen_consultado_em": agora_utc()}
        )

    def buscar_processo(
        self, processo_id: int, user: UserInfo, unidade_id: int
    ) -> dict[str, Any]:
        """Busca todo o histórico do processo, sem esperar a rotina."""
        processo = self.processos.find_by_id(processo_id)
        if processo is None or processo.unidade_id != unidade_id:
            raise NotFoundException(resource="Processo", resource_id=processo_id)
        if not processo.numero_cnj:
            raise ValidationException(
                "O número do processo não está no padrão CNJ (20 dígitos).",
                field="numero",
            )
        resultado = ResultadoCaptura()
        try:
            self._consultar_processo(processo, resultado, executor_id=user.id)
            self._depois_da_fonte()
            self.session.commit()
        except DJENError as erro:
            self.session.rollback()
            self._descartar_pendencias()
            logger.warning(f"DJEN: busca do processo {processo_id} falhou: {erro}")
            raise BusinessLogicException(
                "O DJEN não respondeu. As páginas já recebidas permanecem no acervo. Tente novamente.",
                "DJEN_INDISPONIVEL",
            ) from erro
        except Exception:
            self.session.rollback()
            self._descartar_pendencias()
            raise
        atualizado = self.processos.find_by_id(processo_id)
        return {
            "novas": resultado.novas,
            "atualizadas": resultado.atualizadas,
            "vinculadas": resultado.vinculadas,
            "djen_consultado_em": atualizado.djen_consultado_em if atualizado else None,
        }

    def _depois_da_fonte(self) -> None:
        """Avisos agregados da fonte, na mesma transação que os eventos."""
        avisos, self._avisos = self._avisos, {}
        servico = NotificacaoService()
        for caso, eventos, executor in avisos.values():
            servico.djen_publicacoes(caso, eventos, executor)

    def _descartar_pendencias(self) -> None:
        self._avisos = {}

    def sincronizar(
        self, janela_dias: int | None = None, max_processos: int | None = None
    ) -> dict[str, Any]:
        """Uma execução da rotina para o tenant ativo, uma de cada vez por NPJ.

        O cron e o botão "Rodar rotina agora" podem coincidir; a segunda
        execução é recusada em vez de consultar e gravar tudo em dobro.
        """
        with self.sincronizacoes.trava_da_rotina() as livre:
            if not livre:
                raise BusinessLogicException(
                    "A rotina do DJEN já está rodando para este NPJ. Aguarde alguns minutos.",
                    "DJEN_EM_EXECUCAO",
                )
            from gestaolegal.services.djen_monitoramento_service import DjenMonitoramentoService
            return DjenMonitoramentoService(self).executar(janela_dias)

    def _aplicar_retencao(self) -> int:
        """O acervo e as decisões ficam disponíveis até exclusão explícita."""
        return 0

    @staticmethod
    def _parametros_busca(
        nomes: list[Any], de: Any, ate: Any, tribunais: Any
    ) -> tuple[list[str], date, date, list[str]]:
        limpos: list[str] = []
        for nome in nomes:
            if not isinstance(nome, str):
                raise ValidationException("Nome inválido", field="nome")
            nome = " ".join(nome.split())
            if nome and nome.lower() not in {n.lower() for n in limpos}:
                limpos.append(nome[:150])
        if not limpos or any(len(n) < 3 for n in limpos):
            raise ValidationException(
                "Informe o nome da parte (3 letras ou mais)", field="nome"
            )
        if len(limpos) > BUSCA_PARTE_MAX_NOMES:
            raise ValidationException(
                f"No máximo {BUSCA_PARTE_MAX_NOMES} nomes por busca", field="nome"
            )
        datas = []
        for campo, valor in (("de", de), ("ate", ate)):
            if isinstance(valor, date):
                datas.append(valor)
                continue
            try:
                datas.append(date.fromisoformat(str(valor or "").strip()))
            except ValueError as erro:
                raise ValidationException(
                    "Data inválida (use AAAA-MM-DD)", field=campo
                ) from erro
        inicio, fim = datas
        if fim < inicio:
            raise ValidationException(
                "O fim do período vem antes do início", field="ate"
            )
        if (fim - inicio).days > BUSCA_PARTE_MAX_DIAS:
            raise ValidationException(
                f"O período máximo é de {BUSCA_PARTE_MAX_DIAS} dias", field="ate"
            )
        # Aceita uma sigla ou uma lista; vazio = todos os tribunais.
        if tribunais is None or isinstance(tribunais, str):
            tribunais = [tribunais] if tribunais else []
        if not isinstance(tribunais, list):
            raise ValidationException("Tribunal inválido", field="tribunal")
        siglas: list[str] = []
        for sigla in tribunais:
            if not isinstance(sigla, str):
                raise ValidationException("Tribunal inválido", field="tribunal")
            sigla = sigla.strip().upper()[:30]
            if sigla and sigla not in siglas:
                siglas.append(sigla)
        if len(siglas) > BUSCA_PARTE_MAX_TRIBUNAIS:
            raise ValidationException(
                f"No máximo {BUSCA_PARTE_MAX_TRIBUNAIS} tribunais por busca",
                field="tribunal",
            )
        return limpos, inicio, fim, siglas

    def _consultar_partes(
        self, nomes: list[str], inicio: date, fim: date, tribunais: list[str]
    ) -> tuple[list[Comunicacao], bool, dict[int, str]]:
        """Publicações dos nomes no período, sem repetir.

        (itens, truncado, termos): `termos` dá o primeiro nome que trouxe
        cada publicação (`termo_busca` do banco de exemplos).
        """
        cliente = DJENClient(
            base_url=self.client.base_url,
            transporte=self.client._transporte,
            dormir=self.client._dormir,
            max_paginas=BUSCA_PARTE_MAX_PAGINAS,
        )
        vistos: dict[int, Comunicacao] = {}
        termos: dict[int, str] = {}
        truncado = False
        try:
            for nome in nomes:
                for tribunal in tribunais or [None]:
                    itens = self._capturar(
                        cliente,
                        "parte",
                        {
                            "nome": nome,
                            "de": inicio.isoformat(),
                            "ate": fim.isoformat(),
                            "tribunal": tribunal,
                        },
                        RequestContext.get_unidade_ativa(),
                        RequestContext.get_current_user().id,
                        lambda: cliente.buscar_por_parte(nome, inicio, fim, tribunal),
                    )
                    truncado = truncado or cliente.truncado
                    for item in itens:
                        vistos.setdefault(item.id_djen, item)
                        termos.setdefault(item.id_djen, nome)
        except DJENError as erro:
            logger.warning(f"DJEN: busca por parte falhou: {erro}")
            raise BusinessLogicException(
                "O DJEN não respondeu. As páginas já recebidas permanecem no acervo. Tente novamente.",
                "DJEN_INDISPONIVEL",
            ) from erro
        itens = sorted(
            vistos.values(),
            key=lambda c: (c.data_disponibilizacao, c.id_djen),
            reverse=True,
        )
        return itens, truncado, termos

    def _processos_da_unidade(
        self, numeros: set[str], unidade_id: int
    ) -> dict[str, Processo]:
        """Processo ativo da unidade para cada número CNJ (ambíguo não casa)."""
        resultado: dict[str, Processo] = {}
        for numero in numeros:
            achados = [
                p
                for p in self.processos.find_by_numero_cnj(numero)
                if p.unidade_id == unidade_id
            ]
            if len(achados) == 1:
                resultado[numero] = achados[0]
        return resultado

    def busca_parte(
        self,
        nomes: list[Any],
        de: Any,
        ate: Any,
        tribunais: Any,
        user: UserInfo,
        unidade_id: int,
    ) -> dict[str, Any]:
        """Consulta o DJEN por nome da parte e diz o que já existe no NPJ."""
        if user.urole not in PAPEIS_GESTAO:
            raise ForbiddenException()
        nomes, inicio, fim, tribunais = self._parametros_busca(
            nomes, de, ate, tribunais
        )
        itens, truncado, _ = self._consultar_partes(nomes, inicio, fim, tribunais)
        gravadas = self.repo.por_ids_djen([i.id_djen for i in itens])
        exemplos = self.acervo.por_ids_djen([i.id_djen for i in itens])
        processos = self._processos_da_unidade(
            {i.numero_processo for i in itens}, unidade_id
        )
        resultado = []
        for item in itens:
            gravada = gravadas.get(item.id_djen)
            processo = processos.get(item.numero_processo)
            resultado.append(
                {
                    "id_djen": item.id_djen,
                    "data_disponibilizacao": item.data_disponibilizacao,
                    "numero_processo": item.numero_processo,
                    "numero_processo_mascara": item.numero_processo_mascara
                    or mascarar_cnj(item.numero_processo),
                    "sigla_tribunal": item.sigla_tribunal,
                    "nome_orgao": djen_html.corrigir_caixa(item.nome_orgao),
                    "tipo_comunicacao": item.tipo_comunicacao,
                    "tipo_documento": item.tipo_documento,
                    "nome_classe": djen_html.corrigir_caixa(item.nome_classe),
                    "destinatarios": item.destinatarios,
                    "resumo": djen_html.resumo(
                        djen_html.texto_plano(item.texto) or "", 300
                    ),
                    "link": item.link,
                    "ativo": item.ativo,
                    "ja_no_banco": gravada is not None,
                    # Só a publicação da unidade ativa vira link.
                    "publicacao_id": gravada.id
                    if gravada is not None and gravada.unidade_id == unidade_id
                    else None,
                    "processo_id": processo.id if processo else None,
                    "processo_id_caso": processo.id_caso if processo else None,
                    # Rótulo no banco de exemplos (nulo = ainda sem exemplo).
                    "rotulo": exemplos[item.id_djen]["rotulo"]
                    if item.id_djen in exemplos
                    else None,
                }
            )
        return {
            "items": resultado,
            "total": len(resultado),
            "truncado": truncado,
            "nomes": nomes,
            # Em ISO: a tela devolve o período igual na importação.
            "de": inicio.isoformat(),
            "ate": fim.isoformat(),
            "tribunais": tribunais,
        }

    def importar_busca(
        self, corpo: dict[str, Any], user: UserInfo, unidade_id: int
    ) -> dict[str, Any]:
        """Grava as publicações escolhidas na busca por parte.

        O conteúdo vem do acervo persistido, nunca do corpo da requisição. Cada publicação é vinculada ao processo da unidade com o
        mesmo número; sem processo, cria-se um processo sem caso com a parte
        informada (`id_atendido`). Tudo numa transação.
        """
        from gestaolegal.services.processo_service import ProcessoService

        if user.urole not in PAPEIS_GESTAO:
            raise ForbiddenException()
        ids = self._ids_selecionados(corpo)
        id_atendido = corpo.get("id_atendido")
        if id_atendido is not None:
            # Conferido antes de consultar o DJEN; mesma resposta para id
            # inexistente, de outra unidade ou de outro NPJ.
            if (
                isinstance(id_atendido, bool)
                or not isinstance(id_atendido, int)
                or AtendidoRepository().find_by_id(id_atendido, unidade_id=unidade_id)
                is None
            ):
                raise ValidationException("Parte não encontrada", field="id_atendido")
        sem_parte = corpo.get("sem_parte", False)
        if not isinstance(sem_parte, bool) or (sem_parte and id_atendido is not None):
            raise ValidationException("Opção sem parte inválida", field="sem_parte")
        especie = corpo.get("especie") or ESPECIE_IMPORTADA
        if not isinstance(especie, str) or len(especie) > 25:
            raise ValidationException("Espécie inválida", field="especie")

        registros = self.acervo.selecionadas(ids, unidade_id)
        from gestaolegal.services.djen_contexto_service import DjenContextoService
        self.acervo.contextos_operacao = DjenContextoService().preparar_operacao(registros, corpo, unidade_id)
        itens = [self._comunicacao_salva(r) for r in registros]
        publicacoes_salvas = {r["id_djen"]: r["id"] for r in registros}
        escolhidos = itens
        nao_encontradas = sorted(set(ids) - {i.id_djen for i in escolhidos})
        if nao_encontradas:
            raise ValidationException(
                "Publicação não encontrada na unidade", field="ids"
            )
        processos = self._processos_da_unidade(
            {i.numero_processo for i in escolhidos}, unidade_id
        )
        sem_processo = sorted({i.numero_processo for i in escolhidos} - set(processos))
        if sem_processo and id_atendido is None and not sem_parte:
            raise ValidationException(
                "Informe a parte do processo sem caso para os números sem processo: "
                + ", ".join(mascarar_cnj(n) or n for n in sem_processo),
                field="id_atendido",
            )

        resultado = ResultadoCaptura()
        criados: list[int] = []
        try:
            comunicacoes = self.repo.por_publicacoes(list(publicacoes_salvas.values()))
            if any(c["unidade_id"] != unidade_id for c in comunicacoes.values()):
                raise ValidationException(
                    "Publicação vinculada a outra unidade", field="ids"
                )
            servico = ProcessoService()
            for numero in sem_processo:
                if len(numero) != 20:
                    raise ValidationException(
                        f"Número {numero} fora do padrão CNJ; cadastre o processo à mão",
                        field="ids",
                    )
                exemplo = next(i for i in escolhidos if i.numero_processo == numero)
                dados = ProcessoDjenInput(
                    especie=especie,
                    numero=exemplo.numero_processo_mascara
                    or mascarar_cnj(numero)
                    or numero,
                    # `processos` tem colunas legadas em latin1 no MySQL.
                    vara=djen_html.para_latin1(
                        djen_html.corrigir_caixa(exemplo.nome_orgao)
                    )[:200]
                    if exemplo.nome_orgao
                    else None,
                    identificacao=djen_html.para_latin1(
                        djen_html.corrigir_caixa(exemplo.nome_classe)
                    ),
                    partes=[ParteInput(id_atendido=id_atendido)] if id_atendido is not None else [],
                )
                novo = servico.criar_sem_caso(dados, user, unidade_id)
                processos[numero] = self.processos.find_by_id(novo["id"])
                criados.append(novo["id"])
            processos_bloqueados = {}
            for item in escolhidos:
                pid = publicacoes_salvas[item.id_djen]
                gravada = comunicacoes.get(pid)
                if gravada is None:
                    cid = self.repo.criar(
                        dict(id_publicacao=pid, situacao="pendente", unidade_id=unidade_id)
                    )
                    gravada = dict(id=cid, situacao="pendente")
                    comunicacoes[pid] = gravada
                    resultado.novas += 1
                if gravada["situacao"] != "vinculada":
                    alvo = processos[item.numero_processo]
                    manual = gravada["situacao"] == "descartada"
                    self._vincular(
                        gravada["id"],
                        alvo,
                        None,
                        user.id,
                        manual=manual,
                        exemplo=manual,
                        processos_bloqueados=processos_bloqueados,
                    )
                    gravada["situacao"] = "vinculada"
                    resultado.vinculadas += 1
            self.acervo.classificar_lote(
                list(publicacoes_salvas.values()), "relevante", "busca_parte", user.id
            )
            self._depois_da_fonte()
            self.session.commit()
        except Exception:
            self.session.rollback()
            self._descartar_pendencias()
            raise
        logger.info(
            f"DJEN: busca por parte importou {resultado.novas} publicação(ões) "
            f"por {user.id}; {len(criados)} processo(s) sem caso criado(s)"
        )
        return {
            "novas": resultado.novas,
            "atualizadas": resultado.atualizadas,
            "vinculadas": resultado.vinculadas,
            "processos_criados": criados,
            "nao_encontradas": nao_encontradas,
        }

    @classmethod
    def _selecao_da_busca(
        cls, corpo: dict[str, Any]
    ) -> tuple[list[str], date, date, list[str], list[int]]:
        """Parâmetros da busca e ids escolhidos (importar e não pertinentes)."""
        nomes = corpo.get("nome")
        nomes = nomes if isinstance(nomes, list) else [nomes]
        nomes, inicio, fim, tribunais = cls._parametros_busca(
            nomes, corpo.get("de"), corpo.get("ate"), corpo.get("tribunal")
        )
        ids = corpo.get("ids")
        if (
            not isinstance(ids, list)
            or not ids
            or len(ids) > IMPORTACAO_MAX_ITENS
            or any(isinstance(i, bool) or not isinstance(i, int) for i in ids)
        ):
            raise ValidationException(
                f"Escolha de 1 a {IMPORTACAO_MAX_ITENS} publicações", field="ids"
            )
        return nomes, inicio, fim, tribunais, ids

    def marcar_nao_pertinentes(
        self, corpo: dict[str, Any], user: UserInfo
    ) -> dict[str, Any]:
        retorno = self.classificar_acervo(
            {**corpo, "rotulo": "irrelevante"}, user, RequestContext.get_unidade_ativa()
        )
        return {
            "marcadas": retorno["classificadas"],
            "nao_revisadas": 0,
            "nao_encontradas": [],
        }

    @staticmethod
    def _ids_selecionados(corpo):
        ids = corpo.get("ids")
        if (
            not isinstance(ids, list)
            or not 1 <= len(ids) <= IMPORTACAO_MAX_ITENS
            or any(type(i) is not int or i <= 0 for i in ids)
        ):
            raise ValidationException(
                f"Escolha de 1 a {IMPORTACAO_MAX_ITENS} publicações", field="ids"
            )
        return sorted(set(ids))

    def classificar_acervo(self, corpo, user, unidade_id):
        if user.urole not in PAPEIS_GESTAO:
            raise ForbiddenException()
        ids = self._ids_selecionados(corpo)
        rotulo = corpo.get("rotulo")
        if rotulo not in (*ROTULOS_EXPLICITOS, "nao_classificado"):
            raise ValidationException("Classificação inválida", field="rotulo")
        try:
            registros = self.acervo.selecionadas(ids, unidade_id)
            if len(registros) != len(ids):
                raise ValidationException(
                    "Publicação não encontrada na unidade", field="ids"
                )
            for registro in registros:
                self.acervo.classificar(
                    registro["id"], rotulo, "classificacao", user.id
                )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return {"classificadas": len(registros)}

    def descartar_acervo(self, corpo, user, unidade_id):
        if user.urole not in PAPEIS_GESTAO:
            raise ForbiddenException()
        ids = self._ids_selecionados(corpo)
        try:
            registros = self.acervo.selecionadas(ids, unidade_id)
            from gestaolegal.services.djen_contexto_service import DjenContextoService
            self.acervo.contextos_operacao = DjenContextoService().preparar_operacao(registros, corpo, unidade_id)
            if len(registros) != len(ids):
                raise ValidationException(
                    "Publicação não encontrada na unidade", field="ids"
                )
            for registro in registros:
                comunicacao = self.repo.find_by_id_djen(registro["id_djen"])
                if comunicacao and (
                    comunicacao.unidade_id != unidade_id
                    or comunicacao.situacao == "vinculada"
                ):
                    raise ValidationException(
                        "Publicação vinculada ou de outra unidade não pode ser descartada"
                    )
                if comunicacao is None:
                    cid = self.repo.criar(
                        dict(
                            id_publicacao=registro["id"],
                            unidade_id=unidade_id,
                            situacao="pendente",
                        )
                    )
                else:
                    cid = comunicacao.id
                self.repo.atualizar(
                    cid,
                    dict(
                        situacao="descartada",
                        data_situacao=agora_utc(),
                        id_vinculado_por=user.id,
                    ),
                )
                self.acervo.classificar(
                    registro["id"], "irrelevante", "descarte", user.id
                )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return {"descartadas": len(registros)}

    @staticmethod
    def _dados_publicacao(item):
        from dataclasses import asdict

        dados = asdict(item)
        dados["texto_html"] = dados.pop("texto")
        dados["texto_plano"] = djen_html.texto_plano(dados["texto_html"])
        dados["nome_orgao"] = djen_html.corrigir_caixa(item.nome_orgao)
        dados["nome_classe"] = djen_html.corrigir_caixa(item.nome_classe)
        return dados

    @staticmethod
    def _comunicacao_salva(registro):
        from dataclasses import fields

        dados = {
            f.name: registro[f.name] for f in fields(Comunicacao) if f.name in registro
        }
        dados["texto"] = registro["texto_html"]
        return Comunicacao(**dados)

    def _capturar(self, cliente, origem, parametros, unidade, executor, consultar):
        consulta = self.acervo.iniciar_consulta(origem, parametros, unidade, executor)
        self.session.commit()

        encontradas = novas = 0
        def pagina(itens):
            nonlocal encontradas, novas
            try:
                anteriores = self.acervo.por_ids_djen([item.id_djen for item in itens])
                self._recebidas_antes.update(anteriores)
                for item in itens:
                    anterior_item = self.repo.find_by_id_djen(item.id_djen)
                    if anterior_item and (
                        anterior_item.ativo != item.ativo
                        or anterior_item.motivo_cancelamento != item.motivo_cancelamento
                    ):
                        self._alteracoes_captura.add(item.id_djen)
                        if (
                            anterior_item.ativo
                            and not item.ativo
                            and anterior_item.id_caso
                        ):
                            self._ao_cancelar(anterior_item, executor)
                    pid = self.acervo.guardar(self._dados_publicacao(item))
                    self.acervo.resultado(consulta, pid)
                    if origem == "parte":
                        self.registrar(item, ResultadoCaptura(), unidade_padrao=unidade,
                            executor_id=executor, somente_com_processo=True)
                if origem == "parte":
                    self._depois_da_fonte()
                quantidade = len(itens)
                novas_pagina = sum(item.id_djen not in anteriores for item in itens)
                self.acervo.atualizar_consulta(consulta, encontradas=encontradas + quantidade, novas=novas + novas_pagina)
                self.session.commit()
                encontradas += quantidade
                novas += novas_pagina
            except Exception:
                self.session.rollback()
                self._descartar_pendencias()
                raise

        anterior = cliente.ao_receber_pagina
        cliente.ao_receber_pagina = pagina
        try:
            itens = consultar()
            self.acervo.finalizar_consulta(
                consulta, "parcial" if cliente.truncado else "ok"
            )
            self.session.commit()
            return itens
        except Exception as erro:
            self.session.rollback()
            self.acervo.atualizar_consulta(consulta, mensagem=str(erro)[:2000])
            self.acervo.finalizar_consulta(consulta, "erro")
            self.session.commit()
            raise
        finally:
            cliente.ao_receber_pagina = anterior

    # --- banco de exemplos ----------------------------------------------------
    # docs/plano-processos-avulsos.md, "Banco de exemplos"; plano-djen.md, §8.

    @staticmethod
    def _dados_exemplo(fonte: Comunicacao | ComunicacaoDJEN) -> dict[str, Any]:
        """Campos do exemplo, da consulta ao DJEN ou da publicação gravada."""
        if isinstance(fonte, Comunicacao):
            texto = djen_html.texto_plano(fonte.texto) or None
        else:
            texto = fonte.texto_plano or djen_html.texto_plano(fonte.texto_html) or None
        return {
            "id_djen": fonte.id_djen,
            "numero_processo": fonte.numero_processo,
            "data_disponibilizacao": fonte.data_disponibilizacao,
            "sigla_tribunal": fonte.sigla_tribunal,
            "nome_orgao": djen_html.corrigir_caixa(fonte.nome_orgao),
            "nome_classe": djen_html.corrigir_caixa(fonte.nome_classe),
            "tipo_comunicacao": fonte.tipo_comunicacao,
            "tipo_documento": fonte.tipo_documento,
            "destinatarios": fonte.destinatarios or [],
            "texto_plano": texto,
        }

    def _rotular(
        self,
        dados: dict[str, Any],
        rotulo: str,
        origem: str,
        rotulado_por: int | None,
        termo_busca: str | None = None,
        existente: Any = _CONSULTAR,
    ) -> bool:
        """Classifica na mesma transação da operação e registra o histórico.

        A captura apenas cria o estado inicial. Decisões automáticas nunca
        substituem uma avaliação anterior.
        """
        registro = self.acervo.por_ids_djen([dados["id_djen"]]).get(dados["id_djen"])
        pid = registro["id"] if registro else self.acervo.guardar(dados)
        if rotulo == "nao_classificado":
            return registro is None
        return self.acervo.classificar(
            pid, rotulo, origem, rotulado_por, automatico=origem == "vinculo_automatico"
        )

    def _rotular_busca(
        self,
        itens: list[Comunicacao],
        escolhidos: list[Comunicacao],
        termos: dict[int, str],
        rotulo: str,
        user_id: int,
    ) -> int:
        """Rótulo das escolhidas; as demais da consulta, ainda sem exemplo,
        entram como não revisadas. Devolve quantas não revisadas entraram."""
        existentes = self.acervo.por_ids_djen([i.id_djen for i in itens])
        ids_escolhidos = {i.id_djen for i in escolhidos}
        for item in escolhidos:
            self._rotular(
                self._dados_exemplo(item),
                rotulo,
                "busca_parte",
                user_id,
                termo_busca=termos.get(item.id_djen),
                existente=existentes.get(item.id_djen),
            )
        nao_revisadas = 0
        for item in itens:
            if item.id_djen in ids_escolhidos or item.id_djen in existentes:
                continue
            self._rotular(
                self._dados_exemplo(item),
                "nao_classificado",
                "busca_parte",
                None,
                termo_busca=termos.get(item.id_djen),
                existente=None,
            )
            nao_revisadas += 1
        return nao_revisadas

    def resumo_exemplos(self) -> dict[str, Any]:
        """Contagens do banco de exemplos do NPJ (admin)."""
        por_rotulo = {r: 0 for r in ROTULOS_EXPLICITOS + ("nao_classificado",)}
        por_origem: dict[str, int] = {}
        total = com_texto = 0
        for linha in self.acervo.contagens():
            por_rotulo[linha["rotulo"]] = (
                por_rotulo.get(linha["rotulo"], 0) + linha["total"]
            )
            por_origem[linha["origem"]] = (
                por_origem.get(linha["origem"], 0) + linha["total"]
            )
            total += linha["total"]
            com_texto += linha["com_texto"]
        return {
            "total": total,
            "por_rotulo": por_rotulo,
            "por_origem": por_origem,
            "com_texto": com_texto,
            "retencao_dias": None,
            "retencao_nao_revisadas_dias": None,
        }

    def exportar_exemplos(self, incluir_nao_revisadas: bool = False):
        """Exemplos em JSON Lines, um por linha (admin).

        Por padrão só os rotulados; as não revisadas entram a pedido.
        """
        rotulos = ROTULOS_EXPLICITOS + (
            ("nao_classificado",) if incluir_nao_revisadas else ()
        )
        for exemplo in self.acervo.para_exportar(rotulos):
            registro = {campo: exemplo.get(campo) for campo in CAMPOS_EXPORTACAO}
            yield json.dumps(registro, ensure_ascii=False, default=_serializar) + "\n"


def _serializar(valor: Any) -> str:
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    raise TypeError(f"{type(valor).__name__} não serializável")
