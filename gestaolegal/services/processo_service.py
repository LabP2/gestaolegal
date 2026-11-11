import logging
from dataclasses import asdict
from datetime import date
from typing import Any

from gestaolegal.common import PageParams, PaginatedResult
from gestaolegal.exceptions import (
    DatabaseException,
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from gestaolegal.models.processo import Processo, ProcessoListItem
from gestaolegal.models.processo_input import (
    ParteInput,
    ProcessoCreateInput,
    ProcessoSemCasoInput,
    ProcessoUpdateInput,
)
from gestaolegal.models.user import User, UserInfo
from gestaolegal.repositories.atendido_repository import AtendidoRepository
from gestaolegal.repositories.caso_repository import CasoRepository
from gestaolegal.repositories.processo_repository import ProcessoRepository
from gestaolegal.repositories.repository import (
    ComplexWhereClause,
    SearchParams,
    WhereClause,
)
from gestaolegal.repositories.user_repository import UserRepository
from gestaolegal.utils.cnj import normalizar_cnj
from gestaolegal.utils.request_context import RequestContext
from gestaolegal.services.referencias import exigir_existente

logger = logging.getLogger(__name__)

# Processos sem caso (docs/plano-processos-avulsos.md, §2). Mesma régua da
# lista do DJEN (`PAPEIS_UNIDADE` em djen_service.py; o teste confere que as
# duas não divergem): veem toda a unidade e cadastram processo sem caso.
PAPEIS_SEM_CASO = ("admin", "prof", "orient", "colab_proj")
# Só os processos dos casos de que participam; nunca os sem caso.
PAPEIS_PARTICIPANTE = ("estag_direito", "colab_ext")
# Exclusão lógica de processo de caso: só admin, como na rota do caso.
PAPEIS_EXCLUIR_DE_CASO = ("admin",)
STATUS_LISTA = {"ativo": True, "inativo": False, "todos": None}
COM_CASO_LISTA = {"sim": True, "nao": False, "todos": None}


class ProcessoService:
    repository: ProcessoRepository
    user_repository: UserRepository
    caso_repository: CasoRepository

    def __init__(self):
        self.repository = ProcessoRepository()
        self.user_repository = UserRepository()
        self.caso_repository = CasoRepository()

    def _caso_da_unidade_ativa(self, caso_id: int) -> bool:
        """O processo segue a unidade do caso, não a do header.

        Caso de outra unidade se comporta como caso inexistente: dizer que ele
        existe mas não é seu já vazaria a existência do caso.
        """
        return (
            self.caso_repository.find_by_id(
                caso_id, unidade_id=RequestContext.get_unidade_ativa()
            )
            is not None
        )

    def find_by_id(self, processo_id: int) -> Processo | None:
        logger.info(f"Finding processo by id: {processo_id}")
        processo = self.repository.find_by_id(processo_id)
        if not processo:
            logger.warning(f"Processo not found with id: {processo_id}")
            return None

        if processo.id_criado_por:
            processo.criado_por = User.to_info_optional(
                self.user_repository.find_by_id(processo.id_criado_por)
            )

        logger.info(f"Processo found with id: {processo_id}")
        return processo

    def search_by_caso(
        self,
        page_params: PageParams,
        caso_id: int,
        search: str = "",
        show_inactive: bool = False,
    ) -> PaginatedResult[Processo]:
        logger.info(
            f"Searching processos for caso {caso_id} with search: '{search}', show_inactive: {show_inactive}"
        )
        if not self._caso_da_unidade_ativa(caso_id):
            logger.warning(f"Caso {caso_id} is not in the active unidade")
            raise NotFoundException(resource="Caso", resource_id=caso_id)

        clauses: list[WhereClause] = [
            WhereClause(column="id_caso", operator="==", value=caso_id)
        ]

        if not show_inactive:
            clauses.append(WhereClause(column="status", operator="==", value=True))

        if search:
            clauses.append(
                WhereClause(
                    column="identificacao", operator="ilike", value=f"%{search}%"
                )
            )

        where = (
            ComplexWhereClause(clauses=clauses, operator="and")
            if len(clauses) > 1
            else clauses[0]
        )

        params = SearchParams(page_params=page_params, where=where)
        result = self.repository.search(params=params)

        for processo in result.items:
            if processo.id_criado_por:
                processo.criado_por = User.to_info_optional(
                    self.user_repository.find_by_id(processo.id_criado_por)
                )

        logger.info(
            f"Returning {len(result.items)} processos of total {result.total} found for caso {caso_id}"
        )
        return result

    def validate_processo_for_caso(
        self, processo_id: int, caso_id: int
    ) -> Processo | None:
        logger.info(f"Validating processo {processo_id} for caso {caso_id}")
        if not self._caso_da_unidade_ativa(caso_id):
            logger.warning(f"Caso {caso_id} is not in the active unidade")
            return None

        processo = self.repository.find_by_id(processo_id)

        if not processo:
            logger.warning(f"Processo not found with id: {processo_id}")
            return None

        if processo.id_caso != caso_id:
            logger.warning(f"Processo {processo_id} does not belong to caso {caso_id}")
            return None

        if processo.id_criado_por:
            processo.criado_por = User.to_info_optional(
                self.user_repository.find_by_id(processo.id_criado_por)
            )

        return processo

    def create(
        self, caso_id: int, processo_input: ProcessoCreateInput, criado_por_id: int
    ) -> Processo:
        logger.info(
            f"Creating processo for caso {caso_id} with especie: {processo_input.especie}, created by: {criado_por_id}"
        )
        if not self._caso_da_unidade_ativa(caso_id):
            logger.warning(f"Caso {caso_id} is not in the active unidade")
            raise NotFoundException(resource="Caso", resource_id=caso_id)

        caso = self.caso_repository.find_by_id(caso_id)
        assert caso is not None
        processo_data = processo_input.model_dump()
        processo_data["id_caso"] = caso_id
        processo_data["unidade_id"] = caso.unidade_id
        processo_data["id_criado_por"] = criado_por_id
        # DJEN: o cadastro não chama a API; só marca o processo para a rotina
        # buscar o histórico (docs/plano-djen.md, §2).
        processo_data["numero_cnj"] = normalizar_cnj(processo_input.numero)
        processo_data["djen_pendente"] = processo_data["numero_cnj"] is not None

        processo_id = self.repository.create(processo_data)

        created_processo = self.find_by_id(processo_id)
        if not created_processo:
            logger.error("Failed to create processo")
            raise DatabaseException("Falha ao criar processo")

        logger.info(f"Processo created successfully with id: {processo_id}")
        return created_processo

    def update(
        self, processo_id: int, processo_input: ProcessoUpdateInput
    ) -> Processo | None:
        logger.info(f"Updating processo with id: {processo_id}")
        existing = self.repository.find_by_id(processo_id)
        if not existing:
            logger.error(f"Update failed: processo not found with id: {processo_id}")
            raise NotFoundException(resource="Processo", resource_id=processo_id)
        exigir_existente("casos", processo_input.id_caso, "id_caso")

        processo_data = processo_input.model_dump(exclude_none=True)
        if processo_input.id_caso is not None and processo_input.id_caso != existing.id_caso:
            # O processo segue a unidade do caso.
            novo_caso = self.caso_repository.find_by_id(processo_input.id_caso)
            assert novo_caso is not None
            processo_data["unidade_id"] = novo_caso.unidade_id
        for field in ("numero", "valor_causa_inicial", "valor_causa_atual"):
            if field in processo_input.model_fields_set:
                processo_data[field] = getattr(processo_input, field)
        if "numero" in processo_input.model_fields_set:
            numero_cnj = normalizar_cnj(processo_input.numero)
            if numero_cnj != existing.numero_cnj:
                processo_data["numero_cnj"] = numero_cnj
                processo_data["djen_pendente"] = numero_cnj is not None
        self.repository.update(processo_id, processo_data)

        logger.info(f"Processo updated successfully with id: {processo_id}")
        return self.find_by_id(processo_id)

    def soft_delete(self, processo_id: int) -> bool:
        logger.info(f"Soft deleting processo with id: {processo_id}")
        result = self.repository.delete(processo_id)
        if result:
            logger.info(f"Processo soft deleted successfully with id: {processo_id}")
        else:
            logger.warning(f"Soft delete failed for processo with id: {processo_id}")
        return result

    # --- lista geral e processo sem caso ------------------------------------
    # docs/plano-processos-avulsos.md, §2 e §3.

    @staticmethod
    def _participante(user: UserInfo) -> int | None:
        """None para quem vê a unidade toda; o id de quem só vê os seus casos."""
        if user.urole in PAPEIS_SEM_CASO:
            return None
        if user.urole in PAPEIS_PARTICIPANTE:
            return user.id
        raise ForbiddenException()

    def listar(
        self,
        user: UserInfo,
        unidade_id: int,
        page_params: PageParams,
        parte: str | None = None,
        numero: str | None = None,
        distribuicao_de: date | None = None,
        distribuicao_ate: date | None = None,
        status: str | None = None,
        com_caso: str | None = None,
    ) -> PaginatedResult[ProcessoListItem]:
        if (status or "ativo") not in STATUS_LISTA:
            raise ValidationException("Status inválido", field="status")
        if (com_caso or "todos") not in COM_CASO_LISTA:
            raise ValidationException("Valor inválido", field="com_caso")
        resultado = self.repository.listar(
            page_params,
            unidade_id=unidade_id,
            participante_id=self._participante(user),
            parte=parte,
            numero=numero,
            distribuicao_de=distribuicao_de,
            distribuicao_ate=distribuicao_ate,
            status=STATUS_LISTA[status or "ativo"],
            com_caso=COM_CASO_LISTA[com_caso or "todos"],
        )
        nomes = self.repository.nomes_das_partes([(p.id, p.id_caso) for p in resultado.items])
        publicacoes = self.repository.total_publicacoes([p.id for p in resultado.items])
        for item in resultado.items:
            item.partes = nomes.get(item.id, [])
            item.total_publicacoes = publicacoes.get(item.id, 0)
        return resultado

    def _visivel(self, processo_id: int, user: UserInfo, unidade_id: int) -> Processo:
        """O processo, se a unidade e o papel permitem vê-lo; senão 404.

        Mesma resposta para id inexistente, de outra unidade ou de outro NPJ.
        """
        participante = self._participante(user)
        processo = self.repository.find_by_id(processo_id)
        if processo is None or processo.unidade_id != unidade_id:
            raise NotFoundException(resource="Processo", resource_id=processo_id)
        if participante is not None and (
            processo.id_caso is None
            or not self.repository.participa_do_caso(processo.id_caso, participante)
        ):
            raise NotFoundException(resource="Processo", resource_id=processo_id)
        return processo

    def detalhe(self, processo_id: int, user: UserInfo, unidade_id: int) -> dict[str, Any]:
        processo = self._visivel(processo_id, user, unidade_id)
        if processo.id_criado_por:
            processo.criado_por = User.to_info_optional(
                self.user_repository.find_by_id(processo.id_criado_por)
            )
        dados = asdict(processo)
        dados["partes"] = [asdict(p) for p in self.repository.partes(processo)]
        dados["total_publicacoes"] = self.repository.total_publicacoes([processo.id]).get(
            processo.id, 0
        )
        return dados

    def _conferir_partes(
        self, partes: list[ParteInput], unidade_id: int
    ) -> list[dict[str, Any]]:
        """Atendidos do NPJ e da unidade ativa; senão 400 genérico, como em
        `services/referencias.py` (não revela se o id existe em outro lugar)."""
        atendidos = AtendidoRepository()
        vistos: set[int] = set()
        resultado = []
        for parte in partes:
            if parte.id_atendido in vistos:
                continue
            vistos.add(parte.id_atendido)
            if atendidos.find_by_id(parte.id_atendido, unidade_id=unidade_id) is None:
                raise ValidationException("Parte não encontrada", field="partes")
            resultado.append({"id_atendido": parte.id_atendido, "polo": parte.polo})
        return resultado

    def criar_sem_caso(
        self, dados: ProcessoSemCasoInput, user: UserInfo, unidade_id: int
    ) -> dict[str, Any]:
        """Processo sem caso, com ao menos uma parte. Não faz commit."""
        if user.urole not in PAPEIS_SEM_CASO:
            raise ForbiddenException()
        partes = self._conferir_partes(dados.partes, unidade_id)
        registro = dados.model_dump(exclude={"partes", "id_caso"})
        registro["id_caso"] = None
        registro["unidade_id"] = unidade_id
        registro["id_criado_por"] = user.id
        # DJEN: mesmas regras do processo de caso (docs/plano-djen.md, §2).
        registro["numero_cnj"] = normalizar_cnj(dados.numero)
        registro["djen_pendente"] = registro["numero_cnj"] is not None
        processo_id = self.repository.create(registro)
        self.repository.definir_partes(processo_id, partes)
        logger.info(f"Processo sem caso {processo_id} criado por {user.id}")
        return self.detalhe(processo_id, user, unidade_id)

    def _pode_editar(self, processo: Processo, user: UserInfo) -> None:
        # O processo de caso segue a régua do caso: quem o vê, edita (como
        # PUT /caso/<id>/processos/<id>). O sem caso, só os papéis da unidade.
        if processo.id_caso is None and user.urole not in PAPEIS_SEM_CASO:
            raise ForbiddenException()

    def atualizar(
        self,
        processo_id: int,
        dados: ProcessoUpdateInput,
        partes: list[ParteInput] | None,
        user: UserInfo,
        unidade_id: int,
    ) -> dict[str, Any]:
        processo = self._visivel(processo_id, user, unidade_id)
        self._pode_editar(processo, user)
        if "id_caso" in dados.model_fields_set:
            raise ValidationException(
                "O caso do processo não muda por esta rota", field="id_caso"
            )
        if partes is not None:
            if processo.id_caso is not None:
                raise ValidationException(
                    "As partes do processo de caso vêm do caso", field="partes"
                )
            if not partes:
                raise ValidationException("Informe ao menos uma parte", field="partes")
            self.repository.definir_partes(
                processo_id, self._conferir_partes(partes, unidade_id)
            )
        self.update(processo_id, dados)
        return self.detalhe(processo_id, user, unidade_id)

    def excluir(self, processo_id: int, user: UserInfo, unidade_id: int) -> None:
        processo = self._visivel(processo_id, user, unidade_id)
        permitidos = PAPEIS_EXCLUIR_DE_CASO if processo.id_caso else PAPEIS_SEM_CASO
        if user.urole not in permitidos:
            raise ForbiddenException()
        self.repository.delete(processo_id)
