"""split contract from document

Revision ID: b3be2d850420
Revises: fdc9e4031d34
Create Date: 2026-07-27 00:22:11.870431

SQLite can't ALTER an existing table's columns/constraints in place, and this
reshapes `documents` (drops organization_id/title/description/document_type,
adds contract_id/name/summary/summary_generated_at) and `workflow_instances`
(document_id -> contract_id) -- both cross-cutting enough that a hand-written
drop/recreate is clearer than a chain of batch_alter_table ops. This is a
pre-production app (see app/infrastructure/seed.py) so there is no production
data to preserve across the reshape.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3be2d850420'
down_revision: Union[str, Sequence[str], None] = 'fdc9e4031d34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'contracts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('contract_type', sa.String(length=100), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('summary_generated_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_contracts_organization_id'), 'contracts', ['organization_id'], unique=False)

    # Children first: FKs point at the tables being dropped/recreated below.
    op.drop_table('document_versions')
    op.drop_table('workflow_history_entries')
    op.drop_table('documents')
    op.drop_table('workflow_instances')

    op.create_table(
        'documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('contract_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=300), nullable=False),
        sa.Column('current_version_no', sa.Integer(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('summary_generated_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['contract_id'], ['contracts.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_documents_contract_id'), 'documents', ['contract_id'], unique=False)

    op.create_table(
        'document_versions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('version_no', sa.Integer(), nullable=False),
        sa.Column('storage_connection_id', sa.Integer(), nullable=False),
        sa.Column('storage_key', sa.String(length=500), nullable=False),
        sa.Column('original_filename', sa.String(length=300), nullable=False),
        sa.Column('content_type', sa.String(length=150), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column(
            'source_provider',
            sa.Enum('LOCAL', 'S3', 'MINIO', 'GCS', 'GOOGLE_DRIVE', 'ONEDRIVE', name='storageprovider'),
            nullable=True,
        ),
        sa.Column('source_external_id', sa.String(length=300), nullable=True),
        sa.Column('uploaded_by', sa.String(length=200), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id']),
        sa.ForeignKeyConstraint(['storage_connection_id'], ['storage_connections.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('document_id', 'version_no', name='uq_doc_version'),
    )
    op.create_index(op.f('ix_document_versions_document_id'), 'document_versions', ['document_id'], unique=False)

    op.create_table(
        'workflow_instances',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('contract_id', sa.Integer(), nullable=False),
        sa.Column('workflow_definition_id', sa.Integer(), nullable=False),
        sa.Column('current_step_key', sa.String(length=80), nullable=False),
        sa.Column('status', sa.Enum('ACTIVE', 'COMPLETED', name='instancestatus'), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['contract_id'], ['contracts.id']),
        sa.ForeignKeyConstraint(['workflow_definition_id'], ['workflow_definitions.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_workflow_instances_contract_id'), 'workflow_instances', ['contract_id'], unique=False)
    op.create_index(
        op.f('ix_workflow_instances_workflow_definition_id'),
        'workflow_instances',
        ['workflow_definition_id'],
        unique=False,
    )

    op.create_table(
        'workflow_history_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workflow_instance_id', sa.Integer(), nullable=False),
        sa.Column('from_step_key', sa.String(length=80), nullable=True),
        sa.Column('to_step_key', sa.String(length=80), nullable=False),
        sa.Column('action_name', sa.String(length=80), nullable=True),
        sa.Column('actor', sa.String(length=200), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['workflow_instance_id'], ['workflow_instances.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_workflow_history_entries_workflow_instance_id'),
        'workflow_history_entries',
        ['workflow_instance_id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema. Drops the reshaped tables -- as with upgrade(), this
    is a destructive reset, not a data-preserving rollback."""
    op.drop_table('workflow_history_entries')
    op.drop_table('workflow_instances')
    op.drop_table('document_versions')
    op.drop_table('documents')
    op.drop_table('contracts')

    op.create_table(
        'documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('document_type', sa.String(length=100), nullable=False),
        sa.Column('current_version_no', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_documents_organization_id'), 'documents', ['organization_id'], unique=False)

    op.create_table(
        'document_versions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('version_no', sa.Integer(), nullable=False),
        sa.Column('storage_connection_id', sa.Integer(), nullable=False),
        sa.Column('storage_key', sa.String(length=500), nullable=False),
        sa.Column('original_filename', sa.String(length=300), nullable=False),
        sa.Column('content_type', sa.String(length=150), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column(
            'source_provider',
            sa.Enum('LOCAL', 'S3', 'MINIO', 'GCS', 'GOOGLE_DRIVE', 'ONEDRIVE', name='storageprovider'),
            nullable=True,
        ),
        sa.Column('source_external_id', sa.String(length=300), nullable=True),
        sa.Column('uploaded_by', sa.String(length=200), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id']),
        sa.ForeignKeyConstraint(['storage_connection_id'], ['storage_connections.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('document_id', 'version_no', name='uq_doc_version'),
    )
    op.create_index(op.f('ix_document_versions_document_id'), 'document_versions', ['document_id'], unique=False)

    op.create_table(
        'workflow_instances',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('workflow_definition_id', sa.Integer(), nullable=False),
        sa.Column('current_step_key', sa.String(length=80), nullable=False),
        sa.Column('status', sa.Enum('ACTIVE', 'COMPLETED', name='instancestatus'), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id']),
        sa.ForeignKeyConstraint(['workflow_definition_id'], ['workflow_definitions.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_workflow_instances_document_id'), 'workflow_instances', ['document_id'], unique=False)
    op.create_index(
        op.f('ix_workflow_instances_workflow_definition_id'),
        'workflow_instances',
        ['workflow_definition_id'],
        unique=False,
    )

    op.create_table(
        'workflow_history_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workflow_instance_id', sa.Integer(), nullable=False),
        sa.Column('from_step_key', sa.String(length=80), nullable=True),
        sa.Column('to_step_key', sa.String(length=80), nullable=False),
        sa.Column('action_name', sa.String(length=80), nullable=True),
        sa.Column('actor', sa.String(length=200), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['workflow_instance_id'], ['workflow_instances.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_workflow_history_entries_workflow_instance_id'),
        'workflow_history_entries',
        ['workflow_instance_id'],
        unique=False,
    )
