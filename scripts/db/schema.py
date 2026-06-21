import sqlite3
import os

def init_db():
    db_path = "cards.db"
    schema_path = os.path.join(os.path.dirname(__file__),"schema.sql")

    conn = sqlite3.connect(db_path)
    with open(schema_path, "r") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()