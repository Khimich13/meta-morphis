import sqlite3
from typing import Any

import pytest
from pytest import MonkeyPatch

from meta_morphis import config
from meta_morphis.models.card import Card
from meta_morphis.scryfall.repo import get_chosen_printing, save_chosen_printing
from meta_morphis.scryfall.service import get_display_printings
from meta_morphis.utils.http import RequestUnavailable


def _raw(
    printing_id: str,
    artwork: str = "art-1",
    released: str = "2020-01-01",
    oracle_id: str = "oid",
) -> dict[str, Any]:
    return {
        "id": printing_id,
        "oracle_id": oracle_id,
        "name": "Lightning Bolt",
        "released_at": released,
        "illustration_id": artwork,
        "artist": "Some Artist",
        "games": ["paper"],
        "image_uris": {"grid": f"{printing_id}.webp", "art": f"{printing_id}-art.webp"},
    }

DEFAULT = Card.from_raw(_raw("default"))

def _shown(conn: sqlite3.Connection, *cards: Card) -> list[str]:
    return [card.id for card in get_display_printings(conn, list(cards))]

def _searches(monkeypatch: MonkeyPatch, printings: list[dict[str, Any]]) -> list[list[str]]:
    """Scryfall answers every search with `printings`; returns the searches made"""
    asked: list[list[str]] = []

    def search(oracle_ids: list[str]) -> list[dict[str, Any]]:
        asked.append(oracle_ids)
        return [p for p in printings if p["oracle_id"] in oracle_ids]

    monkeypatch.setattr("meta_morphis.scryfall.service.search_printings", search)
    return asked

def test_chosen_printing_round_trip(conn: sqlite3.Connection) -> None:
    assert get_chosen_printing(conn, "oid") is None
    save_chosen_printing(conn, "oid", _raw("m10"))

    cached = get_chosen_printing(conn, "oid")
    assert cached is not None
    assert cached.id == "m10"
    assert cached.age < 5

def test_searches_and_saves_the_choice(conn: sqlite3.Connection, monkeypatch: MonkeyPatch) -> None:
    _searches(monkeypatch, [
        _raw("lea", "rush", "1993-08-05"),
        _raw("m10", "moeller", "2009-07-17"),
        _raw("m11", "moeller", "2010-07-16"),
    ])

    # Moeller's art is on two printings; m11 is the newer of them
    assert _shown(conn, DEFAULT) == ["m11"]
    saved = get_chosen_printing(conn, "oid")
    assert saved is not None and saved.id == "m11"

def test_cards_are_searched_in_groups_and_sorted_back(
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "SCRYFALL_PRINTINGS_PER_SEARCH", 2)
    cards = [Card.from_raw(_raw(f"default-{n}", oracle_id=f"card-{n}")) for n in range(5)]
    asked = _searches(monkeypatch, [_raw(f"chosen-{n}", oracle_id=f"card-{n}") for n in range(5)])

    assert _shown(conn, *cards) == [f"chosen-{n}" for n in range(5)]
    assert asked == [["card-0", "card-1"], ["card-2", "card-3"], ["card-4"]]

def test_a_fresh_choice_is_used_without_searching(
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch
) -> None:
    save_chosen_printing(conn, "oid", _raw("m10"))
    asked = _searches(monkeypatch, [])

    assert _shown(conn, DEFAULT) == ["m10"]
    assert asked == []

def test_an_old_choice_is_searched_again(
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch
) -> None:
    save_chosen_printing(conn, "oid", _raw("m10"))
    conn.execute(
        "UPDATE chosen_printings SET updated_at = updated_at - ?",
        (config.SCRYFALL_REFRESH_RATE + 10,),
    )
    _searches(monkeypatch, [_raw("2xm")])

    assert _shown(conn, DEFAULT) == ["2xm"]

@pytest.mark.parametrize("saved", [True, False])
def test_unreachable_scryfall_falls_back(
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch, saved: bool
) -> None:
    if saved:
        save_chosen_printing(conn, "oid", _raw("m10"))
        conn.execute(
            "UPDATE chosen_printings SET updated_at = updated_at - ?",
            (config.SCRYFALL_REFRESH_RATE + 10,),
        )

    def unreachable(oracle_ids: list[str]) -> None:
        raise RequestUnavailable("down")

    monkeypatch.setattr("meta_morphis.scryfall.service.search_printings", unreachable)

    # The old choice if there is one, otherwise the card as it came
    assert _shown(conn, DEFAULT) == ["m10" if saved else "default"]

def test_no_regular_printing_keeps_the_card(
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch
) -> None:
    _searches(monkeypatch, [])
    assert _shown(conn, DEFAULT) == ["default"]

def test_a_card_without_oracle_id_is_kept(conn: sqlite3.Connection) -> None:
    card = Card.from_raw({"id": "x", "name": "Odd"})
    assert get_display_printings(conn, [card]) == [card]

def test_a_card_listed_twice_is_searched_once(
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch
) -> None:
    asked = _searches(monkeypatch, [_raw("m10")])
    assert _shown(conn, DEFAULT, DEFAULT) == ["m10", "m10"]
    assert asked == [["oid"]]
