"""Conferência dos ids que chegam no corpo de uma criação ou edição.

Um id de outro NPJ, ou que não existe, é recusado com a mesma resposta: a
mensagem não pode revelar que o registro existe em outro tenant. Sem esta
conferência, o service gravaria a referência cruzada (a leitura não mostra
nada, mas o vínculo fica no banco).
"""

from collections.abc import Iterable

from gestaolegal.database.tables import metadata
from gestaolegal.exceptions import ValidationException
from gestaolegal.repositories.repository import BaseRepository

ROTULOS = {
    "usuarios": "Usuário",
    "atendidos": "Atendido",
    "casos": "Caso",
}


def exigir_existentes(tabela: str, ids: Iterable[int | None], campo: str) -> None:
    """Levanta ValidationException se algum id não existe no tenant ativo.

    None é ignorado: campos opcionais não informados não são conferidos.
    """
    procurados = {i for i in ids if i is not None}
    if not procurados:
        return
    existentes = BaseRepository().ids_do_tenant(metadata.tables[tabela], procurados)
    if procurados - existentes:
        raise ValidationException(f"{ROTULOS[tabela]} não encontrado", field=campo)


def exigir_existente(tabela: str, id: int | None, campo: str) -> None:
    exigir_existentes(tabela, [id], campo)
