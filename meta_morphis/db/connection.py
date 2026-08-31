import sqlite3
from pathlib import Path

import config


def get_connection() -> sqlite3.Connection:
    db_path = Path(config.DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(config.DB_PATH)