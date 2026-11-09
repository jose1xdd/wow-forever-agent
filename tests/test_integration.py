"""Requires running Docker and `alembic upgrade head`. No web access needed."""

import os
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from wow_knowledge.database import SessionLocal, engine
from wow_knowledge.database.models import Document, GameBuild, GameChange, PlayerMemory, Character
from wow_knowledge.ingestion import ingest_html, sync_sources
from wow_knowledge.profiles import get_character, save_character, save_memory
from wow_knowledge.retrieval import search_knowledge

pytestmark = pytest.mark.skipif(os.getenv("WOW_INTEGRATION") != "1", reason="Set WOW_INTEGRATION=1 after migrations")


@pytest.fixture
def db():
    with SessionLocal() as session:
        sync_sources(session)
        yield session


def test_pgvector_available():
    with engine.connect() as connection:
        assert connection.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")).scalar()


def test_ingest_version_duplicate_and_lexical(db, monkeypatch):
    from wow_knowledge import ingestion

    monkeypatch.setattr(ingestion.encoder, "encode", lambda texts, **kw: [[1.0] + [0.0] * 383 for _ in texts])
    url = f"https://wowforeverbuilds.com/test-{uuid4().hex}"
    def html(version):
        return f"<html lang='en'><head><title>Hunter leveling</title></head><body><article><h1>Hunter leveling</h1><p>Forever Hunter leveling uses a companion pet in version {version}. This guide discusses pet abilities and tactical leveling choices for the class in detail.</p></article></body></html>".encode()
    try:
        first = ingest_html(db, url, html("1.60.1.70707"))
        assert first["status"] == "created"
        assert ingest_html(db, url, html("1.60.1.70707"))["status"] == "unchanged"
        newer = ingest_html(db, url, html("1.60.1.70862"))
        assert newer["status"] == "updated"
        results = search_knowledge(db, "companion pet", game_build="1.60.1.70707")
        assert any(row["document_id"] == first["document_id"] for row in results["results"])
        recent = search_knowledge(db, "companion pet", game_build="1.60.1.70862")
        assert any(row["document_id"] == newer["document_id"] for row in recent["results"])
        semantic = search_knowledge(db, "unrelated semantic request", game_build="1.60.1.70862", class_name="Hunter")
        assert any(row["document_id"] == newer["document_id"] for row in semantic["results"])
        monkeypatch.setattr(ingestion.encoder, "encode", lambda texts, **kw: None)
        fallback = search_knowledge(db, "companion pet", game_build="1.60.1.70862")
        assert fallback["semantic_available"] is False
        assert any(row["document_id"] == newer["document_id"] for row in fallback["results"])
        assert db.scalar(select(Document).where(Document.id == first["document_id"])).status == "superseded"
        assert db.scalar(select(GameChange).where(GameChange.document_id == newer["document_id"])) is not None
    finally:
        for doc in db.scalars(select(Document).where(Document.canonical_url == url)).all():
            for change in db.scalars(select(GameChange).where(GameChange.document_id == doc.id)).all():
                db.delete(change)
            db.delete(doc)
        db.commit()
        for build in db.scalars(select(GameBuild).where(GameBuild.version.in_(["1.60.1.70707", "1.60.1.70862"]))).all():
            if not db.scalar(select(Document.id).where(Document.game_build_id == build.id)) and not db.scalar(select(GameChange.id).where(GameChange.to_build_id == build.id)):
                db.delete(build)
        db.commit()


def test_characters_and_memory(db):
    name = "Test" + uuid4().hex[:10]
    second = "Test" + uuid4().hex[:10]
    try:
        save_character(db, name, class_name="Hunter", level=23, goals=["Subir a 30"])
        save_character(db, second, class_name="Mage", level=60)
        save_memory(db, "Probar una estrategia alternativa", "strategy", name)
        assert get_character(db, name)["memories"][0]["kind"] == "strategy"
        assert get_character(db, second)["level"] == 60
    finally:
        characters = db.scalars(select(Character).where(Character.name.in_([name, second]))).all()
        for character in characters:
            for memory in db.scalars(select(PlayerMemory).where(PlayerMemory.character_id == character.id)).all():
                db.delete(memory)
        db.flush()
        for character in characters:
            db.delete(character)
        db.commit()
