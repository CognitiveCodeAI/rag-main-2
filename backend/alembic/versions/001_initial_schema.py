"""Initial schema for NPR RAG

Revision ID: 001
Revises: 
Create Date: 2026-01-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. documents (system of record)
    op.create_table(
        'documents',
        sa.Column('doc_id', sa.String(256), primary_key=True),
        sa.Column('version_id', sa.String(256), nullable=False),
        sa.Column('source_type', sa.String(64), nullable=False),
        sa.Column('source_uri', sa.Text(), nullable=False),
        sa.Column('mime_type', sa.String(128), nullable=True),
        sa.Column('checksum', sa.String(128), nullable=False),
        sa.Column('owner', sa.String(256), nullable=True),
        sa.Column('team', sa.String(256), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint('uq_documents_doc_version', 'documents', ['doc_id', 'version_id'])
    
    # 2. ingest_jobs (job tracking)
    op.create_table(
        'ingest_jobs',
        sa.Column('job_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('doc_id', sa.String(256), sa.ForeignKey('documents.doc_id'), nullable=True),
        sa.Column('status', sa.String(32), nullable=False, server_default='pending'),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_ingest_jobs_status', 'ingest_jobs', ['status'])
    op.create_index('ix_ingest_jobs_doc_id', 'ingest_jobs', ['doc_id'])
    
    # 3. document_ir (IR artifact refs)
    op.create_table(
        'document_ir',
        sa.Column('doc_id', sa.String(256), sa.ForeignKey('documents.doc_id'), primary_key=True),
        sa.Column('version_id', sa.String(256), primary_key=True),
        sa.Column('ir_uri', sa.Text(), nullable=False),
        sa.Column('parse_confidence', sa.Float(), nullable=True),
        sa.Column('ocr_used', sa.Boolean(), server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    # 4. chunks (metadata only, content in MinIO)
    op.create_table(
        'chunks',
        sa.Column('chunk_id', sa.String(256), primary_key=True),
        sa.Column('doc_id', sa.String(256), sa.ForeignKey('documents.doc_id'), nullable=False),
        sa.Column('version_id', sa.String(256), nullable=False),
        sa.Column('section_path', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('chunk_type', sa.String(32), nullable=False),
        sa.Column('start_offset', sa.Integer(), nullable=False),
        sa.Column('end_offset', sa.Integer(), nullable=False),
        sa.Column('chunk_metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_chunks_doc_id', 'chunks', ['doc_id'])
    op.create_index('ix_chunks_chunk_type', 'chunks', ['chunk_type'])
    
    # 5. traces (flight recorder refs)
    op.create_table(
        'traces',
        sa.Column('trace_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('request_id', sa.String(256), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('trace_uri', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_traces_request_id', 'traces', ['request_id'])
    op.create_index('ix_traces_status', 'traces', ['status'])
    
    # 6. golden_records (eval data)
    op.create_table(
        'golden_records',
        sa.Column('record_id', sa.String(256), primary_key=True),
        sa.Column('label', sa.String(32), nullable=False),
        sa.Column('payload', postgresql.JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_golden_records_label', 'golden_records', ['label'])


def downgrade() -> None:
    op.drop_table('golden_records')
    op.drop_table('traces')
    op.drop_table('chunks')
    op.drop_table('document_ir')
    op.drop_table('ingest_jobs')
    op.drop_table('documents')
