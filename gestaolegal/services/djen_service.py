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
from gestaolegal.models.user import UserInfo
from gestaolegal.repositories.caso_repository import CasoRepository
from gestaolegal.repositories.djen_repository import (
    DjenComunicacaoRepository,
    DjenOabRepository,
    DjenSincronizacaoRepository,
)
from gestaolegal.repositories.evento_repository import EventoRepository
from gestaolegal.repositories.processo_repository import ProcessoRepository
from gestaolegal.repositories.tenant_repository import TenantRepository
from gestaolegal.services.notificacao_service import NotificacaoService
from gestaolegal.services.referencias import exigir_existente
from gestaolegal.utils.cnj import mascarar_cnj

logger = logging.getLogger(__name__)

# Permissões (plano, §7).
PAPEIS_GESTAO = ("admin", "prof", "orient")  # sem caso, vincular, descartar
PAPEIS_UNIDADE = PAPEIS_GESTAO + ("colab_proj",)  # lista de toda a unidade
PAPEIS_PARTICIPANTE = ("estag_direito", "colab_ext")  # só casos de que participam

# Só o admin do NPJ mantém a lista de OABs monitoradas (plano, Decisões, 1).
PAPEIS_OABS = ("admin",)
# De quem o `usuarios.oab` aparece como sugestão na tela das OABs.
PAPEIS_SUGESTAO_OAB = ("orient", "prof", "admin")
UFS = frozenset(
    "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split()
)

MSG_DESLIGADO = "A busca no DJEN não está habilitada para este NPJ."


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


def link_certidao(hash_: str | None) -> str | None:
    if not hash_:
        return None
    return f"{Config.DJEN_API_URL}/api/v1/comunicacao/{hash_}/certidao"


class DJENService:
    def __init__(self, client: DJENClient | None = None):
        self.client = client or DJENClient(base_url=Config.DJEN_API_URL)
        self.repo = DjenComunicacaoRepository()
        self.sincronizacoes = DjenSincronizacaoRepository()
        self.processos = ProcessoRepository()
        self.casos = CasoRepository()
        self.tenants = TenantRepository()
        self.eventos = EventoRepository()
        self.oabs = DjenOabRepository()
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
                self.casos.find_by_id(comunicacao.id_caso) if comunicacao.id_caso else None
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
        if ultima is None:
            return {"ultima": None, "atrasada": True}
        referencia = (ultima.fim or ultima.inicio).date()
        return {
            "ultima": ultima.__dict__,
            "atrasada": dias_uteis_entre(referencia, date.today()) > 2,
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
    ) -> None:
        """Upsert por `id_djen` no tenant ativo (idempotente).

        `processo` vem da busca pelo número; sem ele, casa pelo `numero_cnj`.
        Publicação já gravada só atualiza o cancelamento.
        """
        agora = datetime.now()
        existente = self.repo.find_by_id_djen(item.id_djen)
        if existente is not None:
            mudou = existente.ativo != item.ativo or (
                existente.motivo_cancelamento or None
            ) != (item.motivo_cancelamento or None)
            if mudou:
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
            if existente.situacao == "pendente" and existente.id_caso is None:
                alvo = processo or self._casar(existente.numero_processo)
                caso = self._caso_do_processo(alvo) if alvo else None
                if alvo and caso:
                    self._vincular(existente.id, alvo, caso, executor_id, manual=False)
                    resultado.vinculadas += 1
            return

        alvo = processo if processo is not None else self._casar(item.numero_processo)
        caso = self._caso_do_processo(alvo) if alvo else None
        if caso is None:
            alvo = None
        unidade_id = caso.unidade_id if caso else unidade_padrao
        if unidade_id is None:
            logger.warning(
                f"DJEN: publicação {item.id_djen} sem caso nem unidade de origem; ignorada"
            )
            return

        novo_id = self.repo.criar(
            {
                "id_djen": item.id_djen,
                "hash": item.hash,
                "numero_processo": item.numero_processo,
                "numero_processo_mascara": item.numero_processo_mascara,
                "data_disponibilizacao": item.data_disponibilizacao,
                "sigla_tribunal": item.sigla_tribunal,
                "nome_orgao": item.nome_orgao,
                "tipo_comunicacao": item.tipo_comunicacao,
                "tipo_documento": item.tipo_documento,
                "nome_classe": item.nome_classe,
                "texto_html": item.texto,
                "texto_plano": djen_html.texto_plano(item.texto),
                "link": item.link,
                "destinatarios": item.destinatarios,
                "advogados": item.advogados,
                "ativo": item.ativo,
                "motivo_cancelamento": item.motivo_cancelamento,
                "situacao": "pendente",
                "oab_origem": oab_origem,
                "capturada_em": agora,
                "unidade_id": unidade_id,
            }
        )
        resultado.novas += 1
        if alvo is not None and caso is not None:
            self._vincular(novo_id, alvo, caso, executor_id, manual=False)
            resultado.vinculadas += 1

    def _vincular(
        self,
        comunicacao_id: int,
        processo: Processo,
        caso: Caso,
        executor_id: int | None,
        manual: bool,
    ) -> Evento:
        """Grava o vínculo e cria o evento no caso, na transação em curso.

        O vínculo manual notifica na hora; o da captura agrega os avisos por
        caso até o fim da fonte (`_depois_da_fonte`).
        """
        self.repo.atualizar(
            comunicacao_id,
            {
                "id_processo": processo.id,
                "id_caso": caso.id,
                "unidade_id": caso.unidade_id,
                "situacao": "vinculada",
                "data_situacao": datetime.now(),
                "id_vinculado_por": executor_id if manual else None,
            },
        )
        evento, novo = self._criar_evento(comunicacao_id, caso, executor_id)
        if novo:
            if manual:
                NotificacaoService().djen_publicacoes(caso, [evento], executor_id)
            else:
                _, lista, _ = self._avisos.setdefault(caso.id, (caso, [], executor_id))
                lista.append(evento)
        return evento

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
            p for p in (comunicacao.nome_orgao, comunicacao.nome_classe) if p
        )
        corpo = djen_html.resumo(comunicacao.texto_plano or "", 500)
        descricao = "\n\n".join(p for p in (cabecalho, corpo) if p) or None
        evento_id = self.eventos.create(
            {
                "id_caso": caso.id,
                "num_evento": self.eventos.count_by_caso_id(caso.id) + 1,
                "tipo": (comunicacao.tipo_comunicacao or "Publicação no DJEN")[:50],
                "descricao": descricao,
                "data_evento": comunicacao.data_disponibilizacao,
                "data_criacao": datetime.now(),
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

    def _ao_cancelar(self, comunicacao: ComunicacaoDJEN, executor_id: int | None) -> None:
        """Publicação cancelada depois do vínculo: o evento fica, com o selo de
        cancelada (lido de `djen_comunicacoes.ativo`), e o caso é avisado."""
        logger.info(f"DJEN: publicação {comunicacao.id} cancelada no DJEN")
        evento = self.eventos.find_by_djen_comunicacao(comunicacao.id)
        caso = self.casos.find_by_id(comunicacao.id_caso) if comunicacao.id_caso else None
        if evento is not None and caso is not None:
            NotificacaoService().djen_cancelada(caso, evento, executor_id)

    def vincular(
        self, id: int, processo_id: Any, user: UserInfo, unidade_id: int
    ) -> dict[str, Any]:
        """Vínculo manual: grava, cria o evento e notifica na mesma transação."""
        if user.urole not in PAPEIS_GESTAO:
            raise ForbiddenException()
        comunicacao = self._visivel(id, user, unidade_id)
        if comunicacao.situacao == "vinculada":
            raise ValidationException("A publicação já está vinculada a um caso")
        if isinstance(processo_id, bool) or not isinstance(processo_id, int):
            raise ValidationException("Informe o processo", field="processo_id")
        processo = self.processos.find_by_id(processo_id)
        caso = (
            self.casos.find_by_id(processo.id_caso, unidade_id=unidade_id)
            if processo
            else None
        )
        if processo is None or caso is None:
            # Mesma resposta para id inexistente, de outra unidade ou de outro NPJ.
            raise ValidationException("Processo não encontrado", field="processo_id")
        try:
            self._vincular(comunicacao.id, processo, caso, user.id, manual=True)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        logger.info(f"DJEN: publicação {id} vinculada ao processo {processo_id} por {user.id}")
        return self.detalhe(id, user, unidade_id)

    def descartar(self, id: int, user: UserInfo, unidade_id: int) -> dict[str, Any]:
        """Marca como não pertencente ao NPJ. A retenção apaga depois (plano, §8)."""
        if user.urole not in PAPEIS_GESTAO:
            raise ForbiddenException()
        comunicacao = self._visivel(id, user, unidade_id)
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
                    "data_situacao": datetime.now(),
                    "id_vinculado_por": user.id,
                },
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
            "criado_em": datetime.now(),
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
            mudancas["unidade_id"] = self._unidade_escolhida(dados, user, atual.unidade_id)
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
        fim = date.today()
        inicio = fim - timedelta(days=janela_dias)
        for item in self.client.buscar_por_oab(oab.numero_oab, oab.uf_oab, inicio, fim):
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
        for item in self.client.buscar_por_processo(processo.numero_cnj):
            if item.numero_processo != processo.numero_cnj:
                continue
            self.registrar(item, resultado, processo=processo, executor_id=executor_id)
        self.processos.update(
            processo.id, {"djen_pendente": False, "djen_consultado_em": datetime.now()}
        )

    def buscar_processo(
        self, processo_id: int, user: UserInfo, unidade_id: int
    ) -> dict[str, Any]:
        """Botão "Buscar publicações agora": uma consulta, sem esperar a rotina."""
        processo = self.processos.find_by_id(processo_id)
        caso = (
            self.casos.find_by_id(processo.id_caso, unidade_id=unidade_id)
            if processo
            else None
        )
        if processo is None or caso is None:
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
                "O DJEN não respondeu. Tente de novo em alguns minutos.",
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
        """Uma execução da rotina para o tenant ativo.

        Cada fonte (OAB, processo pendente) é gravada na sua própria transação:
        uma falha de rede no meio não perde o que já foi gravado e deixa a
        execução `parcial`. Toda execução grava uma linha em
        `djen_sincronizacoes`.
        """
        janela = janela_dias if janela_dias is not None else Config.DJEN_JANELA_DIAS
        limite = max_processos if max_processos is not None else Config.DJEN_MAX_PROCESSOS
        inicio = datetime.now()
        total = ResultadoCaptura()
        fontes = 0
        falhas = 0

        for fonte, executar in self._fontes(janela, limite):
            fontes += 1
            parcial = ResultadoCaptura()
            try:
                executar(parcial)
                self._depois_da_fonte()
                self.session.commit()
                total.somar(parcial)
            except Exception as erro:  # a falha de uma fonte não para as outras
                self.session.rollback()
                self._descartar_pendencias()
                falhas += 1
                total.erros.append(f"{fonte}: {erro}")
                logger.warning(f"DJEN: falha em {fonte}: {erro}")

        self._aplicar_retencao()

        if falhas == 0:
            status = "ok"
        elif falhas == fontes:
            status = "erro"
        else:
            status = "parcial"
        registro = {
            "inicio": inicio,
            "fim": datetime.now(),
            "status": status,
            "parametros": {"janela_dias": janela, "max_processos": limite},
            "novas": total.novas,
            "atualizadas": total.atualizadas,
            "vinculadas": total.vinculadas,
            "mensagem": "\n".join(total.erros)[:4000] or None,
        }
        self.sincronizacoes.registrar(registro)
        self.session.commit()
        logger.info(
            f"DJEN: tenant {self.repo.tenant_id()} {status}: {total.novas} nova(s), "
            f"{total.atualizadas} atualizada(s), {total.vinculadas} vinculada(s)"
        )
        return registro

    def _fontes(self, janela_dias: int, max_processos: int):
        """(rótulo, função) de cada fonte a consultar nesta execução.

        Primeiro as OABs ativas (de todas as unidades do NPJ), depois os
        processos pendentes (plano, §4).
        """
        for oab in self.oabs.listar(so_ativas=True):
            yield (
                f"OAB {oab.rotulo}",
                lambda resultado, o=oab: self._consultar_oab(o, janela_dias, resultado),
            )
        for processo in self.processos.pendentes_djen(max_processos):
            yield (
                f"processo {processo.id}",
                lambda resultado, p=processo: self._consultar_processo(p, resultado, None),
            )

    def _aplicar_retencao(self) -> int:
        """Apaga descartadas e pendentes sem caso com mais de N dias (plano, §8).

        Pendentes contam de `capturada_em`; descartadas, da data do descarte.
        Uma falha aqui não derruba a execução: fica para a próxima.
        """
        limite = datetime.now() - timedelta(days=Config.DJEN_RETENCAO_DIAS)
        try:
            apagadas = self.repo.apagar_vencidas(limite)
            self.session.commit()
        except Exception as erro:
            self.session.rollback()
            logger.warning(f"DJEN: retenção falhou: {erro}")
            return 0
        if apagadas:
            logger.info(f"DJEN: retenção apagou {apagadas} publicação(ões)")
        return apagadas
