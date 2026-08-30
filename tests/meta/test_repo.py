import sqlite3
import time

import pytest

import config
from meta_morphis.meta.repo import (
    load_cached_meta,
    save_meta_to_cache,
    should_refresh_meta,
    update_meta_timestamp,
)
from meta_morphis.models.meta import MetaEntry


@pytest.fixture
def conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE meta_refresh (
            format TEXT PRIMARY KEY,
            last_updated INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE meta (
            name TEXT,
            format TEXT,
            rank INTEGER,
            percent REAL,
            deck_count REAL,
            lookup_name TEXT NULL
        )
    """)
    return conn

def test_should_refresh_meta_no_row(conn: sqlite3.Connection) -> None:
    assert should_refresh_meta(conn, "pauper") is True

def test_should_refresh_meta_old(conn: sqlite3.Connection) -> None:
    old_time = int(time.time()) - (config.META_REFRESH_RATE + 10)

    conn.execute(
        "INSERT INTO meta_refresh VALUES (?, ?)",
        ("pauper", old_time)
    )

    assert should_refresh_meta(conn, "pauper") is True

def test_should_refresh_meta_fresh(conn: sqlite3.Connection) -> None:
    fresh_time = int(time.time())

    conn.execute(
        "INSERT INTO meta_refresh VALUES (?, ?)",
        ("pauper", fresh_time)
    )

    assert should_refresh_meta(conn, "pauper") is False

def test_update_meta_timestamp_insert(conn: sqlite3.Connection) -> None:
    update_meta_timestamp(conn, "pauper")

    row = conn.execute(
        "SELECT last_updated FROM meta_refresh WHERE format = ?",
        ("pauper",)
    ).fetchone()

    assert row is not None
    assert isinstance(row[0], int)

def test_update_meta_timestamp_update(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO meta_refresh VALUES (?, ?)",
        ("pauper", 123)
    )

    update_meta_timestamp(conn, "pauper")

    row = conn.execute(
        "SELECT last_updated FROM meta_refresh WHERE format = ?",
        ("pauper",)
    ).fetchone()

    assert row[0] != 123

def test_load_cached_meta(conn: sqlite3.Connection) -> None:
    conn.execute("""
        INSERT INTO meta VALUES ('Bolt', 'pauper', 1, 25.0, 1, NULL)
    """)

    result = load_cached_meta(conn, "pauper")

    assert len(result) == 1
    assert isinstance(result[0], MetaEntry)
    assert result[0].name == "Bolt"

def test_save_meta_to_cache(conn: sqlite3.Connection) -> None:
    # old data
    conn.execute("""
        INSERT INTO meta VALUES ('OldCard', 'pauper', 99, 1.0, 1, NULL)
    """)

    meta = [
        MetaEntry("Bolt", 1, 25.0, 1),
        MetaEntry("Brainstorm", 2, 20.0, 2),
    ]

    save_meta_to_cache(conn, meta, "pauper")

    rows = conn.execute(
        "SELECT name, rank FROM meta WHERE format = ? ORDER BY rank ASC",
        ("pauper",)
    ).fetchall()

    assert rows == [
        ("Bolt", 1),
        ("Brainstorm", 2),
    ]