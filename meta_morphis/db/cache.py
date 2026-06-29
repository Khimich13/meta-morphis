import time
import json

from .utils import normalize_name

META_REFRESH_RATE = 24 * 60 * 60 # 24 hours
SCRYFALL_REFRESH_RATE = 24 * 60 * 60 * 30 # 30 days

def get_card_from_cache(conn, name):
    c = conn.cursor()

    key = normalize_name(name)
    c.execute("SELECT json, updated_at FROM cards WHERE name = ?", (key,))
    row = c.fetchone()

    if not row:
        return None

    json_blob, updated_at = row
    age = time.time() - updated_at

    if age > SCRYFALL_REFRESH_RATE:
        return None  # stale

    try:
        return json.loads(json_blob)
    except json.JSONDecodeError:
        return None


def save_card_to_cache(conn, card):
    c = conn.cursor()

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

def should_refresh_meta(conn, format):
    c = conn.cursor()
    row = c.execute(
        "SELECT last_updated FROM meta_refresh WHERE format = ?", (format,)
    ).fetchone()

    if row is None:
        return True # never scraped before

    last_updated = row[0]
    return (time.time() - last_updated) > META_REFRESH_RATE

def update_meta_timestamp(conn, format):
    c = conn.cursor()
    c.execute("""
        INSERT INTO meta_refresh (format, last_updated)
        VALUES (?, ?)
        ON CONFLICT(format) DO UPDATE SET last_updated = excluded.last_updated
    """, (format, int(time.time()),))
    conn.commit()

def load_cached_meta(conn, format):
    c = conn.cursor()
    rows = c.execute("""
        SELECT name, rank, percent, deck_count
        FROM meta_cards
        WHERE format = ?
        ORDER BY rank ASC
    """, (format,)).fetchall()

    meta = []
    for name, rank, percent, deck_count in rows:
        meta.append({
            "name": name,
            "rank": rank,
            "percent": percent,
            "deck_count": deck_count
        })

    return meta

def save_meta_to_cache(conn, meta_list, format):
    """
    Save the scraped Goldfish meta list into the meta_cards table.
    meta_list should be a list of dicts like:
    [
        {"name": "lightning bolt", "rank": 1, "percent": 23.4, "deck_count": 120},
        ...
    ]
    """
    c = conn.cursor()

    # Clear old format meta before inserting new one
    c.execute("""
        DELETE FROM meta_cards
        WHERE format = ?
        """, (format,))

    for entry in meta_list:
        c.execute("""
            INSERT INTO meta_cards (name, format, rank, percent, deck_count)
            VALUES (?, ?, ?, ?, ?)
        """, (
            entry["name"],
            format,
            entry.get("rank"),
            entry.get("percent"),
            entry.get("deck_count"),
        ))

    conn.commit()
