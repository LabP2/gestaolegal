"""Cliente do DJEN e tratamento do HTML, com transporte falso (sem rede)."""

import json
from datetime import date

import pytest

from gestaolegal.integrations import djen_client
from gestaolegal.integrations.djen_client import DJENClient, DJENError, RespostaHTTP
from gestaolegal.integrations.djen_html import html_seguro, resumo, texto_plano
from gestaolegal.utils.cnj import mascarar_cnj, normalizar_cnj

from .djen_fixtures import HTML_PUBLICACAO, TransporteFalso, item_djen, resposta

NUMERO = "10000011120268130001"


class Dormir:
    def __init__(self):
        self.esperas: list[float] = []

    def __call__(self, segundos: float) -> None:
        self.esperas.append(segundos)


class TestCNJ:
    @pytest.mark.parametrize(
        "entrada,esperado",
        [
            ("1000001-11.2026.8.13.0001", NUMERO),
            (" 1000001-11.2026.8.13.0001 ", NUMERO),
            (NUMERO, NUMERO),
            ("1000001 11 2026 8 13 0001", NUMERO),
            ("0012345-67.2010", None),  # fora do padrão
            ("123456789012345678901", None),  # 21 dígitos
            ("", None),
            (None, None),
            ("abc", None),
        ],
    )
    def test_normalizar(self, entrada, esperado):
        assert normalizar_cnj(entrada) == esperado

    def test_mascara(self):
        assert mascarar_cnj(NUMERO) == "1000001-11.2026.8.13.0001"
        assert mascarar_cnj("123") == "123"


class TestCliente:
    def test_busca_por_processo_converte_os_campos(self):
        transporte = TransporteFalso()
        transporte.por_processo[NUMERO] = [item_djen(1, NUMERO)]
        cliente = DJENClient(transporte=transporte, dormir=Dormir())
        (item,) = cliente.buscar_por_processo(NUMERO)
        assert item.id_djen == 1
        assert item.numero_processo == NUMERO
        assert item.numero_processo_mascara == "1000001-11.2026.8.13.0001"
        assert item.data_disponibilizacao == date(2026, 11, 3)
        assert item.sigla_tribunal == "TJMG"
        assert item.tipo_comunicacao == "Intimação"
        assert item.destinatarios[0] == {"nome": "Fulana de Tal Fictícia", "polo": "A"}
        assert item.advogados == [
            {"nome": "Advogada Fictícia", "numero_oab": "123456", "uf_oab": "MG"}
        ]
        assert item.ativo is True
        assert transporte.chamadas[0]["numeroProcesso"] == NUMERO

    def test_busca_por_oab_manda_periodo_e_uf_maiuscula(self):
        transporte = TransporteFalso()
        cliente = DJENClient(transporte=transporte, dormir=Dormir())
        cliente.buscar_por_oab("123456", "mg", date(2026, 11, 1), date(2026, 11, 3))
        params = transporte.chamadas[0]
        assert params["numeroOab"] == "123456"
        assert params["ufOab"] == "MG"
        assert params["dataDisponibilizacaoInicio"] == "2026-11-01"
        assert params["dataDisponibilizacaoFim"] == "2026-11-03"

    def test_pagina_ate_acabar(self):
        itens = [item_djen(i, NUMERO) for i in range(1, 6)]
        paginas = {1: itens[:2], 2: itens[2:4], 3: itens[4:]}

        def transporte(url, timeout):
            from urllib.parse import parse_qs, urlparse

            q = parse_qs(urlparse(url).query)
            return resposta(paginas[int(q["pagina"][0])], count=5)

        cliente = DJENClient(transporte=transporte, dormir=Dormir(), itens_por_pagina=2)
        assert [i.id_djen for i in cliente.buscar_por_processo(NUMERO)] == [1, 2, 3, 4, 5]
        assert cliente.requisicoes == 3

    def test_limite_de_paginas(self):
        cliente = DJENClient(
            transporte=lambda u, t: resposta([item_djen(1, NUMERO)], count=999),
            dormir=Dormir(),
            itens_por_pagina=1,
            max_paginas=3,
        )
        cliente.buscar_por_processo(NUMERO)
        assert cliente.requisicoes == 3

    def test_espera_quando_o_limite_de_taxa_esta_no_fim(self):
        dormir = Dormir()
        cliente = DJENClient(
            transporte=lambda u, t: resposta([], restante=1), dormir=dormir
        )
        cliente.buscar_por_processo(NUMERO)
        assert dormir.esperas == [djen_client.ESPERA_LIMITE_S]

    def test_nao_espera_com_folga_no_limite(self):
        dormir = Dormir()
        DJENClient(transporte=lambda u, t: resposta([], restante=10), dormir=dormir).buscar_por_processo(NUMERO)
        assert dormir.esperas == []

    def test_429_faz_backoff_e_tenta_de_novo(self):
        respostas = [
            RespostaHTTP(429, {"retry-after": "7"}, b""),
            RespostaHTTP(429, {}, b""),
            resposta([item_djen(1, NUMERO)]),
        ]
        dormir = Dormir()
        cliente = DJENClient(transporte=lambda u, t: respostas.pop(0), dormir=dormir)
        assert len(cliente.buscar_por_processo(NUMERO)) == 1
        assert dormir.esperas == [7.0, djen_client.BACKOFF_429_S * 2]

    def test_429_persistente_vira_erro(self):
        cliente = DJENClient(
            transporte=lambda u, t: RespostaHTTP(429, {}, b""),
            dormir=Dormir(),
            max_tentativas=3,
        )
        with pytest.raises(DJENError, match="3 tentativas"):
            cliente.buscar_por_processo(NUMERO)
        assert cliente.requisicoes == 3

    def test_erro_de_rede_propaga_djen_error(self):
        transporte = TransporteFalso()
        transporte.falhar.add(NUMERO)
        with pytest.raises(DJENError):
            DJENClient(transporte=transporte, dormir=Dormir()).buscar_por_processo(NUMERO)

    def test_resposta_que_nao_e_json(self):
        cliente = DJENClient(
            transporte=lambda u, t: RespostaHTTP(200, {}, b"<html>"), dormir=Dormir()
        )
        with pytest.raises(DJENError, match="JSON"):
            cliente.buscar_por_processo(NUMERO)

    def test_status_4xx_vira_erro(self):
        cliente = DJENClient(
            transporte=lambda u, t: RespostaHTTP(400, {}, b"{}"), dormir=Dormir()
        )
        with pytest.raises(DJENError, match="400"):
            cliente.buscar_por_processo(NUMERO)

    def test_item_sem_id_vira_erro(self):
        corpo = json.dumps({"items": [{"numero_processo": NUMERO}]}).encode()
        cliente = DJENClient(transporte=lambda u, t: RespostaHTTP(200, {}, corpo), dormir=Dormir())
        with pytest.raises(DJENError, match="formato"):
            cliente.buscar_por_processo(NUMERO)

    def test_transporte_padrao_dos_testes_nao_acessa_a_rede(self):
        # O conftest troca o transporte padrão por um que falha.
        with pytest.raises(DJENError, match="rede"):
            DJENClient().buscar_por_processo(NUMERO)


class TestHTML:
    def test_html_seguro_remove_script_eventos_e_javascript(self):
        limpo = html_seguro(HTML_PUBLICACAO)
        for proibido in ("<script", "alert", "onerror", "onclick", "javascript:", "<img", "<a ", "href"):
            assert proibido not in limpo, proibido

    def test_html_seguro_remove_head_e_style_com_o_conteudo(self):
        limpo = html_seguro(HTML_PUBLICACAO)
        assert "Comic Sans" not in limpo
        assert "<style" not in limpo and "<title" not in limpo
        assert "Intimação</title>" not in limpo

    def test_html_seguro_mantem_negrito_e_paragrafos_sem_atributos(self):
        limpo = html_seguro(HTML_PUBLICACAO)
        assert "<b>intimada</b>" in limpo
        assert "<p>Prazo de 15 dias.</p>" in limpo
        assert "ção" in limpo  # entidades convertidas

    def test_texto_simples_e_escapado(self):
        assert html_seguro("a <b\nc & d") == "a &lt;b<br>c &amp; d"
        assert html_seguro("<img src=x onerror=alert(1)>") == ""
        assert html_seguro(None) == ""

    def test_texto_plano(self):
        plano = texto_plano(HTML_PUBLICACAO)
        assert "Comic Sans" not in plano and "alert" not in plano
        assert "Fica a parte intimada do despacho: ção." in plano
        assert "Prazo de 15 dias." in plano
        assert texto_plano("  linha  um \n\n\n linha dois ") == "linha um\n\nlinha dois"

    def test_resumo(self):
        assert resumo("a  b") == "a b"
        assert len(resumo("x" * 600, 500)) == 500
