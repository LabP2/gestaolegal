import logging
from typing import Any

from gestaolegal.common import PageParams, PaginatedResult
from gestaolegal.exceptions import NotFoundException, ValidationException
from gestaolegal.models.assistido import Assistido
from gestaolegal.models.assistido_input import (
    AssistidoCreateInput,
    AssistidoUpdateInput,
)
from gestaolegal.models.atendido import Atendido
from gestaolegal.integrations.djen_html import para_latin1
from gestaolegal.models.atendido_input import (
    AtendidoCreateInput,
    AtendidoSimplificadoInput,
    AtendidoUpdateInput,
    ListAtendido,
)
from gestaolegal.repositories.atendido_repository import AtendidoRepository
from gestaolegal.repositories.endereco_repository import EnderecoRepository
from gestaolegal.repositories.repository import (
    ComplexWhereClause,
    SearchParams,
    WhereClause,
)
from gestaolegal.utils.request_context import RequestContext
from gestaolegal.utils.cpf import cpf_valido

logger = logging.getLogger(__name__)


class AtendidoService:
    repository: AtendidoRepository
    endereco_repository: EnderecoRepository

    def __init__(self):
        self.repository = AtendidoRepository()
        self.endereco_repository = EnderecoRepository()

    def find_by_id(self, atendido_id: int) -> Atendido | None:
        logger.info(f"Finding atendido by id: {atendido_id}")
        atendido = self.repository.find_by_id(
            atendido_id, unidade_id=RequestContext.get_unidade_ativa()
        )
        if atendido:
            if atendido.endereco_id:
                atendido.endereco = self.endereco_repository.find_by_id(
                    atendido.endereco_id
                )
            atendido.assistido = self.repository.find_assistido_by_atendido_id(
                atendido_id
            )
            logger.info(
                f"Atendido found with id: {atendido_id}, has assistido: {atendido.assistido is not None}"
            )
        else:
            logger.warning(f"Atendido not found with id: {atendido_id}")
        return atendido

    def search(
        self,
        search: str,
        page_params: PageParams,
        tipo_busca: str = "todos",
        show_inactive: bool = False,
    ) -> PaginatedResult[ListAtendido]:
        logger.info(
            f"AtendidoService.search called with search_term: '{search}', tipo_busca: {tipo_busca}, "
            + f"page_params: {page_params}, show_inactive: {show_inactive}"
        )

        clauses: list[WhereClause] = [
            WhereClause(
                column="unidade_id",
                operator="==",
                value=RequestContext.get_unidade_ativa(),
            )
        ]

        if not show_inactive:
            clauses.append(WhereClause(column="status", operator="==", value=1))

        where = None
        if len(clauses) > 1:
            where = ComplexWhereClause(clauses=clauses, operator="and")
        elif len(clauses) == 1:
            where = clauses[0]

        params = SearchParams(
            page_params=page_params,
            where=where,
        )

        result = self.repository.search(params=params, tipo_busca=tipo_busca, search=search)

        endereco_ids = [a["endereco_id"] for a in result.items if a["endereco_id"]]
        endereco_map = {}
        if endereco_ids:
            enderecos = self.endereco_repository.get_by_ids(endereco_ids)
            endereco_map = {e.id: e for e in enderecos}

        for atendido in result.items:
            atendido["endereco"] = (
                endereco_map.get(atendido["endereco_id"])
                if atendido["endereco_id"]
                else None
            )
            del atendido["endereco_id"]
            if "total_count" in atendido:
                del atendido["total_count"]

        converted_result = PaginatedResult(
            items=[
                ListAtendido(**a) if isinstance(a, dict) else a for a in result.items
            ],
            total=result.total,
            page=result.page,
            per_page=result.per_page,
        )

        logger.info(
            f"AtendidoService.search returning {result.total} total results, {len(result.items)} items on this page"
        )

        return converted_result

    def create(self, atendido_input: AtendidoCreateInput) -> Atendido:
        logger.info(
            f"Creating atendido with nome: {atendido_input.nome}, cpf: {atendido_input.cpf}"
        )
        atendido_data = atendido_input.model_dump()
        atendido_data["status"] = 1
        atendido_data["unidade_id"] = RequestContext.get_unidade_ativa()

        endereco_data = self.__extract_endereco_data(atendido_data)
        atendido_data["endereco_id"] = self.endereco_repository.create(endereco_data)

        atendido_id = self.repository.create(atendido_data)
        logger.info(f"Atendido created successfully with id: {atendido_id}")
        return self.find_by_id(atendido_id)

    def update(
        self,
        atendido_id: int,
        atendido_input: AtendidoUpdateInput,
    ) -> Atendido | None:
        logger.info(f"Updating atendido with id: {atendido_id}")
        existing = self.repository.find_by_id(
            atendido_id, unidade_id=RequestContext.get_unidade_ativa()
        )
        if not existing:
            logger.error(f"Update failed: atendido not found with id: {atendido_id}")
            raise NotFoundException(resource="Atendido", resource_id=atendido_id)

        self._validar_edicao_legado(existing, atendido_input)
        update_data = atendido_input.model_dump(exclude_none=True)

        endereco_data = self.__extract_endereco_data_for_update(update_data)
        if endereco_data and existing.endereco_id:
            self.endereco_repository.update(existing.endereco_id, endereco_data)
            logger.info(f"Updated address for atendido id: {atendido_id}")

        if update_data:
            self.repository.update(atendido_id, update_data)
        logger.info(f"Atendido updated successfully with id: {atendido_id}")
        return self.find_by_id(atendido_id)

    @staticmethod
    def _validar_edicao_legado(existing: Atendido, atendido_input: AtendidoUpdateInput) -> None:
        # Conferir o estado persistido, nunca uma alegação de legado do cliente.
        supplied = atendido_input.model_dump(exclude_unset=True)
        for field in ("cpf", "procurou_outro_local", "pj_constituida"):
            if field not in supplied or supplied[field] == getattr(existing, field):
                continue
            value = supplied[field]
            if field == "cpf":
                valid = isinstance(value, str) and cpf_valido(value)
            else:
                valid = value in ("sim", "nao")
            if not valid:
                raise ValidationException("Informe um valor válido para o campo alterado", field=field)

    def create_assistido(
        self, id_atendido: int, assistido_input: AssistidoCreateInput
    ) -> Assistido:
        logger.info(f"Creating assistido for atendido id: {id_atendido}")
        atendido = self.repository.find_by_id(
            id_atendido, unidade_id=RequestContext.get_unidade_ativa()
        )
        if not atendido:
            logger.error(
                f"Create assistido failed: atendido not found with id: {id_atendido}"
            )
            raise NotFoundException(resource="Atendido", resource_id=id_atendido)

        pj = assistido_input.assistido_pessoa_juridica
        if pj is not None and atendido.pj_constituida != "sim":
            raise ValidationException(
                "Dados jurídicos exigem pessoa jurídica constituída",
                field="assistido_pessoa_juridica",
            )
        assistido_data = assistido_input.model_dump(
            exclude={"assistido_pessoa_juridica"}
        )
        assistido_data["id_atendido"] = id_atendido

        try:
            assistido_id = self.repository.create_assistido(assistido_data)
            if atendido.sem_triagem:
                # A triagem feita depois mantém o atendido e encerra o "sem triagem".
                self.repository.update(id_atendido, {"sem_triagem": False})
            if pj is not None:
                self.repository.salvar_pessoa_juridica(assistido_id, pj.model_dump())
            logger.info(
                f"Assistido created successfully with id: {assistido_id} for atendido: {id_atendido}"
            )
            return self.repository.find_assistido_by_atendido_id(id_atendido)
        except Exception:
            self.repository.session.rollback()
            raise

    def update_assistido(
        self,
        id_atendido: int,
        atendido_input: AtendidoUpdateInput | None,
        assistido_input: AssistidoUpdateInput,
    ) -> Assistido:
        logger.info(f"Updating assistido for atendido id: {id_atendido}")
        atendido = self.repository.find_by_id(
            id_atendido, unidade_id=RequestContext.get_unidade_ativa()
        )
        if not atendido:
            logger.error(
                f"Update assistido failed: atendido not found with id: {id_atendido}"
            )
            raise NotFoundException(resource="Atendido", resource_id=id_atendido)

        pj = assistido_input.assistido_pessoa_juridica
        pj_constituida = (
            atendido_input.pj_constituida
            if atendido_input and atendido_input.pj_constituida is not None
            else atendido.pj_constituida
        )
        if pj is not None and pj_constituida != "sim":
            raise ValidationException(
                "Dados jurídicos exigem pessoa jurídica constituída",
                field="assistido_pessoa_juridica",
            )

        assistido = self.repository.find_assistido_by_atendido_id(id_atendido)
        if not assistido:
            logger.error(
                f"Update assistido failed: atendido {id_atendido} does not have an assistido record"
            )
            raise ValidationException(
                "Atendido não possui registro de assistido", field="assistido"
            )

        try:
            if atendido_input:
                self._validar_edicao_legado(atendido, atendido_input)
                update_data = atendido_input.model_dump(exclude_none=True)

                endereco_data = self.__extract_endereco_data_for_update(update_data)
                if endereco_data and atendido.endereco_id:
                    self.endereco_repository.update(atendido.endereco_id, endereco_data)
                    logger.info(f"Updated address for atendido id: {id_atendido}")

                if update_data:
                    self.repository.update(id_atendido, update_data)
                logger.info(f"Updated atendido data for id: {id_atendido}")

            assistido_update_data = assistido_input.model_dump(
                exclude_none=True, exclude={"assistido_pessoa_juridica"}
            )
            if assistido_update_data:
                self.repository.update_assistido(id_atendido, assistido_update_data)
            if pj is not None:
                self.repository.salvar_pessoa_juridica(assistido.id, pj.model_dump())
            logger.info(
                f"Assistido updated successfully for atendido id: {id_atendido}"
            )
            return self.repository.find_assistido_by_atendido_id(id_atendido)
        except Exception:
            self.repository.session.rollback()
            raise

    # --- cadastro simplificado e variações do nome ------------------------------
    # docs/plano-processos-avulsos.md, §2: parte de processo sem caso.

    @staticmethod
    def _documento(valor: str | None, digitos: int, campo: str, rotulo: str) -> str | None:
        if valor is None:
            return None
        so_digitos = "".join(c for c in valor if c.isdigit())
        if len(so_digitos) != digitos or not so_digitos.isascii():
            raise ValidationException(f"{rotulo} inválido", field=campo)
        if digitos == 11:
            d = so_digitos
            return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
        d = so_digitos
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"

    def criar_simplificado(self, dados: AtendidoSimplificadoInput) -> Atendido:
        """Só nome, documento e observação; o resto fica nulo até a triagem."""
        registro = {
            # `atendidos` tem colunas legadas em latin1 no MySQL.
            "nome": para_latin1(dados.nome),
            "cpf": self._documento(dados.cpf, 11, "cpf", "CPF"),
            "cnpj": self._documento(dados.cnpj, 14, "cnpj", "CNPJ"),
            "obs": para_latin1(dados.obs),
            "status": 1,
            "sem_triagem": True,
            "unidade_id": RequestContext.get_unidade_ativa(),
        }
        atendido_id = self.repository.create(registro)
        logger.info(f"Atendido {atendido_id} cadastrado sem triagem")
        atendido = self.find_by_id(atendido_id)
        assert atendido is not None
        return atendido

    def _da_unidade(self, atendido_id: int) -> Atendido:
        atendido = self.repository.find_by_id(
            atendido_id, unidade_id=RequestContext.get_unidade_ativa()
        )
        if not atendido:
            raise NotFoundException(resource="Atendido", resource_id=atendido_id)
        return atendido

    def nomes(self, atendido_id: int) -> list[dict[str, Any]]:
        self._da_unidade(atendido_id)
        return self.repository.nomes(atendido_id)

    def adicionar_nome(self, atendido_id: int, nome: Any) -> list[dict[str, Any]]:
        atendido = self._da_unidade(atendido_id)
        if not isinstance(nome, str) or not " ".join(nome.split()):
            raise ValidationException("Informe o nome", field="nome")
        nome = " ".join(nome.split())
        if len(nome) > 150:
            raise ValidationException("Nome com mais de 150 caracteres", field="nome")
        if nome.lower() == (atendido.nome or "").lower() or self.repository.nome_existe(
            atendido_id, nome
        ):
            raise ValidationException("Este nome já está cadastrado", field="nome")
        self.repository.adicionar_nome(atendido_id, nome)
        return self.repository.nomes(atendido_id)

    def remover_nome(self, atendido_id: int, nome_id: int) -> None:
        self._da_unidade(atendido_id)
        if not self.repository.remover_nome(atendido_id, nome_id):
            raise NotFoundException(resource="Nome", resource_id=nome_id)

    def soft_delete(self, atendido_id: int):
        logger.info(f"Soft deleting atendido with id: {atendido_id}")
        existing = self.repository.find_by_id(
            atendido_id, unidade_id=RequestContext.get_unidade_ativa()
        )
        if not existing:
            logger.error(
                f"Soft delete failed: atendido not found with id: {atendido_id}"
            )
            raise NotFoundException(resource="Atendido", resource_id=atendido_id)
        self.repository.delete(atendido_id)
        logger.info(f"Atendido soft deleted successfully with id: {atendido_id}")

    def reactivate(self, atendido_id: int):
        existing = self.repository.find_by_id(
            atendido_id, unidade_id=RequestContext.get_unidade_ativa()
        )
        if not existing:
            raise NotFoundException(resource="Atendido", resource_id=atendido_id)
        self.repository.update(atendido_id, {"status": 1})

    def __extract_endereco_data(self, atendido_data: dict[str, Any]):
        return {
            "logradouro": atendido_data.pop("logradouro"),
            "numero": atendido_data.pop("numero"),
            "cidade": atendido_data.pop("cidade"),
            "estado": atendido_data.pop("estado"),
            "complemento": atendido_data.pop("complemento"),
            "bairro": atendido_data.pop("bairro"),
            "cep": atendido_data.pop("cep"),
        }

    def __extract_endereco_data_for_update(self, atendido_data: dict[str, Any]):
        endereco_fields = [
            "logradouro",
            "numero",
            "cidade",
            "estado",
            "complemento",
            "bairro",
            "cep",
        ]
        endereco_data = {}

        for field in endereco_fields:
            if field in atendido_data:
                endereco_data[field] = atendido_data.pop(field)

        return endereco_data if endereco_data else None
