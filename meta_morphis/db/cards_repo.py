import sqlite3
import time
import json

from typing import Any
from .utils import normalize_name
from meta_morphis.models.card import CachedCard
from meta_morphis.models.card_face import CardFace

def get_card_from_cache(conn: sqlite3.Connection, name: str) -> CachedCard | None:
    c = conn.cursor()

    key = normalize_name(name)

    c.execute(
        """
        SELECT json, updated_at
        FROM cards
        WHERE name = ?
            OR LOWER(json_extract(json, '$.card_faces[0].name')) = ?
        """,
        (key, key)
    )

    row = c.fetchone()

    if not row:
        return None

    json_blob, updated_at = row

    try:
        raw = json.loads(json_blob)
        age = time.time() - updated_at
        return build_cached_card(raw, age)
    except json.JSONDecodeError:
        return None

def save_cards_to_cache(conn: sqlite3.Connection, raw_cards: list[dict[str, Any]]) -> None:
    c = conn.cursor()
    for card in raw_cards:
        key = normalize_name(card["name"])
        c.execute("""
            INSERT INTO cards (id, name, json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                json = excluded.json,
                updated_at = excluded.updated_at
        """, (
            card["id"],
            key, 
            json.dumps(card),
            int(time.time())
        ))
    conn.commit()

def build_cached_card(raw: dict[str, Any], age: float) -> CachedCard:
    faces = []

    # Build CardFace objects if present
    if "card_faces" in raw:
        for face in raw["card_faces"]:
            faces.append(CardFace(
                name=face["name"],
                mana_cost=face.get("mana_cost") or None,
                type_line=face["type_line"]
            ))

    # Determine mana_cost
    if faces:
        mana_cost = faces[0].mana_cost
    else:
        mana_cost = raw.get("mana_cost")

    return CachedCard(
        id=raw["id"],
        name=raw["name"],
        age=age,
        mana_cost=mana_cost,
        type_line=raw.get("type_line", ""),
        faces=faces,
        raw=raw
    )