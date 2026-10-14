import sqlite3

# Bump this whenever the schema changes, and add a `if current_version < N:`
# block below with the migration steps. CREATE TABLE IF NOT EXISTS alone
# can't detect an existing table whose columns have drifted from what the
# code now expects - this guard makes that drift loud instead of silent.
SCHEMA_VERSION = 2


def init_db(conn: sqlite3.Connection) -> None:
    c = conn.cursor()

    # Enable WAL mode for better concurrency and safer writes
    c.execute("PRAGMA journal_mode=WAL;")

    current_version: int = c.execute("PRAGMA user_version").fetchone()[0]

    if current_version > SCHEMA_VERSION:
        raise RuntimeError(
            f"Database is at schema version {current_version}, but this "
            f"build only understands up to version {SCHEMA_VERSION}. "
            f"Refusing to run against a newer schema - update the app."
        )

    if current_version < 1:
        _migrate_to_v1(c)
        current_version = 1

    if current_version < 2:
        _migrate_to_v2(c)
        current_version = 2

    # Next schema change adds a block here, e.g.:
    # if current_version < 3:
    #     _migrate_to_v3(c)
    #     current_version = 3

    c.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()

def _migrate_to_v1(c: sqlite3.Cursor) -> None:
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

    # Create failed cards lookup table
    c.execute("""
        CREATE TABLE IF NOT EXISTS card_lookup_failures (
            name TEXT PRIMARY KEY,
            last_attempt INTEGER NOT NULL
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
            PRIMARY KEY (format, name)
        )
    """)

def _migrate_to_v2(c: sqlite3.Cursor) -> None:
    # The printing chosen to show for each card (see scryfall/artwork.py),
    # as Scryfall's JSON for that printing
    c.execute("""
        CREATE TABLE IF NOT EXISTS chosen_printings (
            oracle_id TEXT PRIMARY KEY,
            json TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        )
    """)
