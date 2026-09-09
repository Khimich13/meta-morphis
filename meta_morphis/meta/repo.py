import sqlite3
import time

import config
from meta_morphis.models.meta import MetaEntry


def should_refresh_meta(conn: sqlite3.Connection, format: str) -> bool:
    c = conn.cursor()
    row: tuple[int] | None = c.execute(
        "SELECT last_updated FROM meta_refresh WHERE format = ?", (format,)
    ).fetchone()

    if row is None:
        return True # never scraped before

    last_updated = row[0]
    return (time.time() - last_updated) > config.META_REFRESH_RATE

def update_meta_timestamp(conn: sqlite3.Connection, format: str) -> None:
    c = conn.cursor()
    c.execute("""
        INSERT INTO meta_refresh (format, last_updated)
        VALUES (?, ?)
        ON CONFLICT(format) DO UPDATE SET last_updated = excluded.last_updated
    """, (format, int(time.time()),))
    conn.commit()

def load_cached_meta(conn: sqlite3.Connection, format: str) -> list[MetaEntry]:
    c = conn.cursor()
    rows = c.execute("""
        SELECT name, rank, percent, avg_copies, lookup_name
        FROM meta
        WHERE format = ?
        ORDER BY rank ASC
    """, (format,)).fetchall()

    meta = []
    for name, rank, percent, avg_copies, lookup_name in rows:
        meta.append(MetaEntry(
            name= name,
            rank= rank,
            percent= percent,
            avg_copies= avg_copies,
            lookup_name= lookup_name
        )
    )

    return meta

def save_meta_to_cache(conn: sqlite3.Connection, meta: list[MetaEntry], format: str) -> None:
    c = conn.cursor()

    # Clear old format meta before inserting new one
    c.execute("""
        DELETE FROM meta
        WHERE format = ?
        """, (format,))

    for entry in meta:
        c.execute("""
            INSERT INTO meta (name, format, rank, percent, avg_copies, lookup_name)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            entry.name,
            format,
            entry.rank,
            entry.percent,
            entry.avg_copies,
            entry.lookup_name
        ))

    conn.commit()