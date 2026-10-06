import sqlite3
import time

from meta_morphis import config
from meta_morphis.meta.repo import (
    get_meta_from_cache,
    save_meta_to_cache,
    should_refresh_meta,
    update_meta_timestamp,
)
from meta_morphis.models.meta import MetaEntry


def test_should_refresh_meta_no_row(conn: sqlite3.Connection) -> None:
    assert should_refresh_meta(conn, "pauper") is True

def test_should_refresh_meta_old(conn: sqlite3.Connection) -> None:
    old_time = int(time.time()) - (config.GOLDFISH_REFRESH_RATE + 10)

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

# Written by a clock that ran ahead - must not block refreshing until
# real time catches up with it
def test_should_refresh_meta_future_timestamp(conn: sqlite3.Connection) -> None:
    future_time = int(time.time()) + 3600

    conn.execute(
        "INSERT INTO meta_refresh VALUES (?, ?)",
        ("pauper", future_time)
    )

    assert should_refresh_meta(conn, "pauper") is True

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

def test_get_meta_from_cache(conn: sqlite3.Connection) -> None:
    conn.execute("""
        INSERT INTO meta VALUES ('Bolt', 'pauper', 1, 25.0, 1, NULL)
    """)

    result = get_meta_from_cache(conn, "pauper")

    assert len(result) == 1
    assert isinstance(result[0], MetaEntry)
    assert result[0].name == "Bolt"

# SQLite sorts NULL before any number in ascending order
def test_get_meta_from_cache_puts_unranked_last(conn: sqlite3.Connection) -> None:
    conn.execute("""
        INSERT INTO meta VALUES
            ('Unranked', 'pauper', NULL, 5.0, 1, NULL),
            ('Second', 'pauper', 2, 10.0, 1, NULL),
            ('First', 'pauper', 1, 25.0, 1, NULL)
    """)

    result = get_meta_from_cache(conn, "pauper")

    assert [e.name for e in result] == ["First", "Second", "Unranked"]

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

# The DELETE that clears old meta must be scoped to the format being saved
def test_save_meta_to_cache_keeps_other_formats(conn: sqlite3.Connection) -> None:
    save_meta_to_cache(conn, [MetaEntry("Counterspell", 1, 30.0, 4.0)], "modern")
    save_meta_to_cache(conn, [MetaEntry("Lightning Bolt", 1, 25.0, 3.5)], "pauper")

    assert [m.name for m in get_meta_from_cache(conn, "modern")] == ["Counterspell"]

# Every field must survive a save/load round trip, in rank order - including
# lookup_name, which split cards need to hit the Scryfall cache
def test_meta_cache_round_trip(conn: sqlite3.Connection) -> None:
    bolt = MetaEntry("Lightning Bolt", rank=1, percent=25.0, avg_copies=3.5)
    wear_tear = MetaEntry("Wear // Tear", rank=2, percent=10.0, avg_copies=1.5, lookup_name="Wear")

    save_meta_to_cache(conn, [wear_tear, bolt], "pauper")

    assert get_meta_from_cache(conn, "pauper") == [bolt, wear_tear]
