import sqlite3
import time

from meta_morphis import config
from meta_morphis.models.meta import MetaEntry


def get_meta_timestamp(conn: sqlite3.Connection, format_name: str) -> int | None:
    """Unix time of the last successful scrape of `format_name`, or None
    if it has never been scraped. get_meta_cards serves the cached list
    when a scrape fails, so this is how a caller tells how old that
    list really is.
    """
    c = conn.cursor()
    row: tuple[int] | None = c.execute(
        "SELECT last_updated FROM meta_refresh WHERE format = ?", (format_name,)
    ).fetchone()
    return row[0] if row else None

def should_refresh_meta(conn: sqlite3.Connection, format_name: str) -> bool:
    last_updated = get_meta_timestamp(conn, format_name)

    if last_updated is None:
        return True # never scraped before

    # A negative age means the timestamp was written by a clock that ran
    # ahead - treat it as stale, or refreshing stops until time catches up.
    age = time.time() - last_updated
    return age < 0 or age > config.GOLDFISH_REFRESH_RATE

def update_meta_timestamp(conn: sqlite3.Connection, format_name: str) -> None:
    c = conn.cursor()
    c.execute("""
        INSERT INTO meta_refresh (format, last_updated)
        VALUES (?, ?)
        ON CONFLICT(format) DO UPDATE SET last_updated = excluded.last_updated
    """, (format_name, int(time.time()),))

def get_meta_from_cache(conn: sqlite3.Connection, format_name: str) -> list[MetaEntry]:
    c = conn.cursor()
    rows = c.execute("""
        SELECT name, rank, percent, avg_copies, lookup_name
        FROM meta
        WHERE format = ?
        ORDER BY rank IS NULL, rank
    """, (format_name,)).fetchall()

    meta: list[MetaEntry] = []
    for name, rank, percent, avg_copies, lookup_name in rows:
        meta.append(MetaEntry(
            name=name,
            rank=rank,
            percent=percent,
            avg_copies=avg_copies,
            lookup_name=lookup_name,
        ))

    return meta

def save_meta_to_cache(conn: sqlite3.Connection, meta: list[MetaEntry], format_name: str) -> None:
    c = conn.cursor()

    # Clear old format meta before inserting new one
    c.execute("""
        DELETE FROM meta
        WHERE format = ?
        """, (format_name,))

    for entry in meta:
        c.execute("""
            INSERT INTO meta (name, format, rank, percent, avg_copies, lookup_name)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            entry.name,
            format_name,
            entry.rank,
            entry.percent,
            entry.avg_copies,
            entry.lookup_name
        ))