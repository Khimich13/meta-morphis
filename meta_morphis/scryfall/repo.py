import sqlite3
import time
import json

from typing import Any

from meta_morphis.utils.text import normalize_name

def get_card_from_cache(conn: sqlite3.Connection, name: str) -> dict[str, Any] | None:
    c = conn.cursor()

    key = normalize_name(name)

    c.execute(
        """
        SELECT json
        FROM cards
        WHERE name = ?
            OR LOWER(json_extract(json, '$.card_faces[0].name')) = ?
            OR LOWER(json_extract(json, '$.card_faces[1].name')) = ?
        """,
        (key, key, key)
    )

    row = c.fetchone()
    if not row:
        return None
    json_blob = row[0]

    try:
        raw: dict[str, Any] = json.loads(json_blob)
        return raw
    except json.JSONDecodeError:
        return None

def get_card_age(conn: sqlite3.Connection, name: str) -> int | None:
    c = conn.cursor()

    key = normalize_name(name)

    c.execute(
        """
        SELECT updated_at
        FROM cards
        WHERE name = ?
            OR LOWER(json_extract(json, '$.card_faces[0].name')) = ?
            OR LOWER(json_extract(json, '$.card_faces[1].name')) = ?
        """,
        (key, key, key)
    )

    row = c.fetchone()

    if row is None:
        return None

    updated_at: int = row[0]

    return int(time.time()) - updated_at

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