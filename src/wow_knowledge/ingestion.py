"""Limited, public, allowlisted web ingestion."""

import hashlib
import ipaddress
import re
import socket
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx
import yaml
from bs4 import BeautifulSoup
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from wow_knowledge.config import ROOT, settings
from wow_knowledge.database.models import Document, DocumentChunk, GameBuild, GameChange, Source
from wow_knowledge.embeddings import encoder

BUILD_RE = re.compile(r"\b(?:1\.\d{2}\.\d+\.\d{4,6})\b")
CLASSES = ("Warrior", "Paladin", "Hunter", "Rogue", "Priest", "Shaman", "Mage", "Warlock", "Druid")
SPECS = ("Beast Mastery", "Marksmanship", "Survival", "Retribution", "Protection", "Holy", "Feral", "Balance", "Restoration", "Affliction", "Demonology", "Destruction", "Frost", "Fire", "Arcane", "Combat", "Assassination", "Subtlety", "Arms", "Fury", "Enhancement", "Elemental", "Discipline", "Shadow")


def configured_sources() -> list[dict]:
    with (ROOT / "config" / "sources.yaml").open(encoding="utf-8") as stream:
        sources = yaml.safe_load(stream)["sources"]
    return sources


def sync_sources(db: Session) -> None:
    for item in configured_sources():
        existing = db.scalar(select(Source).where(Source.name == item["name"]))
        if existing is None:
            existing = Source(name=item["name"], domain=item["domain"], trust=item["trust"],
                              seeds=item.get("seeds", []), refresh_hours=item["refresh_hours"])
            db.add(existing)
        else:
            existing.domain = item["domain"]
            existing.trust = item["trust"]
            existing.seeds = item.get("seeds", [])
            existing.refresh_hours = item["refresh_hours"]
    db.commit()


def normalize_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("Only public HTTPS URLs on the default port are allowed")
    host = parsed.hostname.lower().rstrip(".")
    if not re.fullmatch(r"[a-z0-9.-]+", host) or host.startswith("-"):
        raise ValueError("Invalid hostname")
    return urlunsplit(("https", host, parsed.path or "/", parsed.query, ""))


def check_public_host(host: str) -> None:
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("Hostname cannot be resolved") from exc
    if not addresses or any(not ipaddress.ip_address(info[4][0]).is_global for info in addresses):
        raise ValueError("Private or non-public address rejected")


def allowed_source(db: Session, url: str) -> Source:
    host = urlsplit(url).hostname
    source = db.scalar(select(Source).where(Source.domain == host))
    if source is None:
        raise ValueError("Domain not registered in config/sources.yaml")
    return source


def fetch_public(db: Session, url: str) -> tuple[str, bytes, str]:
    """Each redirect is revalidated. No cookies or authenticated requests."""
    current = normalize_url(url)
    with httpx.Client(follow_redirects=False, timeout=15, trust_env=False,
                      headers={"User-Agent": settings.wow_user_agent}) as client:
        for _ in range(4):
            source = allowed_source(db, current)
            check_public_host(source.domain)
            robot_url = f"https://{source.domain}/robots.txt"
            with client.stream("GET", robot_url) as robots:
                if robots.status_code != 200:
                    raise ValueError("Cannot confirm robots.txt access policy")
                robots_data = bytearray()
                for block in robots.iter_bytes():
                    robots_data.extend(block)
                    if len(robots_data) > 256_000:
                        raise ValueError("robots.txt size limit exceeded")
            parser = RobotFileParser()
            parser.parse(robots_data.decode("utf-8", errors="replace").splitlines())
            if not parser.can_fetch(settings.wow_user_agent, current):
                raise ValueError("robots.txt disallows this URL")
            with client.stream("GET", current) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("Redirect without location")
                    current = normalize_url(urljoin(current, location))
                    continue
                response.raise_for_status()
                media_type = response.headers.get("content-type", "").lower()
                if "text/html" not in media_type:
                    raise ValueError("Only HTML pages are supported")
                data = bytearray()
                for part in response.iter_bytes():
                    data.extend(part)
                    if len(data) > settings.wow_max_download_bytes:
                        raise ValueError("Download size limit exceeded")
                return current, bytes(data), media_type
    raise ValueError("Too many redirects")


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
        except (ValueError, TypeError):
            return None
    return date.replace(tzinfo=timezone.utc) if date.tzinfo is None else date


def visible_date(text: str, label: str) -> datetime | None:
    match = re.search(r"\b" + label + r"\s+([A-Za-z]{3})\s+(\d{1,2}),\s*(\d{4})\b", text[:650], re.I)
    if match:
        try:
            return datetime.strptime(" ".join(match.groups()), "%b %d %Y").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def extract_html(raw: bytes) -> dict:
    # The supported news/guide sources serve UTF-8; decoding explicitly avoids
    # html.parser's occasional Windows-1252 guess for pages without a charset.
    soup = BeautifulSoup(raw.decode("utf-8", errors="replace"), "html.parser")
    title = (soup.find("h1") or soup.title)
    name = title.get_text(" ", strip=True) if title else "Untitled"
    meta = {tag.get("property") or tag.get("name"): tag.get("content")
            for tag in soup.find_all("meta") if tag.get("content")}
    container = soup.find("article") or soup.find("main") or soup.body or soup
    for tag in container.find_all(("script", "style", "nav", "footer", "form", "aside", "noscript", "svg", "button")):
        tag.decompose()
    for section in container.find_all("section"):
        heading = section.find(["h2", "h3"])
        if heading and (heading.get_text(" ", strip=True).lower().startswith("feedback") or
                        heading.get_text(" ", strip=True).lower().startswith("more ")):
            section.decompose()
    lines = [" ".join(line.split()) for line in container.get_text("\n").splitlines()]
    body = "\n".join(re.sub(r"\s*[·•]?\s*\d[\d,]* views\b", "", line, flags=re.I)
                     for line in lines if line and not re.fullmatch(r"\d[\d,]* views", line, re.I))
    if len(body) < 120:
        raise ValueError("No meaningful text extracted")
    return {"title": name[:500], "body": body[:200_000],
            "language": (soup.html.get("lang", "en") if soup.html else "en")[:12].split("-")[0],
            "published_at": parse_date(meta.get("article:published_time") or meta.get("datePublished")) or visible_date(body, "published"),
            "updated_at_source": parse_date(meta.get("article:modified_time") or meta.get("dateModified")) or visible_date(body, "updated")}


def evidence_status(source: Source, title: str, body: str) -> str:
    if source.trust == "official":
        return "official"
    if "theorycraft" in (title + body[:1200]).lower() or "not checked in game" in body.lower():
        return "theorycraft"
    if source.trust == "client_data_claimed":
        return "client_data_claimed"
    return "guide"


def split_chunks(body: str, size: int = 1000) -> list[str]:
    """Short overlapping windows, safely below the E5 512-token input cap."""
    words = body.split()
    chunks = []
    current: list[str] = []
    for word in words:
        if current and len(" ".join(current + [word])) > size:
            chunks.append(" ".join(current))
            current = current[-25:]
        current.append(word)
    if current:
        chunks.append(" ".join(current))
    return chunks[:180]


def classify(title: str, body: str) -> dict:
    lower = title.lower()
    category = next((cat for token, cat in (("hotfix", "hotfix"), ("patch", "changes"), ("legacy", "legacy"),
                ("talent", "builds"), ("class", "classes"), ("dungeon", "dungeons"),
                ("raid", "raids"), ("profession", "professions"), ("level", "leveling"),
                ("pvp", "pvp"), ("item", "items")) if token in lower), "general")
    classes = [name for name in CLASSES if re.search(r"\b" + name + r"\b", title, re.I)]
    specs = [spec for spec in SPECS if re.search(r"\b" + spec + r"\b", title, re.I)]
    # A later section or site footer may describe a different system/build.
    # Only a version in the article lead can apply to the whole document.
    builds = set(BUILD_RE.findall(title + "\n" + body))
    lead_builds = set(BUILD_RE.findall(title + "\n" + body[:700]))
    return {"category": category, "class_name": classes[0] if len(classes) == 1 else None,
            "specialization": specs[0] if len(specs) == 1 else None,
            "activity": next((activity for activity in ("pvp", "leveling", "raid", "dungeon") if activity in lower), None),
            "build": next(iter(builds)) if len(builds) == len(lead_builds) == 1 else None}


def ingest_html(db: Session, url: str, raw: bytes) -> dict:
    """Also usable with fixture HTML; URL must still be on an allowed domain."""
    url = normalize_url(url)
    source = allowed_source(db, url)
    item = extract_html(raw)
    if "forever" not in item["title"].lower() and "forever" not in item["body"][:4000].lower() and "wow-forever" not in url:
        raise ValueError("Page is not demonstrably about WoW Forever")
    content_hash = hashlib.sha256(item["body"].encode("utf-8")).hexdigest()
    verification = evidence_status(source, item["title"], item["body"])
    metadata = classify(item["title"], item["body"])
    build = None
    if metadata["build"]:
        build = db.scalar(select(GameBuild).where(GameBuild.version == metadata["build"]))
        if build is None:
            build = GameBuild(version=metadata["build"])
            db.add(build)
            db.flush()
    old = db.scalar(select(Document).where(Document.canonical_url == url, Document.status == "current").order_by(Document.id.desc()))
    if old and old.content_hash == content_hash:
        old.extracted_at = datetime.now(timezone.utc)
        old.evidence_status = verification
        old.game_build_id = build.id if build else None
        old.published_at = item["published_at"]
        old.updated_at_source = item["updated_at_source"]
        db.commit()
        return {"status": "unchanged", "document_id": old.id, "url": url}
    existing = db.scalar(select(Document).where(Document.canonical_url == url, Document.content_hash == content_hash))
    if old:
        old.status = "superseded"
    if existing:
        existing.status = "current"
        existing.extracted_at = datetime.now(timezone.utc)
        existing.evidence_status = verification
        existing.game_build_id = build.id if build else None
        db.commit()
        return {"status": "restored", "document_id": existing.id, "url": url}
    doc = Document(source_id=source.id, game_build_id=build.id if build else None,
                   canonical_url=url, domain=source.domain, title=item["title"],
                   category=metadata["category"], language=item["language"],
                   class_name=metadata["class_name"], specialization=metadata["specialization"],
                   activity=metadata["activity"], published_at=item["published_at"],
                   updated_at_source=item["updated_at_source"], content_hash=content_hash,
                   status="current", evidence_status=verification, body=item["body"])
    chunks = split_chunks(item["body"])
    vectors = encoder.encode(chunks)
    db.add(doc)
    db.flush()
    for i, text in enumerate(chunks):
        db.add(DocumentChunk(document_id=doc.id, ordinal=i, text=text,
                             text_search=func.to_tsvector("simple", text),
                             embedding=vectors[i] if vectors else None,
                             embedding_model=settings.wow_embedding_model if vectors else None))
    if old and build and old.game_build_id and old.game_build_id != build.id:
        db.add(GameChange(from_build_id=old.game_build_id, to_build_id=build.id,
                          document_id=doc.id, entity_type="document", entity_name=doc.title[:160],
                          description="The source document changed between builds; inspect revisions for specific mechanics.",
                          status="unverified"))
    db.commit()
    return {"status": "updated" if old else "created", "document_id": doc.id,
            "url": url, "chunks": len(chunks), "build": metadata["build"], "embeddings": bool(vectors)}


def ingest_url(db: Session, url: str) -> dict:
    url, body, _ = fetch_public(db, url)
    return ingest_html(db, url, body)


def refresh_sources(db: Session, source_name: str | None = None, full: bool = False) -> dict:
    sync_sources(db)
    items = db.scalars(select(Source).where(Source.name == source_name) if source_name else select(Source)).all()
    if source_name and not items:
        raise ValueError("Unknown source")
    results = []
    now = datetime.now(timezone.utc)
    for source in items:
        if not full and source.last_checked_at and (now - source.last_checked_at).total_seconds() < source.refresh_hours * 3600:
            continue
        for url in source.seeds[:20]:
            try:
                result = ingest_url(db, url)
                source.last_error = None
                results.append({"source": source.name, **result})
            except Exception as exc:
                source.last_error = str(exc)[:500]
                results.append({"source": source.name, "url": url, "error": source.last_error})
        source.last_checked_at = now
        db.commit()
    return {"checked": len(results), "results": results}
