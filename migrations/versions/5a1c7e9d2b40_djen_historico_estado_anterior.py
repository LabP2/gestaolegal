"""Estado anterior da avaliação no histórico, para reverter sem inferir a origem."""
from alembic import op
import sqlalchemy as sa

revision = '5a1c7e9d2b40'
down_revision = '49b08df53ce1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('djen_contexto_historico', sa.Column('origem_anterior', sa.String(30)))
    op.add_column('djen_contexto_historico', sa.Column('id_rotulado_por_anterior', sa.Integer()))
    op.add_column('djen_contexto_historico', sa.Column('rotulado_em_anterior', sa.DateTime()))


def downgrade():
    op.drop_column('djen_contexto_historico', 'rotulado_em_anterior')
    op.drop_column('djen_contexto_historico', 'id_rotulado_por_anterior')
    op.drop_column('djen_contexto_historico', 'origem_anterior')
