import sqlite3


def init_db(conn: sqlite3.Connection) -> None:
    c = conn.cursor()

    # Enable WAL mode for better concurrency and safer writes
    c.execute("PRAGMA journal_mode=WAL;")
    
    # Create Scryfall card cache table
    c.execute("""
        CREATE TABLE IF NOT EXISTS cards (
            id TEXT,
            name TEXT UNIQUE NOT NULL,
            json TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        )
    """)

    # Create cards lookup table
    c.execute("""
        CREATE TABLE IF NOT EXISTS card_aliases (
            alias TEXT PRIMARY KEY,
            card_name TEXT NOT NULL REFERENCES cards(name)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS card_lookup_failures (
            name TEXT PRIMARY KEY,
            last_attempt INTEGER
        )
    """)

    # Create Goldfish meta refresh timestamp table
    c.execute("""
        CREATE TABLE IF NOT EXISTS meta_refresh (
            format TEXT PRIMARY KEY,
            last_updated INTEGER NOT NULL
        )
    """)

    # Create Goldfish meta card list table
    c.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            name TEXT NOT NULL,
            format TEXT NOT NULL,
            rank INTEGER,
            percent REAL,
            avg_copies FLOAT,
            lookup_name TEXT,
            PRIMARY KEY (name, format)
        )
    """)

    conn.commit()