"""Character information is never inferred from public pages or chats."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from wow_knowledge.database.models import Character, PlayerMemory, PlayerProfile
from wow_knowledge.ingestion import CLASSES


def profile(db: Session) -> PlayerProfile:
    result = db.scalar(select(PlayerProfile).where(PlayerProfile.label == "default"))
    if not result:
        result = PlayerProfile(label="default", preferences={})
        db.add(result)
        db.flush()
    return result


def get_preferences(db: Session) -> dict:
    return {"preferences": profile(db).preferences}


def save_preferences(db: Session, preferences: dict[str, str]) -> dict:
    if len(preferences) > 20 or any(len(k) > 60 or len(v) > 300 for k, v in preferences.items()):
        raise ValueError("Too many preferences or value too long")
    p = profile(db)
    p.preferences = {**p.preferences, **preferences}
    db.commit()
    return get_preferences(db)


def get_character(db: Session, name: str, realm: str = "") -> dict:
    p = profile(db)
    character = db.scalar(select(Character).where(Character.profile_id == p.id, Character.name == name, Character.realm == realm))
    if not character:
        return {"found": False, "name": name, "realm": realm}
    memories = db.scalars(select(PlayerMemory).where(PlayerMemory.character_id == character.id).order_by(PlayerMemory.created_at.desc()).limit(10)).all()
    return {"found": True, "id": character.id, "name": character.name, "realm": character.realm,
            "class_name": character.class_name, "race": character.race, "faction": character.faction,
            "level": character.level, "specialization": character.specialization,
            "professions": character.professions, "equipment": character.equipment,
            "goals": character.goals, "notes": character.notes,
            "memories": [{"kind": m.kind, "note": m.note} for m in memories]}


def save_character(db: Session, name: str, realm: str = "", **fields) -> dict:
    if not name.strip() or len(name) > 100 or len(realm) > 100:
        raise ValueError("Invalid character identity")
    if fields.get("class_name") is not None and fields["class_name"].title() not in CLASSES:
        raise ValueError("Unknown class")
    if fields.get("level") is not None and not 1 <= fields["level"] <= 60:
        raise ValueError("Level must be 1-60")
    if fields.get("faction") is not None and fields["faction"].lower() not in ("alliance", "horde"):
        raise ValueError("Faction must be Alliance or Horde")
    p = profile(db)
    character = db.scalar(select(Character).where(Character.profile_id == p.id, Character.name == name, Character.realm == realm))
    if not character:
        character = Character(profile_id=p.id, name=name, realm=realm, professions=[], equipment={}, goals=[])
        db.add(character)
    for key, value in fields.items():
        if value is not None:
            setattr(character, key, value)
    db.commit()
    return get_character(db, name, realm)


def save_memory(db: Session, note: str, kind: str, character_name: str | None = None, realm: str = "") -> dict:
    if kind not in ("goal", "recommendation", "strategy") or not 1 <= len(note) <= 2000:
        raise ValueError("Invalid memory kind or length")
    p = profile(db)
    character = None
    if character_name:
        character = db.scalar(select(Character).where(Character.profile_id == p.id,
                    Character.name == character_name, Character.realm == realm))
        if character is None:
            raise ValueError("Character not registered")
    entry = PlayerMemory(profile_id=p.id, character_id=character.id if character else None, kind=kind, note=note)
    db.add(entry)
    db.commit()
    return {"saved": True, "id": entry.id, "kind": kind, "character_name": character_name}
