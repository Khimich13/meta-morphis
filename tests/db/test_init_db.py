import sqlite3
from pathlib import Path

import pytest

from meta_morphis.db.init_db import SCHEMA_VERSION, init_db


def test_init_db_stamps_a_fresh_database_with_the_current_version() -> None:
    conn = sqlite3.connect(":memory:")
    init_db(conn)

    version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == SCHEMA_VERSION

def test_init_db_creates_all_expected_tables() -> None:
    conn = sqlite3.connect(":memory:")
    init_db(conn)

    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }

    assert tables == {
        "cards",
        "card_aliases",
        "card_lookup_failures",
        "meta_refresh",
        "meta",
    }

# Uses a file - an in-memory database can't be put in WAL mode at all.
# The mode is stored in the file itself, so a fresh connection sees it.
def test_init_db_enables_wal(db_file: Path) -> None:
    conn = sqlite3.connect(db_file)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()

    assert mode == "wal"

def test_init_db_is_idempotent() -> None:
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    conn.execute(
        "INSERT INTO cards (id, name, json, updated_at) VALUES (?, ?, ?, ?)",
        ("1", "lightning bolt", "{}", 0),
    )
    conn.commit()

    # Calling init_db again on an already-versioned connection must not
    # error, and must not touch existing data - this is the normal path
    # every real run takes, since get_connection() never checks whether
    # init_db has already run.
    init_db(conn)

    version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == SCHEMA_VERSION
    assert conn.execute("SELECT name FROM cards").fetchall() == [("lightning bolt",)]

def test_init_db_refuses_a_newer_schema_version() -> None:
    # Regression guard for the actual point of this mechanism: running
    # older code against a database a newer version already migrated
    # must fail loudly, not silently operate against an unknown shape.
    conn = sqlite3.connect(":memory:")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")

    with pytest.raises(RuntimeError):
        init_db(conn)
