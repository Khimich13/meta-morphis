import sqlite3
from pathlib import Path

from pytest import MonkeyPatch

from meta_morphis.db.connection import get_connection


def test_get_connection_creates_missing_parent_directory(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    # Regression test for H1: a fresh clone has no data/ directory (it's
    # gitignored), and get_connection used to call sqlite3.connect directly
    # without ensuring the parent directory exists first, raising
    # "OperationalError: unable to open database file".
    db_path = tmp_path / "nested" / "does" / "not" / "exist" / "cards.db"
    monkeypatch.setattr("meta_morphis.db.connection.config.DB_PATH", db_path)

    assert not db_path.parent.exists()

    with get_connection() as conn:
        assert isinstance(conn, sqlite3.Connection)
        conn.execute("SELECT 1")

    assert db_path.parent.exists()
    assert db_path.exists()
