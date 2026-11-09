"""Simple setup and smoke-test commands for users without SQL knowledge."""

import argparse
import json

import httpx

from wow_knowledge.database import SessionLocal
from wow_knowledge.ingestion import allowed_source, ingest_url, normalize_url, refresh_sources, sync_sources
from wow_knowledge.retrieval import search_knowledge


def main() -> None:
    parser = argparse.ArgumentParser(description="Local WoW Forever knowledge")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("init-sources")
    ingest = sub.add_parser("ingest")
    ingest.add_argument("url")
    find = sub.add_parser("search")
    find.add_argument("query")
    refresh = sub.add_parser("refresh")
    refresh.add_argument("--source")
    refresh.add_argument("--full", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        if args.action == "init-sources":
            sync_sources(db)
            result = {"sources": "registered"}
        elif args.action == "ingest":
            sync_sources(db)
            try:
                result = ingest_url(db, args.url)
                allowed_source(db, result["url"]).last_error = None
                db.commit()
            except (ValueError, httpx.HTTPError) as exc:
                db.rollback()
                try:
                    allowed_source(db, normalize_url(args.url)).last_error = str(exc)[:500]
                    db.commit()
                except ValueError:
                    pass
                parser.exit(1, f"Cannot index URL: {exc}\n")
        elif args.action == "search":
            result = search_knowledge(db, args.query)
        else:
            result = refresh_sources(db, args.source, args.full)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
