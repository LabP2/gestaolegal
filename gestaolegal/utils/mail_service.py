import logging
from dataclasses import dataclass, field
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from functools import cache
from pathlib import Path

from flask_mail import Message
from jinja2 import Environment, FileSystemLoader, select_autoescape

from gestaolegal.config import Config

logger = logging.getLogger(__name__)

ASSUNTO_RECUPERACAO = "Recuperação de senha Gestão Legal"

_PASTA_TEMPLATES = Path(__file__).resolve().parent.parent / "templates" / "email"
_PASTA_IMAGENS = _PASTA_TEMPLATES / "img"

CID_CAPIVARA = "capivara@gestaolegal"


@dataclass(frozen=True)
class Instituicao:
    sigla: str
    nome: str
    url: str
    arquivo: str
    altura: int

    @property
    def cid(self) -> str:
        return f"{Path(self.arquivo).stem}@gestaolegal"


# Rodapé obrigatório de todo e-mail do sistema, no HTML e no texto. A ordem é
# a do rodapé do front (web/src/lib/components/app-footer.svelte).
INSTITUICOES = (
    Instituicao(
        "LabP²",
        "LabP² · Laboratório de Tecnologias Públicas para o Setor Público",
        "https://labp2.direito.ufmg.br/",
        "labp2.png",
        32,
    ),
    Instituicao(
        "FD/UFMG",
        "Faculdade de Direito da UFMG",
        "https://www.direito.ufmg.br/",
        "fdufmg.png",
        40,
    ),
    Instituicao(
        "UFMG",
        "Universidade Federal de Minas Gerais",
        "https://ufmg.br/",
        "ufmg.png",
        24,
    ),
)


@dataclass(frozen=True)
class Botao:
    texto: str
    url: str


@dataclass(frozen=True)
class ConteudoEmail:
    """O que muda de um e-mail para outro; o layout é sempre o mesmo.

    `paragrafos` e `nota` são texto puro (o HTML é escapado no template). O
    botão aparece no HTML como botão e no texto como "texto: url".
    """

    titulo: str
    paragrafos: list[str] = field(default_factory=list)
    botao: Botao | None = None
    nota: str | None = None


class _MensagemComImagens(Message):
    """Message do Flask-Mail com imagens inline em multipart/related.

    O Flask-Mail põe anexos num multipart/mixed, e alguns clientes (Apple
    Mail, Thunderbird) mostram as imagens como anexos soltos além de exibi-las
    no corpo. Aqui o HTML e as imagens ficam juntos em multipart/related.
    """

    def __init__(self, *args, imagens: dict[str, bytes], **kwargs):
        super().__init__(*args, **kwargs)
        self.imagens = imagens

    def _message(self):
        original = super()._message()
        if not self.html or not self.imagens:
            return original

        alternativa = original.get_payload()[0]
        raiz = MIMEMultipart("related")
        raiz.attach(alternativa)
        for cid, dados in self.imagens.items():
            imagem = MIMEImage(dados, "png")
            imagem.add_header("Content-ID", f"<{cid}>")
            imagem.add_header(
                "Content-Disposition", "inline", filename=cid.split("@")[0] + ".png"
            )
            raiz.attach(imagem)

        for chave, valor in original.items():
            if chave.lower() not in ("content-type", "mime-version"):
                raiz[chave] = valor
        return raiz


@cache
def _ambiente() -> Environment:
    return Environment(
        loader=FileSystemLoader(_PASTA_TEMPLATES),
        autoescape=select_autoescape(["html"]),
    )


@cache
def _imagem(arquivo: str) -> bytes:
    return (_PASTA_IMAGENS / arquivo).read_bytes()


def _rodape_texto() -> str:
    linhas = ["--", "Gestão Legal · Assistência Judiciária da Faculdade de Direito da UFMG"]
    linhas += [f"{inst.nome}: {inst.url}" for inst in INSTITUICOES]
    linhas.append("Mensagem automática. Não responda a este e-mail.")
    return "\n".join(linhas)


def renderizar_texto(conteudo: ConteudoEmail) -> str:
    partes = [*conteudo.paragrafos]
    if conteudo.botao:
        partes.append(f"{conteudo.botao.texto}:\n{conteudo.botao.url}")
    if conteudo.nota:
        partes.append(conteudo.nota)
    partes.append(_rodape_texto())
    return "\n\n".join(partes) + "\n"


def renderizar_html(assunto: str, conteudo: ConteudoEmail) -> str:
    return _ambiente().get_template("base.html").render(
        assunto=assunto,
        previa=conteudo.paragrafos[0] if conteudo.paragrafos else conteudo.titulo,
        titulo=conteudo.titulo,
        paragrafos=conteudo.paragrafos,
        botao=conteudo.botao,
        nota=conteudo.nota,
        cid_capivara=CID_CAPIVARA,
        instituicoes=INSTITUICOES,
    )


def _imagens_inline() -> dict[str, bytes]:
    imagens = {CID_CAPIVARA: _imagem("capivara.png")}
    for inst in INSTITUICOES:
        imagens[inst.cid] = _imagem(inst.arquivo)
    return imagens


def enviar_email(
    destinatario: str, assunto: str, conteudo: ConteudoEmail | str
) -> bool:
    """Entrega uma mensagem ao SMTP configurado, no layout padrão do sistema.

    Todo e-mail sai em HTML (capivara, rodapé com LabP², FD e UFMG) e em texto
    puro, com o mesmo conteúdo. Uma string vira parágrafos separados por linha
    em branco, com o assunto como título.

    Nunca levanta exceção: falha de envio vira log e `False`. Quem chama trata
    o envio como melhor esforço — indisponibilidade do servidor de e-mail não
    pode derrubar a requisição do usuário.
    """
    # Import local: o objeto é criado em gestaolegal/__init__.py, que importa
    # utils; importar no topo daria ciclo.
    from gestaolegal import mail

    if isinstance(conteudo, str):
        paragrafos = [p.strip() for p in conteudo.split("\n\n") if p.strip()]
        conteudo = ConteudoEmail(titulo=assunto, paragrafos=paragrafos)

    try:
        mensagem = _MensagemComImagens(
            subject=assunto,
            recipients=[destinatario],
            body=renderizar_texto(conteudo),
            html=renderizar_html(assunto, conteudo),
            sender=Config.MAIL_DEFAULT_SENDER,
            imagens=_imagens_inline(),
        )
        mail.send(mensagem)
    except Exception:
        logger.exception(f"Falha ao enviar e-mail para {destinatario}: {assunto}")
        return False

    logger.info(f"E-mail enviado para {destinatario}: {assunto}")
    return True


def enviar_link_recuperacao(destinatario: str, nome: str, url: str) -> bool:
    validade = Config.PASSWORD_RESET_TOKEN_TTL_MINUTES
    conteudo = ConteudoEmail(
        titulo="Redefinição de senha",
        paragrafos=[
            f"Olá, {nome}.",
            "Recebemos um pedido para redefinir a sua senha no Gestão Legal.",
            "Para escolher uma senha nova, acesse o link abaixo.",
        ],
        botao=Botao("Escolher nova senha", url),
        nota=(
            f"O link vale por {validade} minutos e pode ser usado uma única vez. "
            "Se não foi você que pediu, ignore esta mensagem: sua senha continua a mesma."
        ),
    )
    return enviar_email(destinatario, ASSUNTO_RECUPERACAO, conteudo)
