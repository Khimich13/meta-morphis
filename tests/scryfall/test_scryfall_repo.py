import json
import sqlite3
import time

import pytest
from pytest import MonkeyPatch

from meta_morphis import config
from meta_morphis.models.card import Card
from meta_morphis.scryfall.repo import (
    add_alias,
    answers_another_cached_card,
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
    conn: sqlite3.Connection, caplog: pytest.LogCaptureFixture
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

    assert "already belongs to another card" in caplog.text

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

# Written by a clock that ran ahead - must not extend the cooldown
def test_should_skip_lookup_future_attempt(conn: sqlite3.Connection) -> None:
    future = int(time.time()) + 3600

    conn.execute("""
        INSERT INTO card_lookup_failures (name, last_attempt)
        VALUES (?, ?)
    """, (normalize_name("BadName"), future))

    assert should_skip_lookup(conn, "BadName", cooldown=999999) is False

# The default used to be bound at import time, so patching config did nothing
def test_should_skip_lookup_default_cooldown_follows_config(conn: sqlite3.Connection, monkeypatch: MonkeyPatch) -> None:
    old = int(time.time()) - 100

    conn.execute("""
        INSERT INTO card_lookup_failures (name, last_attempt)
        VALUES (?, ?)
    """, (normalize_name("BadName"), old))

    monkeypatch.setattr(config, "SCRYFALL_BAD_NAMES_LOOKUP_COOLDOWN", 10)

    assert should_skip_lookup(conn, "BadName") is False

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

# A corrupt JSON blob is treated as a cache miss (so the card gets re-fetched)
# rather than crashing every lookup that hits it
def test_get_card_from_cache_corrupt_json_is_a_miss(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO cards VALUES (?, ?, ?, ?)", ("2", "shock", "{not json", int(time.time())))
    conn.execute("INSERT INTO card_aliases (alias, card_name) VALUES (?, ?)", ("shock", "shock"))

    assert get_card_from_cache(conn, "Shock") is None

# Same for valid JSON that lacks a field Card.from_raw needs - here a face
# without type_line - instead of the KeyError ending the whole export
def test_get_card_from_cache_missing_field_is_a_miss(conn: sqlite3.Connection) -> None:
    key = normalize_name("Delver of Secrets // Insectile Aberration")
    raw = {
        "id": "3",
        "name": "Delver of Secrets // Insectile Aberration",
        "card_faces": [
            {"name": "Delver of Secrets"},
            {"name": "Insectile Aberration", "type_line": "Creature — Human Insect"},
        ],
    }
    conn.execute("INSERT INTO cards VALUES (?, ?, ?, ?)", ("3", key, json.dumps(raw), int(time.time())))
    conn.execute("INSERT INTO card_aliases (alias, card_name) VALUES (?, ?)", (key, key))

    assert get_card_from_cache(conn, "Delver of Secrets // Insectile Aberration") is None

# And for valid JSON of the wrong shape - a row that is `null` or a list,
# or a card whose card_faces is null - which fails in from_raw with
# TypeError or AttributeError rather than KeyError
@pytest.mark.parametrize("blob", [
    "null",
    "[]",
    json.dumps({"id": "4", "name": "Shock", "card_faces": None}),
    json.dumps({"id": "4", "name": "Shock", "card_faces": ["Shock"]}),
])
def test_get_card_from_cache_wrong_shape_is_a_miss(conn: sqlite3.Connection, blob: str) -> None:
    conn.execute("INSERT INTO cards VALUES (?, ?, ?, ?)", ("4", "shock", blob, int(time.time())))
    conn.execute("INSERT INTO card_aliases (alias, card_name) VALUES (?, ?)", ("shock", "shock"))

    assert get_card_from_cache(conn, "Shock") is None

# A reversible card has no oracle_id at the top level, only on its faces.
# A renamed one used to look like a different card: the old row was kept,
# and its name was refused, so the stale row was fetched again after
# every cooldown. The face's oracle_id identifies it, on either side.
@pytest.mark.parametrize("old_reversible, new_reversible", [
    (True, False), (False, True), (True, True),
])
def test_a_renamed_reversible_card_is_not_another_card(
    conn: sqlite3.Connection, old_reversible: bool, new_reversible: bool
) -> None:
    def raw(card_id: str, name: str, reversible: bool) -> dict[str, object]:
        if not reversible:
            return {"id": card_id, "oracle_id": "o1", "name": name}
        return {
            "id": card_id, "name": f"{name} // {name}", "layout": "reversible_card",
            "card_faces": [
                {"oracle_id": "o1", "name": name, "type_line": "Instant"},
                {"oracle_id": "o1", "name": name, "type_line": "Instant"},
            ],
        }
    old = Card.from_raw(raw("1", "Old", old_reversible))
    new = Card.from_raw(raw("2", "New", new_reversible))
    save_cards_to_cache(conn, [old, new])

    assert not answers_another_cached_card(conn, old.name, new)
    add_alias(conn, old.name, new.name)

    found = get_card_from_cache(conn, old.name)
    assert found is not None and found.name == new.name
    assert conn.execute(
        "SELECT 1 FROM cards WHERE name = ?", (normalize_name(old.name),)
    ).fetchone() is None
