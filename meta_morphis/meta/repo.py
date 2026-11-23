import sqlite3
import time
from datetime import date

from meta_morphis import config
from meta_morphis.models.meta import MetaEntry


def get_meta_timestamp(conn: sqlite3.Connection, format_name: str) -> int | None:
    """Unix time of the last successful count of `format_name`'s decks,
    or None if they have never been counted. get_meta_cards serves the
    last count when counting fails, so this is how a caller tells how
    old that count really is.
    """
    c = conn.cursor()
    row: tuple[int] | None = c.execute(
        "SELECT last_updated FROM meta_refresh WHERE format = ?", (format_name,)
    ).fetchone()
    return row[0] if row else None


def should_refresh_meta(conn: sqlite3.Connection, format_name: str) -> bool:
    last_updated = get_meta_timestamp(conn, format_name)

    if last_updated is None:
        return True  # never counted before

    # A negative age means the timestamp was written by a clock that ran
    # ahead - treat it as stale, or refreshing stops until time catches up.
    age = time.time() - last_updated
    return age < 0 or age > config.META_REFRESH_RATE


def update_meta_timestamp(
    conn: sqlite3.Connection, format_name: str, decks_to: date | None
) -> None:
    """Records that `format_name`'s decks were counted now, to the day
    of the newest decks, `decks_to`"""
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO meta_refresh (format, last_updated, decks_to)
        VALUES (?, ?, ?)
        ON CONFLICT(format) DO UPDATE SET
            last_updated = excluded.last_updated,
            decks_to = excluded.decks_to
    """,
        (
            format_name,
            int(time.time()),
            decks_to.isoformat() if decks_to else None,
        ),
    )


def get_decks_to(conn: sqlite3.Connection, format_name: str) -> str | None:
    """The day of the newest decks in `format_name`'s last count, e.g.
    "2026-11-19", or None if it isn't known"""
    row: tuple[str | None] | None = conn.execute(
        "SELECT decks_to FROM meta_refresh WHERE format = ?", (format_name,)
    ).fetchone()
    return row[0] if row else None


def get_meta_from_cache(conn: sqlite3.Connection, format_name: str) -> list[MetaEntry]:
    c = conn.cursor()
    rows = c.execute(
        """
        SELECT name, rank, percent, avg_copies
        FROM meta
        WHERE format = ?
        ORDER BY rank IS NULL, rank
    """,
        (format_name,),
    ).fetchall()

    meta: list[MetaEntry] = []
    for name, rank, percent, avg_copies in rows:
        meta.append(
            MetaEntry(
                name=name,
                rank=rank,
                percent=percent,
                avg_copies=avg_copies,
            )
        )

    return meta


def save_meta_to_cache(
    conn: sqlite3.Connection, meta: list[MetaEntry], format_name: str
) -> None:
    c = conn.cursor()

    # Clear old format meta before inserting new one
    c.execute(
        """
        DELETE FROM meta
        WHERE format = ?
        """,
        (format_name,),
    )

    for entry in meta:
        c.execute(
            """
            INSERT INTO meta (name, format, rank, percent, avg_copies)
            VALUES (?, ?, ?, ?, ?)
        """,
            (
                entry.name,
                format_name,
                entry.rank,
                entry.percent,
                entry.avg_copies,
            ),
        )
