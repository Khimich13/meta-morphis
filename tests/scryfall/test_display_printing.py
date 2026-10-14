import sqlite3
from typing import Any

import pytest
from pytest import MonkeyPatch

from meta_morphis import config
from meta_morphis.models.card import Card
from meta_morphis.scryfall.repo import get_chosen_printing, save_chosen_printing
from meta_morphis.scryfall.service import get_display_printing
from meta_morphis.utils.http import RequestUnavailable


def _raw(printing_id: str, artwork: str = "art-1", released: str = "2020-01-01") -> dict[str, Any]:
    return {
        "id": printing_id,
        "oracle_id": "oid",
        "name": "Lightning Bolt",
        "released_at": released,
        "illustration_id": artwork,
        "artist": "Some Artist",
        "image_uris": {"grid": f"{printing_id}.webp", "art": f"{printing_id}-art.webp"},
    }

DEFAULT = Card.from_raw(_raw("default"))

def test_chosen_printing_round_trip(conn: sqlite3.Connection) -> None:
    assert get_chosen_printing(conn, "oid") is None
    save_chosen_printing(conn, "oid", _raw("m10"))

    cached = get_chosen_printing(conn, "oid")
    assert cached is not None
    assert cached.id == "m10"
    assert cached.age < 5

def test_searches_and_saves_the_choice(conn: sqlite3.Connection, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "meta_morphis.scryfall.service.search_printings",
        lambda oracle_id: [
            _raw("lea", "rush", "1993-08-05"),
            _raw("m10", "moeller", "2009-07-17"),
            _raw("m11", "moeller", "2010-07-16"),
        ],
    )

    # Moeller's art is on two printings; m11 is the newer of them
    assert get_display_printing(conn, DEFAULT).id == "m11"
    saved = get_chosen_printing(conn, "oid")
    assert saved is not None and saved.id == "m11"

def test_a_fresh_choice_is_used_without_searching(
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch
) -> None:
    save_chosen_printing(conn, "oid", _raw("m10"))

    def must_not_search(oracle_id: str) -> None:
        raise AssertionError("searched although the saved choice is fresh")

    monkeypatch.setattr("meta_morphis.scryfall.service.search_printings", must_not_search)

    assert get_display_printing(conn, DEFAULT).id == "m10"

def test_an_old_choice_is_searched_again(
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch
) -> None:
    save_chosen_printing(conn, "oid", _raw("m10"))
    conn.execute(
        "UPDATE chosen_printings SET updated_at = updated_at - ?",
        (config.SCRYFALL_REFRESH_RATE + 10,),
    )
    monkeypatch.setattr(
        "meta_morphis.scryfall.service.search_printings", lambda oracle_id: [_raw("2xm")]
    )

    assert get_display_printing(conn, DEFAULT).id == "2xm"

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

    def unreachable(oracle_id: str) -> None:
        raise RequestUnavailable("down")

    monkeypatch.setattr("meta_morphis.scryfall.service.search_printings", unreachable)

    # The old choice if there is one, otherwise the card as it came
    assert get_display_printing(conn, DEFAULT).id == ("m10" if saved else "default")

def test_no_regular_printing_keeps_the_card(
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr("meta_morphis.scryfall.service.search_printings", lambda oracle_id: None)
    assert get_display_printing(conn, DEFAULT).id == "default"

def test_a_card_without_oracle_id_is_kept(conn: sqlite3.Connection) -> None:
    card = Card.from_raw({"id": "x", "name": "Odd"})
    assert get_display_printing(conn, card) is card
