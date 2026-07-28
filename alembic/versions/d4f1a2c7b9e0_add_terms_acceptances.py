"""add terms acceptances

Revision ID: d4f1a2c7b9e0
Revises: c2e992f03ef4
Create Date: 2026-07-28 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4f1a2c7b9e0'
down_revision: Union[str, Sequence[str], None] = 'c2e992f03ef4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'terms_acceptances',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.String(length=40), nullable=False),
        sa.Column('accepted_at', sa.DateTime(), nullable=False),
        sa.Column('ip_address', sa.String(length=64), nullable=True),
        sa.Column('user_agent', sa.String(length=400), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_terms_acceptances_organization_id'), 'terms_acceptances', ['organization_id'], unique=False)
    op.create_index(op.f('ix_terms_acceptances_user_id'), 'terms_acceptances', ['user_id'], unique=False)
    op.create_index(op.f('ix_terms_acceptances_version'), 'terms_acceptances', ['version'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_terms_acceptances_version'), table_name='terms_acceptances')
    op.drop_index(op.f('ix_terms_acceptances_user_id'), table_name='terms_acceptances')
    op.drop_index(op.f('ix_terms_acceptances_organization_id'), table_name='terms_acceptances')
    op.drop_table('terms_acceptances')
