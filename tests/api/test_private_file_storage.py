"""Cofre dos anexos privados: gravação, leitura, remoção e recusas (#190)."""

import io
import os

import pytest
from werkzeug.datastructures import FileStorage

from gestaolegal.services import private_file_storage as pfs
from gestaolegal.services.private_file_storage import PrivateFileError
from gestaolegal.utils.request_context import contexto_tenant

from .conftest import TENANT_DAJ, TENANT_OUTRO


@pytest.fixture
def raiz(app, tmp_path, monkeypatch):
    """Pasta do tenant 1 numa raiz privada isolada por teste.

    A raiz é `tmp_path`; o storage grava em `<raiz>/<tenant_id>/<categoria>`,
    então o que os testes enxergam como "raiz" é `tmp_path / "1"`.
    """
    monkeypatch.setitem(app.config, "PRIVATE_FILES_ROOT", str(tmp_path))
    with app.app_context(), contexto_tenant(TENANT_DAJ):
        yield tmp_path / str(TENANT_DAJ)


def _upload(nome: str, conteudo: bytes = b"conteudo") -> FileStorage:
    return FileStorage(stream=io.BytesIO(conteudo), filename=nome)


# ------------------------------------------------------------------ feliz


def test_grava_le_e_remove(raiz):
    ref = pfs.save("casos", _upload("parecer.pdf", b"%PDF-1.4"))

    caminho = pfs.resolve("casos", ref)
    assert os.path.isfile(caminho)
    assert open(caminho, "rb").read() == b"%PDF-1.4"
    assert caminho.startswith(str(raiz))
    assert ref.endswith("_parecer.pdf")
    assert os.path.dirname(ref) == ""

    pfs.remove("casos", ref)
    assert not os.path.exists(caminho)


def test_remover_ausente_nao_falha(raiz):
    ref = pfs.save("arquivos", _upload("nota.txt"))
    pfs.remove("arquivos", ref)
    pfs.remove("arquivos", ref)


def test_nome_repetido_gera_referencias_distintas(raiz):
    primeira = pfs.save("eventos", _upload("ata.pdf", b"um"))
    segunda = pfs.save("eventos", _upload("ata.pdf", b"dois"))

    assert primeira != segunda
    assert open(pfs.resolve("eventos", primeira), "rb").read() == b"um"
    assert open(pfs.resolve("eventos", segunda), "rb").read() == b"dois"


def test_nome_longo_cabe_no_limite_da_coluna(raiz):
    ref = pfs.save("casos", _upload("a" * 400 + ".pdf"))

    assert len(ref) <= pfs.NAME_MAX <= pfs.REF_MAX
    assert ref.endswith(".pdf")
    assert os.path.isfile(pfs.resolve("casos", ref))


def test_caracteres_especiais_sao_higienizados(raiz):
    ref = pfs.save("casos", _upload("relatório final (2).pdf"))

    assert "/" not in ref and " " not in ref
    assert os.path.isfile(pfs.resolve("casos", ref))


def test_categoria_criada_sob_demanda(raiz):
    pfs.save("casos", _upload("x.txt"))
    assert (raiz / "casos").is_dir()


def test_cabecalhos_de_download():
    assert pfs.DOWNLOAD_HEADERS["Content-Disposition"] == "attachment"
    assert pfs.DOWNLOAD_HEADERS["Cache-Control"] == "private, no-store"


# ------------------------------------------------------------------ recusas


def test_categoria_desconhecida(raiz):
    with pytest.raises(PrivateFileError, match="Categoria"):
        pfs.save("outra", _upload("x.txt"))
    with pytest.raises(PrivateFileError, match="Categoria"):
        pfs.resolve("outra", "x.txt")


@pytest.mark.parametrize("ref", ["", "   ", None])
def test_referencia_vazia(raiz, ref):
    with pytest.raises(PrivateFileError, match="vazia"):
        pfs.resolve("casos", ref)


def test_referencia_absoluta(raiz):
    with pytest.raises(PrivateFileError, match="absoluto"):
        pfs.resolve("casos", "/etc/passwd")


@pytest.mark.parametrize("ref", ["../segredo", "sub/../../segredo", "..", "a/../../b"])
def test_referencia_com_subida_de_diretorio(raiz, ref):
    with pytest.raises(PrivateFileError):
        pfs.resolve("casos", ref)


def test_referencia_maior_que_o_limite(raiz):
    with pytest.raises(PrivateFileError, match="excede"):
        pfs.resolve("casos", "a" * (pfs.REF_MAX + 1))


def test_symlink_que_escapa_da_raiz(raiz):
    fora = raiz.parent / "fora"
    fora.mkdir()
    (fora / "segredo.txt").write_text("sigiloso")
    categoria = raiz / "casos"
    categoria.mkdir(parents=True)
    os.symlink(str(fora / "segredo.txt"), str(categoria / "atalho.txt"))

    with pytest.raises(PrivateFileError, match="fora da raiz"):
        pfs.resolve("casos", "atalho.txt")
    with pytest.raises(PrivateFileError, match="fora da raiz"):
        pfs.remove("casos", "atalho.txt")


def test_falha_de_gravacao_nao_deixa_temporario(raiz, monkeypatch):
    def explode(*args, **kwargs):
        raise OSError("disco cheio")

    monkeypatch.setattr(FileStorage, "save", explode)

    with pytest.raises(OSError):
        pfs.save("casos", _upload("x.txt"))

    assert os.listdir(raiz / "casos") == []


def test_nao_sobrescreve_arquivo_existente(raiz, monkeypatch):
    ref = pfs.save("casos", _upload("x.txt", b"original"))
    monkeypatch.setattr(pfs, "gerar_ref", lambda _nome: ref)

    with pytest.raises(FileExistsError):
        pfs.save("casos", _upload("x.txt", b"invasor"))

    assert open(pfs.resolve("casos", ref), "rb").read() == b"original"
    assert [n for n in os.listdir(raiz / "casos") if n.startswith(".tmp_")] == []


def test_raiz_nao_configurada(app, monkeypatch):
    monkeypatch.setitem(app.config, "PRIVATE_FILES_ROOT", "")
    with app.app_context():
        with pytest.raises(PrivateFileError, match="não configurada"):
            pfs.resolve("casos", "x.txt")


# ------------------------------------------------------------------ tenant


def test_grava_na_pasta_do_tenant_ativo(raiz):
    ref = pfs.save("casos", _upload("x.txt"))
    assert (raiz / "casos" / ref).is_file()
    assert raiz.name == str(TENANT_DAJ)


def test_sem_tenant_nao_le_nem_grava(app, tmp_path, monkeypatch):
    monkeypatch.setitem(app.config, "PRIVATE_FILES_ROOT", str(tmp_path))
    with app.app_context():
        with pytest.raises(RuntimeError, match="tenant"):
            pfs.save("casos", _upload("x.txt"))
        with pytest.raises(RuntimeError, match="tenant"):
            pfs.resolve("casos", "x.txt")
    assert list(tmp_path.iterdir()) == []


def test_anexo_de_outro_tenant_nao_e_alcancado(app, tmp_path, monkeypatch):
    monkeypatch.setitem(app.config, "PRIVATE_FILES_ROOT", str(tmp_path))
    with app.app_context():
        with contexto_tenant(TENANT_OUTRO):
            ref = pfs.save("casos", _upload("segredo.pdf", b"do outro NPJ"))
            assert pfs.exists("casos", ref)

        with contexto_tenant(TENANT_DAJ):
            # A mesma referência, no tenant 1, aponta para a pasta do tenant 1.
            assert not pfs.exists("casos", ref)
            assert pfs.resolve("casos", ref).startswith(str(tmp_path / "1") + os.sep)
            # E não há como subir até a pasta do outro.
            with pytest.raises(PrivateFileError):
                pfs.resolve("casos", f"../../{TENANT_OUTRO}/casos/{ref}")
            pfs.remove("casos", ref)

        with contexto_tenant(TENANT_OUTRO):
            assert pfs.exists("casos", ref)


def test_symlink_para_a_pasta_de_outro_tenant_e_recusado(app, tmp_path, monkeypatch):
    monkeypatch.setitem(app.config, "PRIVATE_FILES_ROOT", str(tmp_path))
    with app.app_context():
        with contexto_tenant(TENANT_OUTRO):
            ref = pfs.save("casos", _upload("segredo.pdf"))
        with contexto_tenant(TENANT_DAJ):
            categoria = tmp_path / "1" / "casos"
            categoria.mkdir(parents=True)
            os.symlink(str(tmp_path / str(TENANT_OUTRO) / "casos" / ref), str(categoria / "atalho.pdf"))
            with pytest.raises(PrivateFileError, match="fora da raiz"):
                pfs.resolve("casos", "atalho.pdf")


def test_layout_antigo_sem_tenant_nao_e_lido(raiz):
    # Sem fallback: um anexo deixado em `<raiz>/<categoria>` (antes do
    # scripts/mover_arquivos_tenant.py) não é encontrado.
    antigo = raiz.parent / "casos"
    antigo.mkdir()
    (antigo / "legado.pdf").write_bytes(b"x")
    assert not pfs.exists("casos", "legado.pdf")
