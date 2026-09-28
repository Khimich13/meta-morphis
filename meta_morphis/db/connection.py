import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from meta_morphis import config


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    db_path = config.DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()