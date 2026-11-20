"""Estado persistente do treino; worker separado e inferência em lotes."""

from alembic import op
import sqlalchemy as sa

revision = "38a97ce42bd0"
down_revision = "27f86bd31ac9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "djen_contextos",
        sa.Column(
            "treino_status", sa.String(20), nullable=False, server_default="ocioso"
        ),
    )
    for nome, tipo in [
        ("treino_token", sa.String(36)),
        ("treino_erro", sa.String(500)),
        ("treino_solicitado_em", sa.DateTime()),
        ("treino_iniciado_em", sa.DateTime()),
        ("treino_finalizado_em", sa.DateTime()),
    ]:
        op.add_column("djen_contextos", sa.Column(nome, tipo))


def downgrade():
    for nome in (
        "treino_finalizado_em",
        "treino_iniciado_em",
        "treino_solicitado_em",
        "treino_erro",
        "treino_token",
        "treino_status",
    ):
        op.drop_column("djen_contextos", nome)
