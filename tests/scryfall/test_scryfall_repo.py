import json
import sqlite3
import time

import pytest

from meta_morphis.db.init_db import init_db
from meta_morphis.models.card import Card
from meta_morphis.scryfall.repo import (
    get_card_from_cache,
    record_bad_name_attempt,
    save_cards_to_cache,
    should_skip_lookup,
)
from meta_morphis.utils.text import normalize_name


@pytest.fixture
def conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    conn.execute(
        "INSERT INTO cards VALUES (?, ?, ?, ?)", (
            "1",
            normalize_name("Sai, Master Thopterist"),
            json.dumps({
                "id": "1",
                "name": "Sai, Master Thopterist",
                "mana_cost": "2U",
                "type_line": "Legendary Creature — Human Artificer"
            }),
            # make it old
            int(time.time()) - 999999
        )
    )

    conn.execute("""
        INSERT INTO card_aliases (alias, card_name)
        VALUES (?, ?)
    """, (normalize_name("Sai, Master Thopterist"), normalize_name("Sai, Master Thopterist")))

    return conn

def test_get_card_from_cache(conn: sqlite3.Connection) -> None:
    card = get_card_from_cache(conn, "Sai, Master Thopterist")

    assert card != None

    assert card.raw == {
        "id": "1",
        "name": "Sai, Master Thopterist",
        "mana_cost": "2U",
        "type_line": "Legendary Creature — Human Artificer"
    }

    assert get_card_from_cache(conn, "Unknown") == None
    
def test_save_cards_to_cache(conn: sqlite3.Connection) -> None:
    new_card_1 = {
        "id": "2",
        "name": "Shock",
        "mana_cost": "R",
        "type_line": "Instant"
    }

    new_card_2 = {
        "id": "3",
        "name": "Counterspell",
        "mana_cost": "UU",
        "type_line": "Instant"
    }
    save_cards_to_cache(conn, [Card.from_raw(new_card_1), Card.from_raw(new_card_2)])

    card = get_card_from_cache(conn, "Shock")
    assert card != None
    assert card.raw == {
        "id": "2",
        "name": "Shock",
        "mana_cost": "R",
        "type_line": "Instant"
    }

    card = get_card_from_cache(conn, "Counterspell")
    assert card != None
    assert card.raw == {
        "id": "3",
        "name": "Counterspell",
        "mana_cost": "UU",
        "type_line": "Instant"
    }

def test_save_cards_to_cache_reprint(conn: sqlite3.Connection) -> None:
    reprint = {
        "id": "2",
        "name": "Sai, Master Thopterist",
        "mana_cost": "2U",
        "type_line": "Legendary Creature — Human Artificer"
    }
    save_cards_to_cache(conn, [Card.from_raw(reprint)])

    cards_with_same_name = conn.execute(
        "SELECT * FROM cards WHERE name = ?", (normalize_name("Sai, Master Thopterist"),)
    ).fetchall()
    
    assert len(cards_with_same_name) == 1

    # id column itself was updated, not just the json blob
    assert cards_with_same_name[0][0] == "2"  

    card = get_card_from_cache(conn, "Sai, Master Thopterist")

    assert card is not None
    assert card.id == "2"
    assert card.raw["id"] == "2"

def test_save_cards_to_cache_updated_at(conn: sqlite3.Connection) -> None:
    old_card = get_card_from_cache(conn, "Sai, Master Thopterist")
    assert old_card is not None
    old_card_age = old_card.age
    new_version_card = {
        "id": "2",
        "name": "Sai, Master Thopterist",
        "mana_cost": "2U",
        "type_line": "Legendary Creature — Human Artificer"
    }
    save_cards_to_cache(conn, [Card.from_raw(new_version_card)])
    new_card = get_card_from_cache(conn, "Sai, Master Thopterist")
    assert new_card is not None
    new_card_age = new_card.age

    assert new_card_age < old_card_age

def test_record_bad_name_attempt_inserts(conn: sqlite3.Connection) -> None:
    record_bad_name_attempt(conn, "BadName")

    row = conn.execute("""
        SELECT name, last_attempt
        FROM card_lookup_failures
        WHERE name = ?
    """, (normalize_name("BadName"),)).fetchone()

    assert row is not None
    assert row[0] == normalize_name("BadName")
    assert isinstance(row[1], int)

def test_should_skip_lookup_empty(conn: sqlite3.Connection) -> None:
    assert should_skip_lookup(conn, "Unknown") is False

def test_should_skip_lookup_within_cooldown(conn: sqlite3.Connection) -> None:
    now = int(time.time())

    conn.execute("""
        INSERT INTO card_lookup_failures (name, last_attempt)
        VALUES (?, ?)
    """, (normalize_name("BadName"), now))

    assert should_skip_lookup(conn, "BadName", cooldown=999999) is True

def test_should_skip_lookup_after_cooldown(conn: sqlite3.Connection) -> None:
    old = int(time.time()) - 999999

    conn.execute("""
        INSERT INTO card_lookup_failures (name, last_attempt)
        VALUES (?, ?)
    """, (normalize_name("BadName"), old))

    assert should_skip_lookup(conn, "BadName", cooldown=10) is False

def test_record_bad_name_attempt_updates(conn: sqlite3.Connection) -> None:
    old = int(time.time()) - 999999

    key = normalize_name("BadName")

    conn.execute("""
        INSERT INTO card_lookup_failures (name, last_attempt)
        VALUES (?, ?)
    """, (key, old))

    record_bad_name_attempt(conn, "BadName")

    new_row = conn.execute("""
        SELECT last_attempt
        FROM card_lookup_failures
        WHERE name = ?
    """, (key,)).fetchone()

    assert new_row[0] > old