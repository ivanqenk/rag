"""add embeddings and full text search to chunks

Revision ID: 1f96c51a7247
Revises: 97519583831a
Create Date: 2026-10-23 12:54:22.280528

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "1f96c51a7247"
down_revision: str | Sequence[str] | None = "97519583831a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # La imagen pgvector/pgvector trae la extensión instalada; aquí se activa en esta base.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # 1536 = dimensión de text-embedding-3-small. Nulas para fragmentos anteriores a esta
    # migración: no tienen embedding hasta que se reprocesen.
    op.add_column("document_chunks", sa.Column("embedding", Vector(1536), nullable=True))
    op.add_column(
        "document_chunks", sa.Column("embedding_model", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "document_chunks",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple', text)", persisted=True),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_document_chunks_search_vector",
        "document_chunks",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_document_chunks_search_vector", table_name="document_chunks", postgresql_using="gin"
    )
    op.drop_column("document_chunks", "search_vector")
    op.drop_column("document_chunks", "embedding_model")
    op.drop_column("document_chunks", "embedding")
    op.execute("DROP EXTENSION IF EXISTS vector")
