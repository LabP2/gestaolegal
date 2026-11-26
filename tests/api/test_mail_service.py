"""Layout padrão dos e-mails do sistema (HTML com capivara e rodapé institucional)."""

import email

from gestaolegal import mail
from gestaolegal.utils.mail_service import (
    CID_CAPIVARA,
    INSTITUICOES,
    Botao,
    ConteudoEmail,
    enviar_email,
    enviar_link_recuperacao,
)

DESTINO = "pessoa@exemplo.com"
LINKS = (
    "https://labp2.direito.ufmg.br/",
    "https://www.direito.ufmg.br/",
    "https://ufmg.br/",
)


def _enviar(app, *args):
    with app.app_context(), mail.record_messages() as enviados:
        assert enviar_email(DESTINO, *args) is True
        assert len(enviados) == 1
        return enviados[0]


def test_todo_email_leva_rodape_institucional_no_html_e_no_texto(app):
    mensagem = _enviar(app, "Assunto qualquer", "Primeiro parágrafo.\n\nSegundo.")

    for link in LINKS:
        assert link in mensagem.body
        assert f'href="{link}"' in mensagem.html
    assert "Faculdade de Direito da UFMG" in mensagem.body
    assert "<p" in mensagem.html and "Segundo." in mensagem.html


def test_imagens_vao_inline_em_multipart_related(app):
    mensagem = _enviar(app, "Assunto", "Corpo.")

    with app.app_context():
        mime = email.message_from_bytes(mensagem.as_bytes())
    assert mime.get_content_type() == "multipart/related"
    assert mime["To"] == DESTINO
    assert mime["Subject"] == "Assunto"

    partes = mime.get_payload()
    assert partes[0].get_content_type() == "multipart/alternative"
    cids = {p["Content-ID"] for p in partes[1:]}
    esperados = {f"<{CID_CAPIVARA}>"} | {f"<{i.cid}>" for i in INSTITUICOES}
    assert cids == esperados
    for parte in partes[1:]:
        assert parte.get_content_type() == "image/png"
        assert parte.get_content_disposition() == "inline"
        assert f"cid:{parte['Content-ID'][1:-1]}" in mensagem.html


def test_conteudo_e_escapado_no_html(app):
    conteudo = ConteudoEmail(
        titulo="Título <b>",
        paragrafos=["Olá, <script>alert(1)</script>."],
        botao=Botao("Abrir", "https://gl.exemplo/x?a=1&b=2"),
    )
    mensagem = _enviar(app, "Assunto", conteudo)

    assert "<script>" not in mensagem.html
    assert "&lt;script&gt;" in mensagem.html
    assert 'href="https://gl.exemplo/x?a=1&amp;b=2"' in mensagem.html
    assert "Abrir:\nhttps://gl.exemplo/x?a=1&b=2" in mensagem.body


def test_recuperacao_tem_botao_e_link_em_texto(app):
    url = "https://gl.exemplo/redefinir-senha/abc"
    with app.app_context(), mail.record_messages() as enviados:
        assert enviar_link_recuperacao(DESTINO, "Maria", url) is True
    mensagem = enviados[0]

    assert url in mensagem.body
    assert f'href="{url}"' in mensagem.html
    assert "Escolher nova senha" in mensagem.html
    assert "Olá, Maria." in mensagem.body
