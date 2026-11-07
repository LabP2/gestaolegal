"""Entidades globais da plataforma: os NPJs (tenants) e quem os administra."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Tenant:
    id: int
    nome: str
    sigla: str
    slug: str
    instituicao: str | None
    ativo: bool
    criado_em: datetime
    id_criado_por: int | None = None


@dataclass
class PlataformaAdmin:
    id: int
    nome: str
    email: str
    senha: str  # hash bcrypt; nunca vai para a resposta da API
    ativo: bool
    criado_em: datetime
    ultimo_login_em: datetime | None = None
