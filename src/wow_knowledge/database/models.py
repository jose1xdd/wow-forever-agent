from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    domain: Mapped[str] = mapped_column(String(255), index=True)
    trust: Mapped[str] = mapped_column(String(40))
    refresh_hours: Mapped[int] = mapped_column(Integer, default=72)
    seeds: Mapped[list[str]] = mapped_column(JSONB, default=list)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class GameBuild(Base):
    __tablename__ = "game_builds"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(String(80), unique=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    notes: Mapped[str | None] = mapped_column(Text)


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("canonical_url", "content_hash", name="uq_document_url_hash"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    game_build_id: Mapped[int | None] = mapped_column(ForeignKey("game_builds.id"), index=True)
    canonical_url: Mapped[str] = mapped_column(Text)
    domain: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(60), default="general")
    language: Mapped[str] = mapped_column(String(12), default="en")
    class_name: Mapped[str | None] = mapped_column(String(40), index=True)
    specialization: Mapped[str | None] = mapped_column(String(60))
    activity: Mapped[str | None] = mapped_column(String(60))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at_source: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    content_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="current", index=True)
    evidence_status: Mapped[str] = mapped_column(String(30), default="unverified")
    body: Mapped[str] = mapped_column(Text)
    source: Mapped[Source] = relationship()
    game_build: Mapped[GameBuild | None] = relationship()
    chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "ordinal"),
        Index("ix_chunks_text_search", "text_search", postgresql_using="gin"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    text_search: Mapped[Any] = mapped_column(TSVECTOR)
    embedding: Mapped[Any | None] = mapped_column(Vector(384))
    embedding_model: Mapped[str | None] = mapped_column(String(150))
    document: Mapped[Document] = relationship(back_populates="chunks")


class GameChange(Base):
    __tablename__ = "game_changes"
    id: Mapped[int] = mapped_column(primary_key=True)
    from_build_id: Mapped[int | None] = mapped_column(ForeignKey("game_builds.id"))
    to_build_id: Mapped[int] = mapped_column(ForeignKey("game_builds.id"))
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="unverified")


class PlayerProfile(Base):
    __tablename__ = "player_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(120), unique=True, default="default")
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class Character(Base):
    __tablename__ = "characters"
    __table_args__ = (UniqueConstraint("profile_id", "name", "realm", name="uq_character_identity"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("player_profiles.id"))
    name: Mapped[str] = mapped_column(String(100))
    realm: Mapped[str] = mapped_column(String(100), default="")
    class_name: Mapped[str | None] = mapped_column(String(40))
    race: Mapped[str | None] = mapped_column(String(60))
    faction: Mapped[str | None] = mapped_column(String(20))
    level: Mapped[int | None] = mapped_column(Integer)
    specialization: Mapped[str | None] = mapped_column(String(60))
    professions: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    equipment: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    goals: Mapped[list[str]] = mapped_column(JSONB, default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PlayerMemory(Base):
    __tablename__ = "player_memories"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("player_profiles.id"))
    character_id: Mapped[int | None] = mapped_column(ForeignKey("characters.id"))
    kind: Mapped[str] = mapped_column(String(30))
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
