import time
import json
import sqlite3

def get_card_from_cache(name):
    conn = sqlite3.connect("cards.db")
    c = conn.cursor()
    c.execute("SELECT json, updated_at FROM cards WHERE name = ?", (name,))
    row = c.fetchone()
    conn.close()

    if not row:
        return None

    json_blob, updated_at = row
    age = time.time() - updated_at

    if age > 86400:  # 24 hours
        return None  # stale

    return json.loads(json_blob)


def save_card_to_cache(card):
    conn = sqlite3.connect("cards.db")
    c = conn.cursor()
    c.execute("""
        INSERT INTO cards (id, name, json, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            json = excluded.json,
            updated_at = excluded.updated_at
    """, (
        card["id"],
        card["name"],
        json.dumps(card),
        int(time.time())
    ))
    conn.commit()
    conn.close()
