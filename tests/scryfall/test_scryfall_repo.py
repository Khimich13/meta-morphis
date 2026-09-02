import json
import sqlite3
import time

import pytest

from meta_morphis.scryfall.repo import (
    get_card_age,
    get_card_from_cache,
    save_cards_to_cache,
)
from meta_morphis.utils.text import normalize_name


@pytest.fixture
def conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE cards (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            json TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        )
    """)
    conn.execute(
        "INSERT INTO cards VALUES (?, ?, ?, ?)", (
            1,
            normalize_name("Sai, Master Thopterist"),
            json.dumps({
                "id": 1,
                "name": "Sai, Master Thopterist",
                "mana_cost": "2U",
                "type_line": "Legendary Creature — Human Artificer"
            }),
            0.25
        )
    )

    return conn

def test_get_card_from_cache(conn: sqlite3.Connection) -> None:
    
    assert get_card_from_cache(conn, "Sai, Master Thopterist") == {
        "id": 1,
        "name": "Sai, Master Thopterist",
        "mana_cost": "2U",
        "type_line": "Legendary Creature — Human Artificer"
    }

    assert get_card_from_cache(conn, "Unknown") == None

def test_get_card_age(conn: sqlite3.Connection) -> None:

    assert get_card_age(conn, "Sai, Master Thopterist") == int(time.time()) - 0.25

    assert get_card_age(conn, "Unknown") == None
    
def test_save_cards_to_cache(conn: sqlite3.Connection) -> None:
    new_card_1 = {
        "id": 2,
        "name": "Shock",
        "mana_cost": "R",
        "type_line": "Instant"
    }

    new_card_2 = {
        "id": 3,
        "name": "Counterspell",
        "mana_cost": "UU",
        "type_line": "Instant"
    }
    save_cards_to_cache(conn, [new_card_1, new_card_2])

    assert get_card_from_cache(conn, "Shock") == {
        "id": 2,
        "name": "Shock",
        "mana_cost": "R",
        "type_line": "Instant"
    }

    assert get_card_from_cache(conn, "Counterspell") == {
        "id": 3,
        "name": "Counterspell",
        "mana_cost": "UU",
        "type_line": "Instant"
    }

def test_save_cards_to_cache_duplicates(conn: sqlite3.Connection) -> None:
    new_version_card = {
        "id": 2,
        "name": "Sai, Master Thopterist",
        "mana_cost": "2U",
        "type_line": "Legendary Creature — Human Artificer"
    }
    save_cards_to_cache(conn, [new_version_card])

    cards_with_same_name = conn.execute(
        "SELECT * FROM cards WHERE name = ?", (normalize_name("Sai, Master Thopterist"),)
    ).fetchall()
    
    assert len(cards_with_same_name) == 1
    updated_cached_card = cards_with_same_name[0]
    # check if the new card updated the old one by its id
    assert updated_cached_card[0] == 2