"""unaccent full text search

Revision ID: 209b3d66294e
Revises: ccf1d1e9ef0d
Create Date: 2026-10-24 17:30:25.073259

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "209b3d66294e"
down_revision: str | Sequence[str] | None = "ccf1d1e9ef0d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# unaccent() no es IMMUTABLE (depende de un diccionario configurable), así que PostgreSQL no
# deja usarlo en una columna calculada. El envoltorio fija el diccionario y se declara inmutable.
CREATE_FUNCTION = """
CREATE OR REPLACE FUNCTION immutable_unaccent(text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
AS $$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $$
"""


def _replace_search_vector(expression: str) -> None:
    op.drop_index("ix_document_chunks_search_vector", table_name="document_chunks")
    op.drop_column("document_chunks", "search_vector")
    op.add_column(
        "document_chunks",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(expression, persisted=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_document_chunks_search_vector",
        "document_chunks",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )


def upgrade() -> None:
    """Búsqueda por palabras sin tildes: «pidio» encuentra «pidió» y al revés."""
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute(CREATE_FUNCTION)
    # Recalcula la columna para todos los fragmentos existentes (no hace falta reprocesar).
    _replace_search_vector("to_tsvector('simple', immutable_unaccent(text))")


def downgrade() -> None:
    """Vuelve a la búsqueda que distingue tildes."""
    _replace_search_vector("to_tsvector('simple', text)")
    op.execute("DROP FUNCTION IF EXISTS immutable_unaccent(text)")
    # La extensión se deja instalada: otras bases o funciones podrían usarla.
