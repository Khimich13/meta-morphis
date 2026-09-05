import json
import sqlite3
import time
from typing import Any

from meta_morphis.models.card import Card
from meta_morphis.utils.text import normalize_name


def get_card_from_cache(conn: sqlite3.Connection, name: str) -> Card | None:
    c = conn.cursor()

    key = normalize_name(name)

    c.execute(
        """
        SELECT json, updated_at
        FROM cards
        WHERE name = ?
            OR EXISTS (
                SELECT 1
                FROM json_each(cards.json, '$.card_faces')
                WHERE LOWER(json_each.value ->> '$.name') = ?
            )
        """,
        (key, key)
    )

    row = c.fetchone()
    if not row:
        return None

    json_blob, updated_at = row

    try:
        raw: dict[str, Any] = json.loads(json_blob)
    except json.JSONDecodeError:
        return None

    card = Card.from_raw(raw)
    card.age = int(time.time()) - updated_at
    return card

def save_cards_to_cache(conn: sqlite3.Connection, raw_cards: list[dict[str, Any]]) -> None:
    c = conn.cursor()
    for card in raw_cards:
        key = normalize_name(card["name"])
        c.execute("""
            INSERT INTO cards (id, name, json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                json = excluded.json,
                updated_at = excluded.updated_at
        """, (
            card["id"],
            key, 
            json.dumps(card),
            int(time.time())
        ))
    conn.commit()