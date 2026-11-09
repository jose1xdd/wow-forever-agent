"""Initial relational schema and vector extension.

Revision ID: 0001
Revises:
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table("sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False, unique=True),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("trust", sa.String(40), nullable=False),
        sa.Column("refresh_hours", sa.Integer(), nullable=False),
        sa.Column("seeds", postgresql.JSONB(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()))
    op.create_index("ix_sources_domain", "sources", ["domain"])
    op.create_table("game_builds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.String(80), nullable=False, unique=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("notes", sa.Text()))
    op.create_table("player_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("label", sa.String(120), nullable=False, unique=True),
        sa.Column("preferences", postgresql.JSONB(), nullable=False))
    op.create_table("documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("game_build_id", sa.Integer(), sa.ForeignKey("game_builds.id")),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("category", sa.String(60), nullable=False),
        sa.Column("language", sa.String(12), nullable=False),
        sa.Column("class_name", sa.String(40)),
        sa.Column("specialization", sa.String(60)),
        sa.Column("activity", sa.String(60)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at_source", sa.DateTime(timezone=True)),
        sa.Column("extracted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.UniqueConstraint("canonical_url", "content_hash", name="uq_document_url_hash"))
    for col in ("source_id", "game_build_id", "class_name", "status"):
        op.create_index(f"ix_documents_{col}", "documents", [col])
    op.create_index("ix_documents_url_status", "documents", ["canonical_url", "status"])
    op.create_table("document_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_search", postgresql.TSVECTOR()),
        sa.Column("embedding", Vector(384)),
        sa.Column("embedding_model", sa.String(150)),
        sa.UniqueConstraint("document_id", "ordinal"))
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index("ix_chunks_text_search", "document_chunks", ["text_search"], postgresql_using="gin")
    op.execute("CREATE INDEX ix_chunks_embedding_hnsw ON document_chunks USING hnsw (embedding vector_cosine_ops)")
    op.create_table("game_changes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("from_build_id", sa.Integer(), sa.ForeignKey("game_builds.id")),
        sa.Column("to_build_id", sa.Integer(), sa.ForeignKey("game_builds.id"), nullable=False),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("entity_type", sa.String(40), nullable=False),
        sa.Column("entity_name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False))
    op.create_table("characters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("player_profiles.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("realm", sa.String(100), nullable=False),
        sa.Column("class_name", sa.String(40)),
        sa.Column("race", sa.String(60)),
        sa.Column("faction", sa.String(20)),
        sa.Column("level", sa.Integer()),
        sa.Column("specialization", sa.String(60)),
        sa.Column("professions", postgresql.JSONB(), nullable=False),
        sa.Column("equipment", postgresql.JSONB(), nullable=False),
        sa.Column("goals", postgresql.JSONB(), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("profile_id", "name", "realm", name="uq_character_identity"))
    op.create_table("player_memories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("player_profiles.id"), nullable=False),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id")),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade() -> None:
    for table in ("player_memories", "characters", "game_changes", "document_chunks", "documents", "player_profiles", "game_builds", "sources"):
        op.drop_table(table)
    # The vector extension may be shared by other schemas; do not drop it.
