def init_db(conn):
    c = conn.cursor()

    # Create Scryfall card cache table
    c.execute("""
        CREATE TABLE IF NOT EXISTS cards (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            json TEXT NOT NULL,
            updated_at INTEGER NOT NULL
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
        CREATE TABLE IF NOT EXISTS meta_cards (
            name TEXT NOT NULL,
            format TEXT NOT NULL,
            rank INTEGER,
            percent REAL,
            deck_count FLOAT,
            PRIMARY KEY (name, format)
        )
    """)

    conn.commit()
