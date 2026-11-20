"""Tratamento do campo `texto` das publicações do DJEN (plano, §4 "HTML").

O campo chega como documento HTML completo (com `<head>`, `<style>` e acentos
em entidades) ou como texto simples. É conteúdo de terceiros:

- `html_seguro` filtra com `nh3` numa lista restrita de tags, sem atributos, e
  remove `head`, `style` e `script` **com o conteúdo**. É o único que o front
  mostra com `{@html}`.
- `texto_plano` tira as tags e converte as entidades (biblioteca padrão), para
  o resumo do evento e para a busca.
"""

import unicodedata
from html import escape
from html.parser import HTMLParser

import nh3

TAGS_PERMITIDAS = frozenset(
    {"p", "b", "strong", "i", "u", "br", "table", "tr", "td", "section", "span"}
)
TAGS_COM_CONTEUDO_REMOVIDO = frozenset({"head", "style", "script", "title"})
# Tags que quebram linha no texto plano.
_BLOCOS = frozenset(
    {"p", "br", "div", "section", "tr", "table", "li", "h1", "h2", "h3", "h4", "h5", "h6"}
)


def _parece_html(texto: str) -> bool:
    return "<" in texto and ">" in texto


def html_seguro(texto: str | None) -> str:
    if not texto:
        return ""
    if not _parece_html(texto):
        # Texto simples: só escapa e preserva as quebras de linha.
        return escape(texto).replace("\r\n", "\n").replace("\n", "<br>")
    return nh3.clean(
        texto,
        tags=set(TAGS_PERMITIDAS),
        attributes={},
        clean_content_tags=set(TAGS_COM_CONTEUDO_REMOVIDO),
        url_schemes=set(),
        link_rel=None,
        strip_comments=True,
    ).strip()


class _Extrator(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.partes: list[str] = []
        self._ignorar = 0

    def handle_starttag(self, tag, attrs):
        if tag in TAGS_COM_CONTEUDO_REMOVIDO:
            self._ignorar += 1
        elif tag in _BLOCOS:
            self.partes.append("\n")

    def handle_startendtag(self, tag, attrs):
        if tag in _BLOCOS:
            self.partes.append("\n")

    def handle_endtag(self, tag):
        if tag in TAGS_COM_CONTEUDO_REMOVIDO:
            self._ignorar = max(0, self._ignorar - 1)
        elif tag in _BLOCOS:
            self.partes.append("\n")

    def handle_data(self, data):
        if not self._ignorar:
            self.partes.append(data)


def texto_plano(texto: str | None) -> str:
    if not texto:
        return ""
    if _parece_html(texto):
        extrator = _Extrator()
        extrator.feed(texto)
        extrator.close()
        bruto = "".join(extrator.partes)
    else:
        bruto = texto
    linhas = (" ".join(linha.split()) for linha in bruto.replace("\xa0", " ").splitlines())
    # Junta linhas em branco seguidas numa só.
    saida: list[str] = []
    for linha in linhas:
        if linha or (saida and saida[-1]):
            saida.append(linha)
    return "\n".join(saida).strip()


def resumo(texto: str, limite: int = 500) -> str:
    texto = " ".join(texto.split())
    if len(texto) <= limite:
        return texto
    return texto[: limite - 1].rstrip() + "…"


def corrigir_caixa(texto: str | None) -> str | None:
    """Conserta a caixa que o DJEN entrega em nomes de classe e órgão.

    A API devolve, por exemplo, "AçãO TRABALHISTA - RITO SUMARíSSIMO": o texto
    em maiúsculas com as letras acentuadas em minúsculas. Quando nenhuma letra
    ASCII está em minúscula, o texto inteiro vai para maiúsculas.
    """
    if not texto:
        return texto
    if any("a" <= c <= "z" for c in texto) or texto == texto.upper():
        return texto
    return texto.upper()


def para_latin1(texto: str | None) -> str | None:
    """Adapta o texto às colunas legadas em latin1 (`eventos.descricao`, `tipo`).

    O latin1 do MySQL é o cp1252. Caracteres de controle C1 (U+0080 a U+009F)
    chegam no DJEN quando a origem leu cp1252 como latin1 (o travessão vira
    U+0096): voltam ao caractere certo. O que o cp1252 não tem perde o acento,
    se for o caso, ou vira "?"; sem isso o INSERT falha com o erro 1366.
    """
    if not texto:
        return texto
    saida: list[str] = []
    for c in texto:
        if "\x80" <= c <= "\x9f":
            try:
                c = bytes([ord(c)]).decode("cp1252")
            except UnicodeDecodeError:
                continue
        try:
            c.encode("cp1252")
        except UnicodeEncodeError:
            base = "".join(
                b for b in unicodedata.normalize("NFKD", c) if not unicodedata.combining(b)
            )
            try:
                base.encode("cp1252")
                c = base
            except UnicodeEncodeError:
                c = "?"
        saida.append(c)
    return "".join(saida)
