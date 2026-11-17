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

    assert tables == {"meta_refresh", "meta"}


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
        "INSERT INTO meta (name, format) VALUES (?, ?)", ("Lightning Bolt", "modern")
    )
    conn.commit()

    # Calling init_db again on an already-versioned connection must not
    # error, and must not touch existing data - this is the normal path
    # every real run takes, since get_connection() never checks whether
    # init_db has already run.
    init_db(conn)

    version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == SCHEMA_VERSION
    assert conn.execute("SELECT name FROM meta").fetchall() == [("Lightning Bolt",)]


def test_init_db_refuses_a_newer_schema_version() -> None:
    # Regression guard for the actual point of this mechanism: running
    # older code against a database a newer version already migrated
    # must fail loudly, not silently operate against an unknown shape.
    conn = sqlite3.connect(":memory:")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")

    with pytest.raises(RuntimeError):
        init_db(conn)


def test_init_db_upgrades_a_version_1_database() -> None:
    # A database made before chosen_printings existed goes through every
    # step: the table is made, then dropped with the other Scryfall tables
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE cards (
            id TEXT NOT NULL UNIQUE, name TEXT PRIMARY KEY,
            json TEXT NOT NULL, updated_at INTEGER NOT NULL
        )
    """)
    conn.execute("INSERT INTO cards VALUES ('1', 'lightning bolt', '{}', 0)")
    # Every version 1 database has this table, and version 3 changes it
    conn.execute("CREATE TABLE meta (name TEXT, format TEXT, lookup_name TEXT)")
    conn.execute("PRAGMA user_version = 1")

    init_db(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
    assert "cards" not in tables
    assert "chosen_printings" not in tables


def test_init_db_upgrades_a_version_2_database() -> None:
    # A database whose meta table still has lookup_name keeps its rows
    # and loses the column
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE meta (
            name TEXT NOT NULL, format TEXT NOT NULL, rank INTEGER,
            percent REAL, avg_copies FLOAT, lookup_name TEXT,
            PRIMARY KEY (format, name)
        )
    """)
    conn.execute(
        "INSERT INTO meta VALUES ('Wear // Tear', 'modern', 1, 10.0, 1.5, 'Wear')"
    )
    conn.execute("PRAGMA user_version = 2")

    init_db(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    columns = [row[1] for row in conn.execute("PRAGMA table_info(meta)")]
    assert columns == ["name", "format", "rank", "percent", "avg_copies"]
    assert conn.execute("SELECT name FROM meta").fetchall() == [("Wear // Tear",)]


def test_init_db_upgrades_a_version_3_database() -> None:
    # The Scryfall tables go - its card data now comes from its daily
    # file - and the MTGGoldfish lists stay
    conn = sqlite3.connect(":memory:")
    version_3 = """
        CREATE TABLE cards (
            id TEXT, name TEXT UNIQUE NOT NULL,
            json TEXT NOT NULL, updated_at INTEGER NOT NULL
        );
        CREATE TABLE card_aliases (
            alias TEXT PRIMARY KEY,
            card_name TEXT NOT NULL REFERENCES cards(name)
        );
        CREATE TABLE card_lookup_failures (
            name TEXT PRIMARY KEY, last_attempt INTEGER NOT NULL
        );
        CREATE TABLE chosen_printings (
            oracle_id TEXT PRIMARY KEY,
            json TEXT NOT NULL, updated_at INTEGER NOT NULL
        );
        CREATE TABLE meta_refresh (
            format TEXT PRIMARY KEY, last_updated INTEGER NOT NULL
        );
        CREATE TABLE meta (
            name TEXT NOT NULL, format TEXT NOT NULL, rank INTEGER,
            percent REAL, avg_copies FLOAT, PRIMARY KEY (format, name)
        );
        INSERT INTO cards VALUES ('1', 'lightning bolt', '{}', 0);
        INSERT INTO card_aliases VALUES ('lightning bolt', 'lightning bolt');
        INSERT INTO meta VALUES ('Lightning Bolt', 'modern', 1, 10.0, 4.0);
        PRAGMA user_version = 3;
    """
    conn.executescript(version_3)

    init_db(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert tables == {"meta_refresh", "meta"}
    assert conn.execute("SELECT name FROM meta").fetchall() == [("Lightning Bolt",)]
