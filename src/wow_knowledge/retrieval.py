"""Local hybrid search: weighted reciprocal-rank fusion and strict build filters."""

from datetime import datetime, timezone

import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from wow_knowledge.config import ROOT, settings
from wow_knowledge.database.models import Document, DocumentChunk, GameBuild, Source
from wow_knowledge.embeddings import encoder

with (ROOT / "config" / "freshness.yaml").open(encoding="utf-8") as stream:
    FRESHNESS_HOURS = yaml.safe_load(stream)["freshness_hours"]


def search_knowledge(db: Session, query: str, category: str | None = None,
                     class_name: str | None = None, specialization: str | None = None,
                     activity: str | None = None, game_build: str | None = None,
                     language: str | None = None, limit: int = 5) -> dict:
    if not query.strip() or len(query) > 500 or not 1 <= limit <= 10:
        raise ValueError("query must be 1-500 characters and limit 1-10")
    conditions = [Document.status == "current"] if not game_build else []
    for column, value in ((Document.category, category), (Document.class_name, class_name),
                          (Document.specialization, specialization), (Document.activity, activity),
                          (Document.language, language)):
        if value:
            conditions.append(func.lower(column) == value.lower())
    if game_build:
        conditions.append(GameBuild.version == game_build)
    base = (select(DocumentChunk, Document, Source, GameBuild)
            .join(Document, DocumentChunk.document_id == Document.id)
            .join(Source, Document.source_id == Source.id)
            .outerjoin(GameBuild, Document.game_build_id == GameBuild.id)
            .where(*conditions))
    rank = func.ts_rank_cd(DocumentChunk.text_search, func.websearch_to_tsquery("simple", query))
    lexical = db.execute(base.where(DocumentChunk.text_search.op("@@")(func.websearch_to_tsquery("simple", query)))
                         .order_by(rank.desc()).limit(35)).all()
    vectors = encoder.encode([query], query=True)
    semantic = []
    if vectors:
        distance = DocumentChunk.embedding.cosine_distance(vectors[0])
        semantic = db.execute(base.where(DocumentChunk.embedding.is_not(None),
                                          DocumentChunk.embedding_model == settings.wow_embedding_model)
                              .order_by(distance).limit(35)).all()
    scores: dict[int, float] = {}
    rows: dict[int, tuple] = {}
    for weight, candidates in ((1.0, lexical), (1.0, semantic)):
        for i, row in enumerate(candidates):
            chunk = row[0]
            rows[chunk.id] = row
            scores[chunk.id] = scores.get(chunk.id, 0) + weight / (60 + i + 1)
    selected = sorted(scores, key=scores.get, reverse=True)[:limit]
    results = []
    now = datetime.now(timezone.utc)
    for chunk_id in selected:
        chunk, doc, source, build = rows[chunk_id]
        hours = FRESHNESS_HOURS.get(doc.category, 168)
        checked_at = doc.updated_at_source or doc.extracted_at
        stale = (now - checked_at).total_seconds() > hours * 3600
        results.append({"chunk_id": chunk.id, "document_id": doc.id, "title": doc.title,
                        "text": chunk.text[:1100], "url": doc.canonical_url,
                        "source": source.name, "trust": source.trust, "category": doc.category,
                        "build": build.version if build else None, "build_unverified": build is None,
                        "status": doc.status, "evidence_status": doc.evidence_status,
                        "extracted_at": doc.extracted_at.isoformat(),
                        "published_at": doc.published_at.isoformat() if doc.published_at else None,
                        "source_updated_at": doc.updated_at_source.isoformat() if doc.updated_at_source else None,
                        "stale": stale})
    return {"results": results, "count": len(results),
            "semantic_available": bool(vectors),
            "needs_research": not results or any(r["stale"] for r in results) or
                              all(r["evidence_status"] == "theorycraft" for r in results),
            "warning": "Build unspecified: verify before applying patch-specific advice" if any(r["build_unverified"] for r in results) else None}
