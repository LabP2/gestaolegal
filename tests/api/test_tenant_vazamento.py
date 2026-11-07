"""Varredura de vazamento entre tenants sobre todo o `app.url_map`.

A DAJ (tenant 1) ganha um conjunto completo de dados, todos marcados com
`VAZOU-DAJ`. O admin do outro NPJ (tenant 2) então chama cada rota da API:

- rota com id: recebe os ids da DAJ e precisa responder 403 ou 404;
- coleção (lista, busca, contagem, relatório): a resposta precisa ser igual à
  que ele recebia antes de a DAJ ter dados;
- escrita no próprio tenant (criar, configurar, marcar como lida): roda com
  referências a ids da DAJ no corpo, quando a rota aceita.

Nenhuma resposta pode conter a marca nem o e-mail da DAJ, e os dados do tenant
1 precisam estar iguais no fim de cada chamada. Também se confere que a
requisição só roda sem tenant nos trechos permitidos (docs/plano-multitenant.md,
§10).

Toda rota do `url_map` precisa estar classificada em `ROTAS`. Uma rota nova
sem classificação faz `test_toda_rota_esta_classificada` falhar.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Any, Callable

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import select

from gestaolegal.database import session as db_session_module
from gestaolegal.database.tables import TABELAS_GLOBAIS, metadata
from gestaolegal.utils.request_context import sem_tenant

from .conftest import (
    TENANT_DAJ,
    TENANT_OUTRO,
    TEST_ADMIN_EMAIL,
    TEST_ADMIN_PASSWORD,
    UNIDADE_BH,
    UNIDADE_OUTRO,
    criar_usuario,
    get_success_data,
    headers_para,
)
from .test_tenant_isolamento import OUTRO_EMAIL, OUTRO_SENHA

MARCA = "VAZOU-DAJ"
# Termo de busca que acha os registros da DAJ sem que o eco da consulta na
# resposta contenha a marca inteira.
BUSCA = "VAZOU"
PREFIXO_PLATAFORMA = "/api/plataforma/"
ID_INEXISTENTE = 987654
# Rotas da plataforma abertas sem token.
PUBLICAS_PLATAFORMA = {("POST", "/api/plataforma/auth/login")}
LOGGER_CONTEXTO = "gestaolegal.utils.request_context"

# Trechos sem tenant aceitos durante uma requisição. Fora destes, a requisição
# inteira roda dentro do tenant do token.
MOTIVO_LOGIN = "login: localizar o NPJ pelo e-mail"
MOTIVO_TOKEN_SENHA = "recuperação de senha: localizar o token"
MOTIVO_AUTENTICACAO = "autenticação: conferir se o NPJ do token está ativo"
MOTIVO_EMAIL_UNICO = "cadastro: e-mail é único na plataforma"

Ids = dict[str, int]
Corpo = Callable[[Ids], dict[str, Any]]


@dataclass(frozen=True)
class Rota:
    """Como uma rota é exercitada pelo outro NPJ.

    categoria:
      - "publica": sem token (login, recuperação de senha, estáticos), coberta
        por tests/api/test_auth_api.py, test_password_reset_api.py e
        test_tenant_isolamento.py;
      - "id": recebe ids da DAJ em `params` e deve responder 403/404;
      - "colecao": GET sem id; a resposta não muda com os dados da DAJ;
      - "escrita": cria ou altera no próprio tenant; não pode tocar na DAJ.
    """

    categoria: str
    # Parâmetro da URL -> chave em `Ids`.
    params: dict[str, str] = field(default_factory=dict)
    json: Corpo | None = None
    form: Corpo | None = None
    query: str = ""
    # Motivos de sem_tenant aceitos além da autenticação.
    motivos: frozenset[str] = frozenset()
    # Status esperados de uma escrita no próprio NPJ.
    status: tuple[int, ...] = (200, 201)


def _sem_corpo(_: Ids) -> dict[str, Any]:
    return {}


def _pdf(_: Ids) -> dict[str, Any]:
    return {"arquivo": (BytesIO(b"%PDF-1.4 outro npj"), "outro.pdf")}


def _evento(_: Ids) -> dict[str, Any]:
    return {"tipo": "Audiência", "data_evento": "2026-06-20", "descricao": "Outro", "status": "true"}


def _processo(_: Ids) -> dict[str, Any]:
    return {"especie": "Ação", "numero": "5550001", "status": True}


# As escritas do outro NPJ referenciam os próprios registros ("meu_*"). O
# teste de referência cruzada troca esses ids pelos da DAJ.
def _lembrete(ids: Ids) -> dict[str, Any]:
    return {"id_usuario": ids["meu_usuario"], "data_lembrete": "2026-09-15T00:00:00", "descricao": "Outro"}


def _caso(ids: Ids) -> dict[str, Any]:
    return {
        "id_usuario_responsavel": ids["meu_usuario"],
        "id_orientador": ids["meu_usuario"],
        "area_direito": "civel",
        "situacao_deferimento": "deferido",
        "ids_clientes": [ids["meu_atendido"]],
    }


def _orientacao(ids: Ids) -> dict[str, Any]:
    return {"area_direito": "civel", "descricao": "Orientação do outro NPJ", "atendidos_ids": [ids["meu_atendido"]]}


def _assistencia(_: Ids) -> dict[str, Any]:
    return {
        "nome": "Assistência do outro NPJ",
        "regiao": "centro",
        "areas_atendidas": ["civel"],
        "telefone": "(31) 3000-0000",
        "email": "assistencia@outro-npj.br",
        "logradouro": "Rua X",
        "numero": "1",
        "bairro": "Centro",
        "cep": "30000-000",
        "cidade": "Belo Horizonte",
        "estado": "MG",
    }


def _atendido(_: Ids) -> dict[str, Any]:
    return {
        "nome": "Atendido do outro NPJ",
        "data_nascimento": "1990-01-15",
        "cpf": "777.777.777-77",
        "telefone": "(31) 3333-4444",
        "celular": "(31) 98765-4321",
        "email": "atendido@outro-npj.br",
        "estado_civil": "solteiro",
        "logradouro": "Rua X",
        "numero": "1",
        "bairro": "Centro",
        "cep": "30000-000",
        "cidade": "Belo Horizonte",
        "estado": "MG",
        "como_conheceu": "assist",
        "procurou_outro_local": "nao",
        "pj_constituida": "nao",
        "status": 1,
    }


def _assistido(_: Ids) -> dict[str, Any]:
    return {
        "sexo": "M",
        "profissao": "Pedreiro",
        "raca": "parda",
        "rg": "12.345.678",
        "grau_instrucao": "medio_comp",
        "salario": 1000.0,
        "beneficio": "nao",
        "contribui_inss": "sim",
        "qtd_pessoas_moradia": 3,
        "renda_familiar": 2000.0,
        "participacao_renda": "principal",
        "tipo_moradia": "propria_quitada",
        "possui_outros_imoveis": False,
        "possui_veiculos": False,
        "doenca_grave_familia": "nao",
    }


def _usuario(_: Ids) -> dict[str, Any]:
    return {
        "email": "estagiario@outro-npj.br",
        "nome": "Estagiário do outro NPJ",
        "urole": "estag_direito",
        "sexo": "F",
        "rg": "1",
        "cpf": "111.222.333-44",
        "profissao": "Estudante",
        "estado_civil": "solteiro",
        "nascimento": "1999-01-01",
        "celular": "(31) 99999-0000",
        "data_entrada": "2026-01-01",
        "bolsista": False,
        "cert_atuacao_DAJ": "nao",
        "logradouro": "Rua X",
        "numero": "1",
        "bairro": "Centro",
        "cep": "30000-000",
        "cidade": "Belo Horizonte",
        "estado": "MG",
        "unidade_ids": [UNIDADE_OUTRO],
        "telefone": None,
        "oab": None,
        "obs": None,
        "data_saida": None,
        "matricula": None,
        "tipo_bolsa": None,
        "horario_atendimento": None,
        "suplente": None,
        "ferias": None,
        "inicio_bolsa": None,
        "fim_bolsa": None,
        "complemento": None,
    }


def _dias(quantidade: int) -> list[str]:
    base = date.today() + timedelta(days=1)
    return [(base + timedelta(days=i)).isoformat() for i in range(quantidade)]


def _janela() -> dict[str, str]:
    abertura = datetime.now() - timedelta(days=1)
    return {
        "data_abertura": abertura.isoformat(timespec="seconds"),
        "data_fechamento": (abertura + timedelta(days=30)).isoformat(timespec="seconds"),
    }


PERIODO = "data_inicio=2000-01-01&data_final=2100-12-31"

_CASO = {"caso_id": "caso"}

ROTAS: dict[tuple[str, str], Rota] = {
    # --- públicas ---
    ("GET", "/static/<path:filename>"): Rota("publica"),
    ("POST", "/api/auth/login"): Rota("publica"),
    ("POST", "/api/auth/forgot-password"): Rota("publica"),
    ("POST", "/api/auth/reset-password"): Rota("publica"),
    ("GET", "/api/auth/reset-password/<token>/validate"): Rota("publica"),
    # --- arquivos gerais ---
    ("GET", "/api/arquivo/"): Rota("colecao"),
    ("POST", "/api/arquivo/"): Rota(
        "escrita",
        form=lambda _: {"titulo": "Outro", "arquivo": (BytesIO(b"x"), "outro.docx")},
    ),
    ("GET", "/api/arquivo/<int:id>"): Rota("id", {"id": "arquivo"}),
    ("PUT", "/api/arquivo/<int:id>"): Rota("id", {"id": "arquivo"}, form=lambda _: {"titulo": "Alterado"}),
    ("DELETE", "/api/arquivo/<int:id>"): Rota("id", {"id": "arquivo"}),
    ("GET", "/api/arquivo/<int:id>/download"): Rota("id", {"id": "arquivo"}),
    # --- assistências judiciárias ---
    ("GET", "/api/assistencia_judiciaria"): Rota("colecao", query=f"search={BUSCA}"),
    ("POST", "/api/assistencia_judiciaria/"): Rota("escrita", json=_assistencia),
    ("GET", "/api/assistencia_judiciaria/<int:id>"): Rota("id", {"id": "assistencia"}),
    ("PUT", "/api/assistencia_judiciaria/<int:id>"): Rota("id", {"id": "assistencia"}, json=_assistencia),
    ("DELETE", "/api/assistencia_judiciaria/<int:id>"): Rota("id", {"id": "assistencia"}),
    ("POST", "/api/assistencia_judiciaria/<int:id>/encaminhar"): Rota(
        "id", {"id": "assistencia"}, json=lambda ids: {"id_orientacao": ids["orientacao"]}
    ),
    ("DELETE", "/api/assistencia_judiciaria/<int:id>/orientacoes/<int:id_orientacao>"): Rota(
        "id", {"id": "assistencia", "id_orientacao": "orientacao"}
    ),
    # --- atendidos e assistidos ---
    ("GET", "/api/atendido/"): Rota("colecao", query=f"search={BUSCA}"),
    ("POST", "/api/atendido/"): Rota("escrita", json=_atendido),
    ("GET", "/api/atendido/<int:id>"): Rota("id", {"id": "atendido"}),
    ("PUT", "/api/atendido/<int:id>"): Rota("id", {"id": "atendido"}, json=lambda _: {"nome": "Alterado"}),
    ("DELETE", "/api/atendido/<int:id>"): Rota("id", {"id": "atendido"}),
    ("PUT", "/api/atendido/<int:id>/assistido"): Rota("id", {"id": "assistido_atendido"}, json=_assistido),
    ("GET", "/api/atendido/<int:id>/casos"): Rota("id", {"id": "atendido"}),
    ("GET", "/api/atendido/<int:id>/orientacoes"): Rota("id", {"id": "atendido"}),
    ("POST", "/api/atendido/<int:id>/tornar-assistido"): Rota("id", {"id": "atendido_livre"}, json=_assistido),
    # --- casos ---
    ("GET", "/api/caso/"): Rota("colecao", query=f"search={BUSCA}"),
    ("POST", "/api/caso/"): Rota("escrita", json=_caso),
    ("GET", "/api/caso/<int:id>"): Rota("id", {"id": "caso"}),
    ("PUT", "/api/caso/<int:id>"): Rota("id", {"id": "caso"}, json=lambda _: {"descricao": "Alterado"}),
    ("DELETE", "/api/caso/<int:id>"): Rota("id", {"id": "caso"}),
    ("PATCH", "/api/caso/<int:id>/deferir"): Rota("id", {"id": "caso"}, json=_sem_corpo),
    ("PATCH", "/api/caso/<int:id>/indeferir"): Rota(
        "id", {"id": "caso"}, json=lambda _: {"justif_indeferimento": "Alterado"}
    ),
    ("GET", "/api/caso/<int:caso_id>/historico"): Rota("id", _CASO),
    ("GET", "/api/caso/<int:caso_id>/arquivos"): Rota("id", _CASO),
    ("POST", "/api/caso/<int:caso_id>/arquivos"): Rota("id", _CASO, form=_pdf),
    ("PUT", "/api/caso/<int:caso_id>/arquivos/<int:arquivo_id>"): Rota(
        "id", {**_CASO, "arquivo_id": "arquivo_caso"}, form=_pdf
    ),
    ("DELETE", "/api/caso/<int:caso_id>/arquivos/<int:arquivo_id>"): Rota(
        "id", {**_CASO, "arquivo_id": "arquivo_caso"}
    ),
    ("GET", "/api/caso/<int:caso_id>/arquivos/<int:arquivo_id>/download"): Rota(
        "id", {**_CASO, "arquivo_id": "arquivo_caso"}
    ),
    ("GET", "/api/caso/<int:caso_id>/eventos"): Rota("id", _CASO),
    ("POST", "/api/caso/<int:caso_id>/eventos"): Rota("id", _CASO, form=_evento),
    ("GET", "/api/caso/<int:caso_id>/eventos/<int:evento_id>"): Rota("id", {**_CASO, "evento_id": "evento"}),
    ("PUT", "/api/caso/<int:caso_id>/eventos/<int:evento_id>"): Rota(
        "id", {**_CASO, "evento_id": "evento"}, form=_evento
    ),
    ("DELETE", "/api/caso/<int:caso_id>/eventos/<int:evento_id>"): Rota("id", {**_CASO, "evento_id": "evento"}),
    ("GET", "/api/caso/<int:caso_id>/eventos/<int:evento_id>/download"): Rota(
        "id", {**_CASO, "evento_id": "evento"}
    ),
    ("GET", "/api/caso/<int:caso_id>/eventos/<int:evento_id>/arquivos/<int:arquivo_id>/download"): Rota(
        "id", {**_CASO, "evento_id": "evento", "arquivo_id": "anexo_evento"}
    ),
    ("DELETE", "/api/caso/<int:caso_id>/eventos/<int:evento_id>/arquivos/<int:arquivo_id>"): Rota(
        "id", {**_CASO, "evento_id": "evento", "arquivo_id": "anexo_evento"}
    ),
    ("GET", "/api/caso/<int:caso_id>/lembretes"): Rota("id", _CASO),
    ("POST", "/api/caso/<int:caso_id>/lembretes"): Rota("id", _CASO, json=_lembrete),
    ("GET", "/api/caso/<int:caso_id>/lembretes/<int:lembrete_id>"): Rota(
        "id", {**_CASO, "lembrete_id": "lembrete"}
    ),
    ("PUT", "/api/caso/<int:caso_id>/lembretes/<int:lembrete_id>"): Rota(
        "id", {**_CASO, "lembrete_id": "lembrete"}, json=_lembrete
    ),
    ("DELETE", "/api/caso/<int:caso_id>/lembretes/<int:lembrete_id>"): Rota(
        "id", {**_CASO, "lembrete_id": "lembrete"}
    ),
    ("GET", "/api/caso/<int:caso_id>/processos"): Rota("id", _CASO),
    ("POST", "/api/caso/<int:caso_id>/processos"): Rota("id", _CASO, json=_processo),
    ("GET", "/api/caso/<int:caso_id>/processos/<int:processo_id>"): Rota(
        "id", {**_CASO, "processo_id": "processo"}
    ),
    ("PUT", "/api/caso/<int:caso_id>/processos/<int:processo_id>"): Rota(
        "id", {**_CASO, "processo_id": "processo"}, json=_processo
    ),
    ("DELETE", "/api/caso/<int:caso_id>/processos/<int:processo_id>"): Rota(
        "id", {**_CASO, "processo_id": "processo"}
    ),
    # --- fila de atendimento ---
    ("GET", "/api/fila_atendimento/"): Rota("colecao"),
    ("GET", "/api/fila_atendimento/preview"): Rota("colecao"),
    ("POST", "/api/fila_atendimento/"): Rota(
        "escrita", json=lambda ids: {"id_atendido": ids["meu_atendido"], "prioridade": 0, "psicologia": False}
    ),
    ("POST", "/api/fila_atendimento/<int:id>/chamar"): Rota("id", {"id": "fila"}, json=_sem_corpo),
    ("POST", "/api/fila_atendimento/<int:id>/cancelar"): Rota("id", {"id": "fila"}, json=_sem_corpo),
    # --- notificações ---
    ("GET", "/api/notificacao/"): Rota("colecao"),
    ("GET", "/api/notificacao/nao-lidas"): Rota("colecao"),
    ("PATCH", "/api/notificacao/<int:id>/lida"): Rota("id", {"id": "notificacao"}, json=_sem_corpo),
    ("PATCH", "/api/notificacao/<int:id>/arquivada"): Rota("id", {"id": "notificacao"}, json=_sem_corpo),
    ("PATCH", "/api/notificacao/lidas"): Rota("escrita", json=_sem_corpo),
    ("PATCH", "/api/notificacao/arquivadas"): Rota("escrita", json=_sem_corpo),
    # --- orientação jurídica ---
    ("GET", "/api/orientacao_juridica"): Rota("colecao", query=f"search={BUSCA}"),
    ("POST", "/api/orientacao_juridica/"): Rota("escrita", json=_orientacao),
    ("GET", "/api/orientacao_juridica/<int:id>"): Rota("id", {"id": "orientacao"}),
    ("PUT", "/api/orientacao_juridica/<int:id>"): Rota("id", {"id": "orientacao"}, json=_orientacao),
    ("DELETE", "/api/orientacao_juridica/<int:id>"): Rota("id", {"id": "orientacao"}),
    # --- plantão ---
    ("GET", "/api/plantao/"): Rota("colecao"),
    ("GET", "/api/plantao/configuracao"): Rota("colecao"),
    ("GET", "/api/plantao/escalas"): Rota("colecao"),
    ("PUT", "/api/plantao/configuracao"): Rota("escrita", json=lambda _: {"dias": _dias(2), **_janela()}),
    ("POST", "/api/plantao/escalas"): Rota(
        "escrita", json=lambda _: {"nome": "Escala do outro NPJ", "dias": _dias(2), **_janela()}
    ),
    ("POST", "/api/plantao/escalas/<int:escala_id>/cancelar"): Rota("id", {"escala_id": "escala"}, json=_sem_corpo),
    ("POST", "/api/plantao/marcacoes"): Rota("escrita", json=lambda _: {"data": _dias(1)[0]}),
    ("DELETE", "/api/plantao/marcacoes"): Rota("escrita"),
    # --- presença ---
    ("GET", "/api/presenca/registro"): Rota("colecao"),
    ("GET", "/api/presenca/confirmacao"): Rota("colecao"),
    ("POST", "/api/presenca/registro"): Rota("escrita", json=lambda _: {"hora": "08:00"}),
    ("POST", "/api/presenca/confirmacao"): Rota(
        "escrita",
        status=(404,),
        json=lambda ids: {"presencas": [{"id": ids["presenca"], "confirmacao": "confirmar"}], "plantoes": []}
    ),
    # --- relatórios ---
    ("GET", "/api/relatorio/casos-cadastrados"): Rota("colecao", query=PERIODO),
    ("GET", "/api/relatorio/casos-por-status"): Rota("colecao", query=PERIODO),
    ("GET", "/api/relatorio/casos-por-orientacao"): Rota("colecao", query=PERIODO),
    ("GET", "/api/relatorio/horarios"): Rota("colecao", query=PERIODO),
    # --- roteiro ---
    ("GET", "/api/roteiro"): Rota("colecao"),
    ("PUT", "/api/roteiro/"): Rota("escrita", json=lambda _: {"area_direito": "civel", "link": "https://outro-npj.br"}),
    # --- busca global ---
    ("GET", "/api/search/"): Rota("colecao", query=f"q={BUSCA}"),
    # --- unidades ---
    ("GET", "/api/unidades/"): Rota("colecao", query="incluir_inativas=true"),
    ("POST", "/api/unidades/"): Rota("escrita", json=lambda _: {"nome": "Belo Horizonte", "sigla": "BH"}),
    ("PUT", "/api/unidades/<int:id>"): Rota("id", {"id": "unidade"}, json=lambda _: {"nome": "Alterada"}),
    # --- usuários ---
    ("GET", "/api/user/"): Rota("colecao", query="show_inactive=true"),
    ("GET", "/api/user/opcoes"): Rota("colecao"),
    ("GET", "/api/user/me"): Rota("colecao"),
    ("POST", "/api/user/"): Rota("escrita", json=_usuario, motivos=frozenset({MOTIVO_EMAIL_UNICO})),
    ("PUT", "/api/user/me"): Rota(
        "escrita", json=lambda _: {"nome": "Admin Outro NPJ"}, motivos=frozenset({MOTIVO_EMAIL_UNICO})
    ),
    ("GET", "/api/user/<int:id>"): Rota("id", {"id": "usuario"}),
    ("PUT", "/api/user/<int:id>"): Rota(
        "id", {"id": "usuario"}, json=lambda _: {"nome": "Alterado"}, motivos=frozenset({MOTIVO_EMAIL_UNICO})
    ),
    ("DELETE", "/api/user/<int:id>"): Rota("id", {"id": "usuario"}),
    ("PUT", "/api/user/<int:id>/password"): Rota(
        "id", {"id": "usuario"}, json=lambda _: {"newPassword": "senhanova123", "fromAdmin": True}
    ),
}

# Rotas públicas que rodam sem tenant, e com qual motivo.
MOTIVOS_PUBLICOS = {
    ("POST", "/api/auth/login"): {MOTIVO_LOGIN},
    ("POST", "/api/auth/forgot-password"): {MOTIVO_LOGIN},
    ("POST", "/api/auth/reset-password"): {MOTIVO_TOKEN_SENHA},
    ("GET", "/api/auth/reset-password/<token>/validate"): {MOTIVO_TOKEN_SENHA},
}


def _rotas_do_app(app: Flask) -> set[tuple[str, str]]:
    return {
        (metodo, regra.rule)
        for regra in app.url_map.iter_rules()
        for metodo in regra.methods - {"HEAD", "OPTIONS"}
    }


def _de(categoria: str) -> list[tuple[str, str]]:
    return [chave for chave, rota in ROTAS.items() if rota.categoria == categoria]


def _id_teste(chave: tuple[str, str]) -> str:
    return f"{chave[0]} {chave[1]}"


# --------------------------------------------------------------------------- #
# Dados de partida
# --------------------------------------------------------------------------- #


def _ok(response) -> Any:
    assert response.status_code in (200, 201), (response.status_code, response.get_json())
    return get_success_data(response)


def _criar_dados_da_daj(client: FlaskClient, h: dict[str, str]) -> Ids:
    ids: Ids = {"unidade": UNIDADE_BH}
    ids["usuario"] = _ok(client.get("/api/user/me", headers=h))["id"]

    def atendido(sufixo: str, cpf: str) -> int:
        corpo = {**_atendido({}), "nome": f"{MARCA} Atendido {sufixo}", "cpf": cpf, "email": f"{sufixo}@daj.br"}
        return _ok(client.post("/api/atendido/", json=corpo, headers=h))["id"]

    ids["atendido"] = atendido("um", "901.000.000-01")
    ids["atendido_livre"] = atendido("dois", "901.000.000-02")
    ids["assistido_atendido"] = atendido("tres", "901.000.000-03")
    _ok(client.post(f"/api/atendido/{ids['assistido_atendido']}/tornar-assistido", json=_assistido({}), headers=h))

    caso = {
        "id_usuario_responsavel": ids["usuario"],
        "area_direito": "civel",
        "situacao_deferimento": "deferido",
        "descricao": f"{MARCA} caso",
        "ids_clientes": [ids["atendido"]],
    }
    ids["caso"] = _ok(client.post("/api/caso/", json=caso, headers=h))["id"]
    c = ids["caso"]
    ids["processo"] = _ok(
        client.post(f"/api/caso/{c}/processos", json={"especie": f"{MARCA} processo", "numero": "9990001", "status": True}, headers=h)
    )["id"]
    ids["lembrete"] = _ok(
        client.post(
            f"/api/caso/{c}/lembretes",
            json={"id_usuario": ids["usuario"], "data_lembrete": "2026-09-15T00:00:00", "descricao": f"{MARCA} lembrete"},
            headers=h,
        )
    )["id"]
    evento = _ok(
        client.post(
            f"/api/caso/{c}/eventos",
            data={
                "tipo": "Audiência",
                "data_evento": "2026-06-20",
                "descricao": f"{MARCA} evento",
                "status": "true",
                "arquivo": (BytesIO(b"%PDF-1.4 daj"), f"{MARCA}-evento.pdf"),
            },
            headers=h,
            content_type="multipart/form-data",
        )
    )
    ids["evento"] = evento["id"]
    ids["anexo_evento"] = evento["arquivos"][0]["id"]
    arquivo_caso = _ok(
        client.post(
            f"/api/caso/{c}/arquivos",
            data={"arquivo": (BytesIO(b"%PDF-1.4 daj"), f"{MARCA}-caso.pdf")},
            headers=h,
            content_type="multipart/form-data",
        )
    )
    ids["arquivo_caso"] = arquivo_caso["id"]

    ids["orientacao"] = _ok(
        client.post(
            "/api/orientacao_juridica/",
            json={"area_direito": "civel", "descricao": f"{MARCA} orientação", "atendidos_ids": [ids["atendido"]]},
            headers=h,
        )
    )["id"]
    ids["assistencia"] = _ok(
        client.post(
            "/api/assistencia_judiciaria/",
            json={**_assistencia({}), "nome": f"{MARCA} assistência", "email": "assistencia@daj.br"},
            headers=h,
        )
    )["id"]
    _ok(
        client.post(
            f"/api/assistencia_judiciaria/{ids['assistencia']}/encaminhar",
            json={"id_orientacao": ids["orientacao"]},
            headers=h,
        )
    )
    ids["arquivo"] = _ok(
        client.post(
            "/api/arquivo/",
            data={"titulo": f"{MARCA} arquivo", "descricao": MARCA, "arquivo": (BytesIO(b"daj"), "daj.docx")},
            headers=h,
            content_type="multipart/form-data",
        )
    )["id"]
    ids["fila"] = _ok(
        client.post(
            "/api/fila_atendimento/",
            json={"id_atendido": ids["atendido_livre"], "prioridade": 0, "psicologia": False},
            headers=h,
        )
    )["id"]
    ids["escala"] = _ok(
        client.post("/api/plantao/escalas", json={"nome": f"{MARCA} escala", "dias": _dias(2), **_janela()}, headers=h)
    )["id"]
    _ok(client.post("/api/presenca/registro", json={"hora": "08:00"}, headers=h))
    _ok(client.put("/api/roteiro/", json={"area_direito": "civel", "link": f"https://{MARCA}.br"}, headers=h))

    with sem_tenant("teste: aviso e notificação da DAJ"):
        session = db_session_module.get_session()
        try:
            tabela = metadata.tables["notificacao"]
            ids["notificacao"] = session.execute(
                tabela.insert().values(
                    tenant_id=TENANT_DAJ,
                    id_usu_notificar=ids["usuario"],
                    acao=f"{MARCA} notificação",
                    data=date.today(),
                    tipo="caso",
                    lida=False,
                    data_criacao=datetime.now(),
                )
            ).lastrowid
            session.execute(
                tabela.insert().values(
                    tenant_id=TENANT_DAJ,
                    acao=f"{MARCA} aviso geral",
                    data=date.today(),
                    tipo="plantao",
                    lida=False,
                    data_criacao=datetime.now(),
                )
            )
            session.commit()
            registro = metadata.tables["registro_entrada"]
            ids["presenca"] = session.execute(
                select(registro.c.id)
                .where(registro.c.tenant_id == TENANT_DAJ, registro.c.id_usuario == ids["usuario"])
                .order_by(registro.c.id.desc())
            ).scalars().first()
        finally:
            session.close()
    return ids


def _fotografia_da_daj() -> dict[str, list[str]]:
    """Todas as linhas do tenant 1, tabela a tabela, em forma comparável."""
    foto: dict[str, list[str]] = {}
    with sem_tenant("teste: fotografia dos dados da DAJ"):
        session = db_session_module.get_session()
        try:
            for tabela in metadata.sorted_tables:
                if tabela.name in TABELAS_GLOBAIS:
                    continue
                linhas = session.execute(
                    select(tabela).where(tabela.c.tenant_id == TENANT_DAJ)
                ).mappings()
                foto[tabela.name] = sorted(json.dumps(dict(linha), default=str, sort_keys=True) for linha in linhas)
        finally:
            session.close()
    return foto


def _url(regra: str, params: dict[str, str], ids: Ids) -> str:
    url = regra
    for nome, chave in params.items():
        url = url.replace(f"<int:{nome}>", str(ids[chave]))
    assert "<" not in url, f"Parâmetro sem id em {regra}: {url}"
    return url


@dataclass
class Cenario:
    ids: Ids
    daj: dict[str, str]
    outro: dict[str, str]
    # Resposta de cada coleção ao outro NPJ antes de a DAJ ter dados.
    antes: dict[tuple[str, str], tuple[int, Any]]
    foto: dict[str, list[str]]


def _chamar(client: FlaskClient, metodo: str, regra: str, rota: Rota, ids: Ids, headers: dict[str, str]):
    url = _url(regra, rota.params, ids)
    if rota.query:
        url = f"{url}?{rota.query}"
    kwargs: dict[str, Any] = {"headers": headers}
    if rota.form is not None:
        kwargs["data"] = rota.form(ids)
        kwargs["content_type"] = "multipart/form-data"
    elif rota.json is not None:
        kwargs["json"] = rota.json(ids)
    return client.open(url, method=metodo, **kwargs)


def _corpo(response) -> Any:
    return response.get_json(silent=True)


@pytest.fixture(scope="module")
def cenario(app: Flask, client: FlaskClient, create_admin_user: None) -> Cenario:
    with app.app_context():
        criar_usuario(OUTRO_EMAIL, OUTRO_SENHA, "admin", "Admin Outro NPJ", tenant_id=TENANT_OUTRO)
    outro = headers_para(client, OUTRO_EMAIL, OUTRO_SENHA, unidade=UNIDADE_OUTRO)
    daj = headers_para(client, TEST_ADMIN_EMAIL, TEST_ADMIN_PASSWORD)

    # Registros do próprio outro NPJ, referenciados pelas escritas dele. Criados
    # antes de fotografar as coleções, para não mudarem a comparação.
    meus = {"meu_usuario": _ok(client.get("/api/user/me", headers=outro))["id"]}
    corpo = {**_atendido({}), "nome": "Atendido do outro NPJ", "cpf": "902.000.000-01", "email": "um@outro-npj.br"}
    meus["meu_atendido"] = _ok(client.post("/api/atendido/", json=corpo, headers=outro))["id"]

    antes = {}
    for chave in _de("colecao"):
        response = _chamar(client, *chave, ROTAS[chave], {}, outro)
        antes[chave] = (response.status_code, _corpo(response))

    ids = {**_criar_dados_da_daj(client, daj), **meus}
    return Cenario(ids=ids, daj=daj, outro=outro, antes=antes, foto=_fotografia_da_daj())


def _conferir_resposta(response, cenario: Cenario) -> None:
    texto = response.get_data(as_text=True)
    assert MARCA not in texto, texto[:500]
    assert TEST_ADMIN_EMAIL not in texto, texto[:500]


def _motivos(caplog) -> set[str]:
    return {
        r.args[0]
        for r in caplog.records
        if r.name == LOGGER_CONTEXTO and r.msg == "Trecho sem tenant: %s"
    }


# --------------------------------------------------------------------------- #
# Classificação
# --------------------------------------------------------------------------- #


def test_toda_rota_esta_classificada(app: Flask):
    do_app = {c for c in _rotas_do_app(app) if not c[1].startswith(PREFIXO_PLATAFORMA)}
    sem_classificacao = sorted(do_app - ROTAS.keys())
    assert not sem_classificacao, (
        "Rotas sem classificação de vazamento entre tenants. Classifique cada uma em "
        f"ROTAS, em tests/api/test_tenant_vazamento.py: {sem_classificacao}"
    )
    obsoletas = sorted(ROTAS.keys() - do_app)
    assert not obsoletas, f"Rotas classificadas que não existem mais no app: {obsoletas}"


def test_classificacao_e_coerente():
    for (metodo, regra), rota in ROTAS.items():
        assert rota.categoria in {"publica", "id", "colecao", "escrita"}, regra
        assert not regra.startswith(PREFIXO_PLATAFORMA), regra
        tem_id = "<int:" in regra
        if rota.categoria == "id":
            assert tem_id and rota.params, regra
        if rota.categoria == "colecao":
            assert metodo == "GET" and not tem_id, regra
        if rota.categoria == "escrita":
            assert metodo != "GET" and not tem_id, regra
    assert set(MOTIVOS_PUBLICOS) <= set(_de("publica"))


def test_rotas_da_plataforma_recusam_token_de_npj(app: Flask, client: FlaskClient, cenario: Cenario):
    # As rotas da plataforma (PR 7) têm testes próprios. Aqui só se garante que
    # um token de NPJ nunca as abre.
    for metodo, regra in sorted(_rotas_do_app(app)):
        if not regra.startswith(PREFIXO_PLATAFORMA) or (metodo, regra) in PUBLICAS_PLATAFORMA:
            continue
        url = regra
        for parte in regra.split("<")[1:]:
            url = url.replace("<" + parte.split(">")[0] + ">", "1")
        response = client.open(url, method=metodo, headers=cenario.outro, json={})
        assert response.status_code in (401, 403), (metodo, regra, response.status_code)


def test_credenciais_de_npj_nao_entram_na_plataforma(app: Flask, client: FlaskClient, cenario: Cenario):
    if ("POST", "/api/plataforma/auth/login") not in _rotas_do_app(app):
        pytest.skip("área da plataforma ainda não existe")
    response = client.post(
        "/api/plataforma/auth/login", json={"email": OUTRO_EMAIL, "password": OUTRO_SENHA}
    )
    assert response.status_code == 401, (response.status_code, _corpo(response))


# --------------------------------------------------------------------------- #
# Varredura
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("chave", _de("colecao"), ids=_id_teste)
def test_colecao_nao_mostra_dados_de_outro_npj(client, cenario, caplog, chave):
    caplog.set_level(logging.INFO, logger=LOGGER_CONTEXTO)
    response = _chamar(client, *chave, ROTAS[chave], cenario.ids, cenario.outro)
    motivos = _motivos(caplog)
    _conferir_resposta(response, cenario)
    assert (response.status_code, _corpo(response)) == cenario.antes[chave]
    assert motivos <= {MOTIVO_AUTENTICACAO} | ROTAS[chave].motivos


@pytest.mark.parametrize("chave", [c for c in _de("id") if c[0] == "GET"], ids=_id_teste)
def test_leitura_por_id_de_outro_npj_e_recusada(client, cenario, caplog, chave):
    caplog.set_level(logging.INFO, logger=LOGGER_CONTEXTO)
    response = _chamar(client, *chave, ROTAS[chave], cenario.ids, cenario.outro)
    motivos = _motivos(caplog)
    _conferir_resposta(response, cenario)
    if response.status_code not in (403, 404):
        # Sublistas por id (casos do atendido, histórico do caso) respondem
        # lista vazia a um id que não acham. Vale, desde que o id da DAJ dê a
        # mesma resposta que um id inexistente: senão a rota revela que ele
        # existe.
        inexistente = {chave_id: ID_INEXISTENTE for chave_id in cenario.ids}
        controle = _chamar(client, *chave, ROTAS[chave], inexistente, cenario.outro)
        assert (response.status_code, _corpo(response)) == (controle.status_code, _corpo(controle)), (
            response.status_code,
            _corpo(response),
        )
    assert motivos <= {MOTIVO_AUTENTICACAO} | ROTAS[chave].motivos


@pytest.mark.parametrize("chave", [c for c in _de("id") if c[0] != "GET"], ids=_id_teste)
def test_escrita_por_id_de_outro_npj_e_recusada(client, cenario, caplog, chave):
    caplog.set_level(logging.INFO, logger=LOGGER_CONTEXTO)
    response = _chamar(client, *chave, ROTAS[chave], cenario.ids, cenario.outro)
    motivos = _motivos(caplog)
    _conferir_resposta(response, cenario)
    assert response.status_code in (403, 404), (response.status_code, _corpo(response))
    assert _fotografia_da_daj() == cenario.foto
    assert motivos <= {MOTIVO_AUTENTICACAO} | ROTAS[chave].motivos


@pytest.mark.parametrize("chave", _de("escrita"), ids=_id_teste)
def test_escrita_no_proprio_npj_nao_toca_outro(client, cenario, caplog, chave):
    caplog.set_level(logging.INFO, logger=LOGGER_CONTEXTO)
    response = _chamar(client, *chave, ROTAS[chave], cenario.ids, cenario.outro)
    motivos = _motivos(caplog)
    _conferir_resposta(response, cenario)
    esperado = ROTAS[chave].status
    assert response.status_code in esperado, (response.status_code, _corpo(response))
    assert _fotografia_da_daj() == cenario.foto
    assert motivos <= {MOTIVO_AUTENTICACAO} | ROTAS[chave].motivos


# Referências a ids da DAJ no corpo de uma criação. Os services conferem cada
# id no repositório do tenant e recusam com 400, igual a um id inexistente.
# Sem isso, a referência cruzada era gravada (a leitura não mostrava nada).
REFERENCIAS_CRUZADAS = [
    ("POST", "/api/caso/"),
    ("POST", "/api/orientacao_juridica/"),
    ("POST", "/api/fila_atendimento/"),
    ("POST", "/api/caso/<int:caso_id>/lembretes"),
]


@pytest.mark.parametrize("chave", REFERENCIAS_CRUZADAS, ids=_id_teste)
def test_criacao_com_referencia_a_outro_npj_e_recusada(client, cenario, chave):
    rota = ROTAS.get(chave)
    # A mesma escrita que passa com os ids do próprio NPJ, agora com os da DAJ.
    ids = {**cenario.ids, "meu_usuario": cenario.ids["usuario"], "meu_atendido": cenario.ids["atendido"]}
    if chave == ("POST", "/api/caso/<int:caso_id>/lembretes"):
        # Um caso do próprio NPJ, com o lembrete apontando para usuário da DAJ.
        proprio = client.post(
            "/api/caso/",
            json={
                "id_usuario_responsavel": cenario.ids["meu_usuario"],
                "area_direito": "civel",
                "situacao_deferimento": "deferido",
            },
            headers=cenario.outro,
        )
        ids["caso"] = get_success_data(proprio)["id"]
        rota = Rota("escrita", _CASO, json=_lembrete)
    assert rota is not None
    response = _chamar(client, *chave, rota, ids, cenario.outro)
    assert response.status_code == 400, (response.status_code, _corpo(response))
    # Mesma resposta de um id que não existe: não revela que o da DAJ existe.
    inexistente = {**ids, "meu_usuario": ID_INEXISTENTE, "meu_atendido": ID_INEXISTENTE}
    controle = _chamar(client, *chave, rota, inexistente, cenario.outro)
    assert (response.status_code, _corpo(response)) == (controle.status_code, _corpo(controle))
    assert _fotografia_da_daj() == cenario.foto


def test_dono_continua_lendo_os_proprios_dados(client, cenario):
    # Controle: os ids usados na varredura existem e são lidos pela DAJ.
    ids, h = cenario.ids, cenario.daj
    for url in (
        f"/api/atendido/{ids['atendido']}",
        f"/api/caso/{ids['caso']}",
        f"/api/caso/{ids['caso']}/processos/{ids['processo']}",
        f"/api/caso/{ids['caso']}/eventos/{ids['evento']}",
        f"/api/caso/{ids['caso']}/lembretes/{ids['lembrete']}",
        f"/api/caso/{ids['caso']}/arquivos/{ids['arquivo_caso']}/download",
        f"/api/orientacao_juridica/{ids['orientacao']}",
        f"/api/assistencia_judiciaria/{ids['assistencia']}",
        f"/api/arquivo/{ids['arquivo']}",
        f"/api/user/{ids['usuario']}",
    ):
        assert client.get(url, headers=h).status_code == 200, url
    busca = client.get(f"/api/search/?q={BUSCA}", headers=h)
    assert MARCA in busca.get_data(as_text=True)


# --------------------------------------------------------------------------- #
# Trechos sem tenant nas rotas públicas
# --------------------------------------------------------------------------- #


def test_login_so_roda_sem_tenant_para_achar_o_npj(client, cenario, caplog):
    caplog.set_level(logging.INFO, logger=LOGGER_CONTEXTO)
    response = client.post("/api/auth/login", json={"email": OUTRO_EMAIL, "password": OUTRO_SENHA})
    assert response.status_code == 200
    assert _motivos(caplog) == MOTIVOS_PUBLICOS[("POST", "/api/auth/login")]


def test_recuperacao_de_senha_so_roda_sem_tenant_nos_trechos_previstos(client, cenario, caplog):
    caplog.set_level(logging.INFO, logger=LOGGER_CONTEXTO)
    response = client.post("/api/auth/forgot-password", json={"email": OUTRO_EMAIL})
    assert response.status_code == 200
    assert _motivos(caplog) <= MOTIVOS_PUBLICOS[("POST", "/api/auth/forgot-password")]

    caplog.clear()
    response = client.get("/api/auth/reset-password/token-inexistente/validate")
    assert response.status_code < 500
    assert _motivos(caplog) <= MOTIVOS_PUBLICOS[("GET", "/api/auth/reset-password/<token>/validate")]

    caplog.clear()
    response = client.post(
        "/api/auth/reset-password", json={"token": "token-inexistente", "password": "senhanova123"}
    )
    assert response.status_code < 500
    assert _motivos(caplog) <= MOTIVOS_PUBLICOS[("POST", "/api/auth/reset-password")]
