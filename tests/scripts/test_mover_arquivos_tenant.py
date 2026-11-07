"""Movimentação dos anexos do layout antigo para a pasta do tenant (PR 8)."""

import os

import pytest

from scripts.mover_arquivos_tenant import main, mover


@pytest.fixture
def raiz(tmp_path):
    """Layout antigo: `<raiz>/<categoria>/<ref>`, com subpasta e temporário."""
    (tmp_path / "casos").mkdir()
    (tmp_path / "casos" / "abc_parecer.pdf").write_bytes(b"parecer")
    (tmp_path / "eventos" / "sub").mkdir(parents=True)
    (tmp_path / "eventos" / "sub" / "ata.pdf").write_bytes(b"ata")
    (tmp_path / "arquivos").mkdir()
    (tmp_path / "arquivos" / "regimento.docx").write_bytes(b"regimento")
    return tmp_path


def _conteudo(caminho):
    return caminho.read_bytes()


def test_move_tudo_para_a_pasta_do_tenant_1(raiz):
    relatorio = mover(str(raiz))

    assert sorted(relatorio.movidos) == [
        "arquivos/regimento.docx",
        "casos/abc_parecer.pdf",
        "eventos/sub/ata.pdf",
    ]
    assert relatorio.falhas == 0
    assert _conteudo(raiz / "1" / "casos" / "abc_parecer.pdf") == b"parecer"
    assert _conteudo(raiz / "1" / "eventos" / "sub" / "ata.pdf") == b"ata"
    assert _conteudo(raiz / "1" / "arquivos" / "regimento.docx") == b"regimento"
    # O layout antigo some por inteiro.
    assert sorted(os.listdir(raiz)) == ["1"]


def test_e_idempotente(raiz):
    mover(str(raiz))
    antes = sorted(str(p.relative_to(raiz)) for p in raiz.rglob("*"))

    segunda = mover(str(raiz))

    assert segunda.movidos == [] and segunda.falhas == 0
    assert sorted(str(p.relative_to(raiz)) for p in raiz.rglob("*")) == antes


def test_dry_run_nao_move_nada(raiz):
    antes = sorted(str(p.relative_to(raiz)) for p in raiz.rglob("*"))

    relatorio = mover(str(raiz), dry_run=True)

    assert len(relatorio.movidos) == 3
    assert sorted(str(p.relative_to(raiz)) for p in raiz.rglob("*")) == antes
    assert not (raiz / "1").exists()


def test_conflito_nao_sobrescreve_e_falha(raiz):
    (raiz / "1" / "casos").mkdir(parents=True)
    (raiz / "1" / "casos" / "abc_parecer.pdf").write_bytes(b"ja estava")

    relatorio = mover(str(raiz))

    assert relatorio.conflitos == ["casos/abc_parecer.pdf"]
    assert relatorio.falhas == 1
    assert _conteudo(raiz / "1" / "casos" / "abc_parecer.pdf") == b"ja estava"
    # O original fica no lugar antigo, para alguém decidir.
    assert _conteudo(raiz / "casos" / "abc_parecer.pdf") == b"parecer"
    # O resto foi movido mesmo assim.
    assert (raiz / "1" / "arquivos" / "regimento.docx").is_file()


def test_symlink_nao_e_movido(raiz, tmp_path_factory):
    fora = tmp_path_factory.mktemp("fora") / "segredo.txt"
    fora.write_text("sigiloso")
    os.symlink(str(fora), str(raiz / "casos" / "atalho.txt"))

    relatorio = mover(str(raiz))

    assert relatorio.ignorados == ["casos/atalho.txt"]
    assert os.path.islink(raiz / "casos" / "atalho.txt")
    assert not os.path.lexists(raiz / "1" / "casos" / "atalho.txt")


def test_nao_mexe_na_pasta_de_outro_tenant(raiz):
    (raiz / "2" / "casos").mkdir(parents=True)
    (raiz / "2" / "casos" / "do_outro.pdf").write_bytes(b"outro")

    mover(str(raiz))

    assert _conteudo(raiz / "2" / "casos" / "do_outro.pdf") == b"outro"
    assert not (raiz / "1" / "casos" / "do_outro.pdf").exists()


def test_cli_devolve_o_numero_de_falhas(raiz, capsys):
    (raiz / "1" / "casos").mkdir(parents=True)
    (raiz / "1" / "casos" / "abc_parecer.pdf").write_bytes(b"ja estava")

    assert main(["--raiz-privada", str(raiz), "--check"]) == 1
    assert (raiz / "casos" / "abc_parecer.pdf").exists()
    assert main(["--raiz-privada", str(raiz)]) == 1
    saida = capsys.readouterr().out
    assert "conflitos" in saida and "casos/abc_parecer.pdf" in saida


def test_raiz_inexistente_aborta(tmp_path):
    with pytest.raises(SystemExit):
        mover(str(tmp_path / "nao-existe"))
