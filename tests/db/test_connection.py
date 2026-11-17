import sqlite3
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from meta_morphis.db.connection import get_connection


def test_get_connection_creates_missing_parent_directory(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    db_path = tmp_path / "nested" / "does" / "not" / "exist" / "cards.db"
    monkeypatch.setattr("meta_morphis.db.connection.config.DB_PATH", db_path)

    assert not db_path.parent.exists()

    with get_connection() as conn:
        assert isinstance(conn, sqlite3.Connection)
        conn.execute("SELECT 1")

    assert db_path.parent.exists()
    assert db_path.exists()


def test_get_connection_enforces_foreign_keys(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    db_path = tmp_path / "cards.db"
    monkeypatch.setattr("meta_morphis.db.connection.config.DB_PATH", db_path)

    # No table has a foreign key today; one added later is enforced
    with get_connection() as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1

        conn.execute("CREATE TABLE parent (name TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE child (name TEXT REFERENCES parent(name))")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO child VALUES ('no-such-parent')")
