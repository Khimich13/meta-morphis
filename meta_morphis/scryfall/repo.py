import json
import sqlite3
import time
from typing import Any

import config
from meta_morphis.models.card import Card
from meta_morphis.utils.text import normalize_name


def get_card_from_cache(conn: sqlite3.Connection, name: str) -> Card | None:
    c = conn.cursor()

    key = normalize_name(name)

    c.execute("""
        SELECT cards.json, cards.updated_at
        FROM card_names
        JOIN cards ON card_names.card_id = cards.id
        WHERE card_names.name = ?
    """, (key,))

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
    for raw in raw_cards:
        card = Card.from_raw(raw)
        key = normalize_name(card.name)

        # Insert/update main card row
        c.execute("""
            INSERT INTO cards (id, name, json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                json = excluded.json,
                updated_at = excluded.updated_at
        """, (
            card.id,
            key, 
            json.dumps(raw),
            int(time.time())
        ))

        # Insert main name -> id
        c.execute("""
            INSERT OR REPLACE INTO card_names (name, card_id)
            VALUES (?, ?)
        """, (key, card.id))

        # Insert face names -> id
        for face in card.faces:
            face_key = normalize_name(face.name)
            c.execute("""
                INSERT OR REPLACE INTO card_names (name, card_id)
                VALUES (?, ?)
            """, (face_key, card.id))

def record_bad_name_attempt(conn: sqlite3.Connection, name: str) -> None:
    key = normalize_name(name)

    c = conn.cursor()
    c.execute("""
        INSERT INTO card_lookup_failures (name, last_attempt)
        VALUES (?, ?)
        ON CONFLICT(name) DO UPDATE SET
            last_attempt = excluded.last_attempt
    """, (
        key,
        int(time.time())
    ))

def should_skip_lookup(conn: sqlite3.Connection, name: str, cooldown: int = config.SCRYFALL_BAD_NAMES_LOOKUP_COOLDOWN) -> bool:
    key = normalize_name(name)
    cutoff = int(time.time()) - cooldown

    c = conn.cursor()
    c.execute("""
        SELECT last_attempt
        FROM card_lookup_failures
        WHERE name = ?
    """, (key,))
    row = c.fetchone()

    if not row:
        return False

    last_attempt = int(row[0])
    return last_attempt > cutoff