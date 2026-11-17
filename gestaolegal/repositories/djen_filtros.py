"""Filtros sobre os destinatários estruturados do DJEN, sem buscar no texto."""

import json
import re
from sqlalchemy import String, cast, exists, func, or_, select
from gestaolegal.exceptions import ValidationException


def filtrar_identificacao(
    stmt, tabela, dialect, nome_parte=None, numero_processo=None, oab=None
):
    if numero_processo:
        numero = re.sub(r"[.\s/-]", "", numero_processo)
        if not numero.isascii() or not numero.isdigit() or len(numero) > 20:
            raise ValidationException(
                "Informe o número do processo, com ou sem máscara",
                field="numero_processo",
            )
        stmt = stmt.where(
            tabela.c.numero_processo == numero
            if len(numero) == 20
            else tabela.c.numero_processo.contains(numero, autoescape=True)
        )
    if nome_parte:
        nome = nome_parte.strip().lower()
        if dialect == "mysql":
            # Escape LIKE metacharacters: the typed name is literal.
            termo = (
                "%"
                + nome.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                + "%"
            )
            predicado = func.json_search(
                func.lower(cast(tabela.c.destinatarios, String)),
                "one",
                termo,
                "\\",
                "$[*].nome",
            ).is_not(None)
        else:
            partes = (
                func.json_each(tabela.c.destinatarios)
                .table_valued("value")
                .alias("partes_djen")
            )
            predicado = exists(
                select(1)
                .select_from(partes)
                .where(
                    func.lower(func.json_extract(partes.c.value, "$.nome")).contains(
                        nome, autoescape=True
                    )
                )
            )
        stmt = stmt.where(predicado)
    if oab:
        limpo = re.sub(r"[.\s/-]", "", oab).upper()
        match = re.fullmatch(r"([0-9]{1,20})([A-Z]{2})?|([A-Z]{2})([0-9]{1,20})", limpo)
        if not match:
            raise ValidationException(
                "Informe a OAB como número ou número/UF", field="oab"
            )
        numero, uf = (match[1], match[2]) if match[1] else (match[4], match[3])
        if (
            uf
            and uf
            not in "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split()
        ):
            raise ValidationException("UF da OAB inválida", field="oab")
        candidato = {"numero_oab": numero}
        if uf:
            candidato["uf_oab"] = uf
        if dialect == "mysql":
            predicado = (
                func.json_contains(tabela.c.advogados, json.dumps(candidato)) == 1
            )
        else:
            advogados = (
                func.json_each(tabela.c.advogados)
                .table_valued("value")
                .alias("advogados_djen")
            )
            busca = (
                select(1)
                .select_from(advogados)
                .where(func.json_extract(advogados.c.value, "$.numero_oab") == numero)
            )
            if uf:
                busca = busca.where(
                    func.json_extract(advogados.c.value, "$.uf_oab") == uf
                )
            predicado = exists(busca)
        if "oab_origem" in tabela.c:
            origem = (
                tabela.c.oab_origem == f"{numero}/{uf}"
                if uf
                else tabela.c.oab_origem.startswith(numero + "/", autoescape=True)
            )
            predicado = or_(predicado, origem)
        stmt = stmt.where(predicado)
    return stmt
