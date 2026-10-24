"""add folders

Revision ID: 9b8de3a758aa
Revises: 6dbe42ac2cca
Create Date: 2026-10-24 14:18:16.814242

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9b8de3a758aa"
down_revision: str | Sequence[str] | None = "6dbe42ac2cca"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "folders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # Único sin distinguir mayúsculas (índice sobre una expresión).
    op.create_index("uq_folders_name_lower", "folders", [sa.text("lower(name)")], unique=True)
    op.add_column("documents", sa.Column("folder_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_documents_folder_id"), "documents", ["folder_id"], unique=False)
    op.create_foreign_key(
        "fk_documents_folder_id_folders",
        "documents",
        "folders",
        ["folder_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_documents_folder_id_folders", "documents", type_="foreignkey")
    op.drop_index(op.f("ix_documents_folder_id"), table_name="documents")
    op.drop_column("documents", "folder_id")
    op.drop_index("uq_folders_name_lower", table_name="folders")
    op.drop_table("folders")
