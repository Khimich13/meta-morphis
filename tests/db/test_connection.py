import sqlite3
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from meta_morphis.db.connection import get_connection
from meta_morphis.db.init_db import init_db


def test_get_connection_creates_missing_parent_directory(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    db_path = tmp_path / "nested" / "does" / "not" / "exist" / "cards.db"
    monkeypatch.setattr("meta_morphis.db.connection.config.DB_PATH", db_path)

    assert not db_path.parent.exists()

    with get_connection() as conn:
        assert isinstance(conn, sqlite3.Connection)
        conn.execute("SELECT 1")

    assert db_path.parent.exists()
    assert db_path.exists()

def test_get_connection_enforces_foreign_keys(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    # Regression test for H5: PRAGMA foreign_keys is per-connection and
    # defaults OFF, and unlike journal_mode it does NOT persist in the
    # database file - so it must be enabled on every connection, not just
    # once via init_db. Without it, card_aliases.card_name REFERENCES
    # cards(name) is decorative and a dangling alias is accepted silently.
    db_path = tmp_path / "cards.db"
    monkeypatch.setattr("meta_morphis.db.connection.config.DB_PATH", db_path)

    with get_connection() as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1

        init_db(conn)

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO card_aliases (alias, card_name) VALUES (?, ?)",
                ("ghost", "no-such-card"),
            )
