import sqlite3
import config

def get_connection() -> sqlite3.Connection:
    return sqlite3.connect(config.DB_PATH)