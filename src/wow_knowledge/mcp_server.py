"""MCP STDIO entry point: stdout is reserved for the protocol."""

import logging
from datetime import datetime, timedelta, timezone

import httpx
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import select

from wow_knowledge.database import SessionLocal
from wow_knowledge.database.models import Document, GameBuild, GameChange, Source
from wow_knowledge.ingestion import allowed_source, ingest_url, normalize_url, refresh_sources, sync_sources
from wow_knowledge.profiles import get_character, get_preferences, save_character, save_memory, save_preferences
from wow_knowledge.retrieval import FRESHNESS_HOURS, search_knowledge

logging.basicConfig(level=logging.INFO)
mcp = MCPServer("azeroth-knowledge")


@mcp.tool()
def wow_search_knowledge(query: str, category: str | None = None, class_name: str | None = None,
                         specialization: str | None = None, activity: str | None = None,
                         game_build: str | None = None, language: str | None = None,
                         limit: int = 5) -> dict:
    """Search local indexed evidence before looking on the web; report build and freshness."""
    with SessionLocal() as db:
        return search_knowledge(db, query, category, class_name, specialization, activity, game_build, language, limit)


@mcp.tool()
def wow_ingest_url(url: str) -> dict:
    """Index one public, registered, robots-allowed HTTPS page; never crawl whole sites."""
    with SessionLocal() as db:
        sync_sources(db)
        try:
            result = ingest_url(db, url)
            source = allowed_source(db, result["url"])
            source.last_error = None
            db.commit()
            return result
        except (ValueError, httpx.HTTPError) as exc:
            db.rollback()
            try:
                source = allowed_source(db, normalize_url(url))
                source.last_error = str(exc)[:500]
                db.commit()
            except ValueError:
                pass
            raise ToolError(f"Cannot index URL: {exc}") from exc


@mcp.tool()
def wow_refresh_sources(source_name: str | None = None, full: bool = False) -> dict:
    """Refresh configured seed pages; full skips the refresh interval (not a full-site crawl)."""
    with SessionLocal() as db:
        return refresh_sources(db, source_name, full)


@mcp.tool()
def wow_get_character(name: str, realm: str = "") -> dict:
    """Read a player's explicitly saved character, goals and strategies."""
    with SessionLocal() as db:
        return get_character(db, name, realm)


@mcp.tool()
def wow_save_character(name: str, realm: str = "", class_name: str | None = None,
                       race: str | None = None, faction: str | None = None,
                       level: int | None = None, specialization: str | None = None,
                       professions: list[str] | None = None, equipment: dict[str, str] | None = None,
                       goals: list[str] | None = None, notes: str | None = None) -> dict:
    """Save ONLY character fields the player supplied or explicitly requested to remember."""
    with SessionLocal() as db:
        return save_character(db, name, realm, class_name=class_name, race=race, faction=faction,
                              level=level, specialization=specialization, professions=professions,
                              equipment=equipment, goals=goals, notes=notes)


@mcp.tool()
def wow_save_memory(note: str, kind: str, character_name: str | None = None, realm: str = "") -> dict:
    """Save a goal, recommendation or strategy ONLY when the player explicitly agrees."""
    with SessionLocal() as db:
        return save_memory(db, note, kind, character_name, realm)


@mcp.tool()
def wow_get_preferences() -> dict:
    """Read general preferences explicitly stored by the player."""
    with SessionLocal() as db:
        return get_preferences(db)


@mcp.tool()
def wow_save_preferences(preferences: dict[str, str]) -> dict:
    """Store only preferences explicitly supplied by the player; merge rather than replace."""
    with SessionLocal() as db:
        return save_preferences(db, preferences)


@mcp.tool()
def wow_source_status() -> dict:
    """Show registered sources, indexing errors, builds and outdated documents."""
    with SessionLocal() as db:
        sync_sources(db)
        rows = db.execute(select(Source)).scalars().all()
        data = []
        for source in rows:
            documents = db.scalars(select(Document).where(Document.source_id == source.id,
                                                         Document.status == "current")).all()
            stale = sum((datetime.now(timezone.utc) - (doc.updated_at_source or doc.extracted_at)) >
                        timedelta(hours=FRESHNESS_HOURS.get(doc.category, 168)) for doc in documents)
            data.append({"name": source.name, "domain": source.domain, "trust": source.trust,
                         "last_checked_at": source.last_checked_at.isoformat() if source.last_checked_at else None,
                         "last_indexed_at": max((doc.extracted_at for doc in documents), default=None).isoformat() if documents else None,
                         "documents": len(documents), "outdated": stale, "last_error": source.last_error})
        builds = db.scalars(select(GameBuild.version).order_by(GameBuild.first_seen_at.desc()).limit(20)).all()
        return {"sources": data, "detected_builds": builds}


@mcp.tool()
def wow_get_changes(game_build: str, limit: int = 10) -> dict:
    """List candidate source-document changes for a build; entries are not verified gameplay facts."""
    if not 1 <= limit <= 20:
        raise ValueError("limit must be 1-20")
    with SessionLocal() as db:
        rows = db.execute(select(GameChange, Document, GameBuild).join(Document, GameChange.document_id == Document.id)
                          .join(GameBuild, GameChange.to_build_id == GameBuild.id)
                          .where(GameBuild.version == game_build).order_by(GameChange.id.desc()).limit(limit)).all()
        return {"changes": [{"entity_type": change.entity_type, "name": change.entity_name,
                             "description": change.description, "status": change.status,
                             "source": doc.canonical_url, "to_build": build.version}
                            for change, doc, build in rows]}


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
