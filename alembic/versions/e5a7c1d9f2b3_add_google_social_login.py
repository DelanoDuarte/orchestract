"""add google social login

Revision ID: e5a7c1d9f2b3
Revises: d4f1a2c7b9e0
Create Date: 2026-07-31 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5a7c1d9f2b3'
down_revision: Union[str, Sequence[str], None] = 'd4f1a2c7b9e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add google_sub for social login and make password_hash nullable
    (social-only accounts have no password). Batch mode so SQLite (dev) can
    alter the column too."""
    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('google_sub', sa.String(length=255), nullable=True))
        batch.alter_column('password_hash', existing_type=sa.String(length=300), nullable=True)
    op.create_index(op.f('ix_users_google_sub'), 'users', ['google_sub'], unique=True)


def downgrade() -> None:
    """Reverse: drop google_sub and restore password_hash NOT NULL. Any
    social-only rows must be removed first for the NOT NULL restore to hold."""
    op.drop_index(op.f('ix_users_google_sub'), table_name='users')
    with op.batch_alter_table('users') as batch:
        batch.alter_column('password_hash', existing_type=sa.String(length=300), nullable=False)
        batch.drop_column('google_sub')
