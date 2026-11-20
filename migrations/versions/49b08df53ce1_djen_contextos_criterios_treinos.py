"""Critérios versionados, associações preservadas e histórico de treinamentos."""
from alembic import op
import sqlalchemy as sa

revision = '49b08df53ce1'
down_revision = '38a97ce42bd0'
branch_labels = None
depends_on = None


def upgrade():
    for coluna in [
        sa.Column('descricao', sa.Text()), sa.Column('criterios', sa.JSON()),
        sa.Column('versao', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('avaliacoes_versao', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('revisoes', sa.JSON()),
    ]:
        op.add_column('djen_contextos', coluna)
    op.add_column('djen_publicacao_contextos', sa.Column('ativo', sa.Boolean(), nullable=False, server_default='1'))
    op.create_table(
        'djen_treinos',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('contexto_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(36), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('etapa', sa.String(80), nullable=False),
        sa.Column('etapas_concluidas', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('solicitado_em', sa.DateTime(), nullable=False),
        sa.Column('iniciado_em', sa.DateTime()), sa.Column('finalizado_em', sa.DateTime()),
        sa.Column('contexto_snapshot', sa.JSON(), nullable=False),
        sa.Column('logs', sa.JSON(), nullable=False), sa.Column('metricas', sa.JSON()),
        sa.Column('modelo_id', sa.Integer()), sa.Column('erro', sa.String(500)),
        sa.UniqueConstraint('tenant_id', 'id', name='uq_djen_treinos_tenant_id_id'),
        sa.UniqueConstraint('tenant_id', 'token', name='uq_djen_treino_token'),
        sa.ForeignKeyConstraint(['tenant_id', 'contexto_id'], ['djen_contextos.tenant_id', 'djen_contextos.id'], name='fkt_djen_treinos_contexto_id'),
        sa.ForeignKeyConstraint(['tenant_id', 'modelo_id'], ['djen_modelos.tenant_id', 'djen_modelos.id'], name='fkt_djen_treinos_modelo_id'),
    )
    op.create_index('ix_djen_treino_contexto', 'djen_treinos', ['tenant_id', 'contexto_id', 'id'])
    op.create_index('ix_djen_treinos_tenant_id', 'djen_treinos', ['tenant_id'])


def downgrade():
    op.drop_table('djen_treinos')
    op.drop_column('djen_publicacao_contextos', 'ativo')
    for nome in ['revisoes', 'avaliacoes_versao', 'versao', 'criterios', 'descricao']:
        op.drop_column('djen_contextos', nome)
