from dataclasses import fields

import pytest

from gestaolegal.models.user import UserInfo
from gestaolegal.utils.request_context import (
    RequestContext,
    contexto_tenant,
    sem_tenant,
)


def _user_info() -> UserInfo:
    # UserInfo tem muitos campos obrigatorios e nenhum deles importa aqui:
    # o contexto so guarda e devolve a instancia.
    return UserInfo(**{campo.name: None for campo in fields(UserInfo)})


@pytest.fixture(autouse=True)
def limpar_contexto():
    RequestContext.clear()
    yield
    RequestContext.clear()


def test_unidade_ativa_ausente_levanta_runtime_error():
    with pytest.raises(RuntimeError):
        RequestContext.get_unidade_ativa()


def test_set_e_get_unidade_ativa():
    RequestContext.set_unidade_ativa(2)
    assert RequestContext.get_unidade_ativa() == 2


def test_clear_zera_usuario_e_unidade():
    RequestContext.set_current_user(_user_info())
    RequestContext.set_unidade_ativa(1)

    RequestContext.clear()

    with pytest.raises(RuntimeError):
        RequestContext.get_current_user()
    with pytest.raises(RuntimeError):
        RequestContext.get_unidade_ativa()


# --- Tenant -------------------------------------------------------------------


def test_tenant_ausente_levanta_runtime_error():
    with pytest.raises(RuntimeError):
        RequestContext.get_tenant()
    assert RequestContext.get_tenant_ou_none() is None


def test_set_e_get_tenant():
    RequestContext.set_tenant(3)
    assert RequestContext.get_tenant() == 3


@pytest.mark.parametrize("invalido", [0, -1, None, "1", 1.0, True])
def test_set_tenant_recusa_valor_invalido(invalido):
    with pytest.raises(ValueError):
        RequestContext.set_tenant(invalido)
    assert RequestContext.get_tenant_ou_none() is None


def test_clear_zera_tenant():
    RequestContext.set_tenant(1)
    RequestContext.clear()
    with pytest.raises(RuntimeError):
        RequestContext.get_tenant()


def test_contexto_tenant_define_e_restaura():
    with contexto_tenant(2) as tenant_id:
        assert tenant_id == 2
        assert RequestContext.get_tenant() == 2
    assert RequestContext.get_tenant_ou_none() is None


def test_contexto_tenant_restaura_mesmo_com_excecao():
    with pytest.raises(ZeroDivisionError), contexto_tenant(2):
        1 / 0
    assert RequestContext.get_tenant_ou_none() is None


def test_contexto_tenant_aceita_o_mesmo_tenant_e_recusa_outro():
    RequestContext.set_tenant(1)
    with contexto_tenant(1):
        assert RequestContext.get_tenant() == 1
    with pytest.raises(RuntimeError, match="dentro do tenant 1"), contexto_tenant(2):
        pass
    assert RequestContext.get_tenant() == 1


def test_contexto_tenant_recusa_valor_invalido():
    with pytest.raises(ValueError), contexto_tenant(0):
        pass


def test_sem_tenant_esconde_o_tenant_e_restaura():
    RequestContext.set_tenant(1)
    with sem_tenant("teste"):
        assert RequestContext.get_tenant_ou_none() is None
        assert RequestContext.motivo_sem_tenant() == "teste"
        with pytest.raises(RuntimeError):
            RequestContext.get_tenant()
    assert RequestContext.get_tenant() == 1
    assert RequestContext.motivo_sem_tenant() is None


def test_sem_tenant_exige_motivo():
    for motivo in ("", "   ", None):
        with pytest.raises(ValueError), sem_tenant(motivo):
            pass
    assert RequestContext.motivo_sem_tenant() is None


def test_sem_tenant_registra_o_motivo(caplog):
    with caplog.at_level("INFO"), sem_tenant("login por e-mail"):
        pass
    assert "login por e-mail" in caplog.text


def test_tenant_nao_entra_dentro_de_sem_tenant():
    with sem_tenant("teste"):
        with pytest.raises(RuntimeError), contexto_tenant(1):
            pass
        with pytest.raises(RuntimeError):
            RequestContext.set_tenant(1)
        assert RequestContext.get_tenant_ou_none() is None
