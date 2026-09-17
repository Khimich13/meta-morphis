import sqlite3
from contextlib import contextmanager
from typing import Generator

from meta_morphis import config


@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    db_path = config.DB_PATH

    conn = sqlite3.connect(str(db_path))
    try:
        yield conn
    finally:
        conn.close()