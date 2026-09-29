import json
import sqlite3
import time

import pytest

from meta_morphis.models.card import Card
from meta_morphis.scryfall.repo import (
    get_card_from_cache,
    record_bad_name_attempt,
    save_cards_to_cache,
    should_skip_lookup,
)
from meta_morphis.utils.text import normalize_name


@pytest.fixture
def conn(conn: sqlite3.Connection) -> sqlite3.Connection:
    # Overrides the shared `conn` fixture from conftest.py for this module:
    # same empty database, plus one old cached card to test against.
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

    assert card is not None

    assert card.raw == {
        "id": "1",
        "name": "Sai, Master Thopterist",
        "mana_cost": "2U",
        "type_line": "Legendary Creature — Human Artificer"
    }

    assert get_card_from_cache(conn, "Unknown") is None

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
    assert card is not None
    assert card.raw == {
        "id": "2",
        "name": "Shock",
        "mana_cost": "R",
        "type_line": "Instant"
    }

    card = get_card_from_cache(conn, "Counterspell")
    assert card is not None
    assert card.raw == {
        "id": "3",
        "name": "Counterspell",
        "mana_cost": "UU",
        "type_line": "Instant"
    }

def test_save_cards_to_cache_face_alias_first_claim_wins(
    conn: sqlite3.Connection, capsys: pytest.CaptureFixture[str]
) -> None:
    # "Fire" is a real face name shared by two
    # distinct real cards, Fire // Ice and Start // Fire. INSERT OR
    # REPLACE used to let whichever card was cached most recently
    # silently steal the alias, so a lookup could flip to a different
    # card with no error depending purely on fetch order.
    fire_ice = Card.from_raw({
        "id": "fi", "name": "Fire // Ice", "type_line": "Instant",
        "card_faces": [
            {"name": "Fire", "mana_cost": "1R", "type_line": "Instant"},
            {"name": "Ice", "mana_cost": "1U", "type_line": "Instant"},
        ],
    })
    start_fire = Card.from_raw({
        "id": "sf", "name": "Start // Fire", "type_line": "Sorcery",
        "card_faces": [
            {"name": "Start", "mana_cost": "2W", "type_line": "Sorcery"},
            {"name": "Fire", "mana_cost": "2R", "type_line": "Sorcery"},
        ],
    })

    save_cards_to_cache(conn, [fire_ice])
    save_cards_to_cache(conn, [start_fire])

    card = get_card_from_cache(conn, "Fire")
    assert card is not None
    assert card.name == "Fire // Ice"

    captured = capsys.readouterr()
    assert "already belongs to another card" in captured.out

    # Both cards remain independently reachable by their own canonical
    # names and their unambiguous face names.
    for lookup, expected_name in [
        ("Fire // Ice", "Fire // Ice"),
        ("Start // Fire", "Start // Fire"),
        ("Ice", "Fire // Ice"),
        ("Start", "Start // Fire"),
    ]:
        found = get_card_from_cache(conn, lookup)
        assert found is not None
        assert found.name == expected_name

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