import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import config


@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    db_path = Path(config.DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    try:
        yield conn
    finally:
        conn.close()