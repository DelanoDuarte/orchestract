"""add document share links

Revision ID: a1c7e9b2f4d6
Revises: f2b8d3c4a1e7
Create Date: 2026-08-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c7e9b2f4d6'
down_revision: Union[str, Sequence[str], None] = 'f2b8d3c4a1e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add share_links (external, time-boxed, optionally password-protected
    review links for a contract's documents) and share_link_documents (the
    subset a DOCUMENTS-scoped link exposes)."""
    op.create_table(
        'share_links',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('contract_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('scope', sa.Enum('CONTRACT', 'DOCUMENTS', name='sharescope'), nullable=False),
        sa.Column('password_hash', sa.String(length=300), nullable=True),
        sa.Column('allow_download', sa.Boolean(), nullable=False),
        sa.Column('created_by', sa.String(length=200), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('last_accessed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['contract_id'], ['contracts.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_share_links_contract_id'), 'share_links', ['contract_id'], unique=False)
    op.create_index(op.f('ix_share_links_token'), 'share_links', ['token'], unique=True)

    op.create_table(
        'share_link_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('share_link_id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['share_link_id'], ['share_links.id']),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('share_link_id', 'document_id', name='uq_share_link_document'),
    )
    op.create_index(
        op.f('ix_share_link_documents_share_link_id'),
        'share_link_documents',
        ['share_link_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_share_link_documents_share_link_id'), table_name='share_link_documents')
    op.drop_table('share_link_documents')
    op.drop_index(op.f('ix_share_links_token'), table_name='share_links')
    op.drop_index(op.f('ix_share_links_contract_id'), table_name='share_links')
    op.drop_table('share_links')
    sa.Enum(name='sharescope').drop(op.get_bind(), checkfirst=True)
