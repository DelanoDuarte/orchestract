"""add user locale preference

Revision ID: f2b8d3c4a1e7
Revises: e5a7c1d9f2b3
Create Date: 2026-08-03 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2b8d3c4a1e7'
down_revision: Union[str, Sequence[str], None] = 'e5a7c1d9f2b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the nullable `locale` column storing a user's preferred UI language
    (e.g. 'pt'). Null means 'not chosen' -> negotiate from the browser."""
    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('locale', sa.String(length=10), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('users') as batch:
        batch.drop_column('locale')
