"""Separate document currency from verification level.

Revision ID: 0002
Revises: 0001
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("evidence_status", sa.String(30),
                                          nullable=False, server_default="unverified"))
    op.execute("UPDATE documents SET evidence_status='official' WHERE domain IN ('worldofwarcraft.blizzard.com', 'news.blizzard.com')")
    op.execute("UPDATE documents SET evidence_status='theorycraft' WHERE lower(body) LIKE '%theorycraft%'")


def downgrade() -> None:
    op.drop_column("documents", "evidence_status")
