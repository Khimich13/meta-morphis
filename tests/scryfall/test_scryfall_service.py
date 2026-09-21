import sqlite3
from typing import Any

import pytest
from pytest import CaptureFixture, MonkeyPatch

from meta_morphis import config
from meta_morphis.models.card import Card
from meta_morphis.models.meta import MetaEntry
from meta_morphis.scryfall.service import (
    _classify_cards,
    _fetch_updates_for_outdated,
    _process_batch_request,
    fetch_cards,
)


def _card(name: str, age: int = 0, card_id: str = "test") -> Card:
    card = Card.from_raw({"id": card_id, "name": name})
    card.age = age
    return card

def test_classify_cards(monkeypatch: MonkeyPatch) -> None:
    conn = sqlite3.connect(":memory:")

    fresh_meta = MetaEntry(
        name= "Duress",
        rank= 10,
        percent= 15,
        avg_copies= 2
    )
    outdated_meta = MetaEntry(
        name= "Counterspell",
        rank= 5,
        percent= 10,
        avg_copies= 3.2
    )
    missing_meta = MetaEntry(
        name= "Llanowar Elf",
        rank= 1,
        percent= 25,
        avg_copies= 3.9
    )

    meta = [fresh_meta, outdated_meta, missing_meta]

    monkeypatch.setattr(
        "meta_morphis.scryfall.service.should_skip_lookup",
        lambda conn, name: None
    )

    monkeypatch.setattr(
        "meta_morphis.scryfall.service.get_card_from_cache",
        lambda conn, name: (
            _card(name, age=config.SCRYFALL_REFRESH_RATE + 1)
            if name == "Counterspell"
            else _card(name) if name != "Llanowar Elf" else None
        )
    )

    result = _classify_cards(conn, meta)

    fresh_result, outdated_result, missing_result = result

    assert fresh_result[0].name == "Duress"
    assert outdated_result[0].name == "Counterspell"
    assert missing_result == ["Llanowar Elf"]

def test_fetch_updates_for_outdated(monkeypatch: MonkeyPatch) -> None:
    conn = sqlite3.connect(":memory:")

    outdated = [_card("Unknown"), _card("Cancel")]

    fetch_batch_response = {
        "data": [{"name": "Cancel"}],
        "not_found": [{"name": "Unknown"}]
    }

    monkeypatch.setattr(
        "meta_morphis.scryfall.service.fetch_batch",
        lambda names: fetch_batch_response
    )

    monkeypatch.setattr(
        "meta_morphis.scryfall.service._process_batch_request",
        lambda conn, raw: [_card(c["name"]) for c in raw["data"]]
    )

    result = _fetch_updates_for_outdated(conn, outdated)

    updates, unrecognized = result

    assert updates == [_card("Cancel")]
    assert unrecognized == [_card("Unknown")]

def test_fetch_cards(monkeypatch: MonkeyPatch) -> None:
    conn = sqlite3.connect(":memory:")

    fresh = MetaEntry(
        name= "Duress",
        rank= 10,
        percent= 15,
        avg_copies= 2
    )
    outdated_refreshed = MetaEntry(
        name= "Counterspell",
        rank= 5,
        percent= 10,
        avg_copies= 3.2
    )
    outdated_not_refreshed = MetaEntry(
        name= "Fling",
        rank= 20,
        percent= 4,
        avg_copies= 1.1
    )
    missing = MetaEntry(
        name= "Llanowar Elf",
        rank= 1,
        percent= 25,
        avg_copies= 3.9
    )

    meta = [fresh, outdated_refreshed, outdated_not_refreshed, missing]
    monkeypatch.setattr(
        "meta_morphis.scryfall.service._classify_cards", 
        lambda conn, meta: (
            [_card(fresh.name)], 
            [_card(outdated_refreshed.name), _card(outdated_not_refreshed.name)], 
            [missing.name]
        )
    )
    monkeypatch.setattr(
        "meta_morphis.scryfall.service.fetch_batch", 
        lambda names: {"data": [{"name": n} for n in names]}
    )
    monkeypatch.setattr(
        "meta_morphis.scryfall.service._process_batch_request", 
        lambda conn, raw: [_card(c["name"]) for c in raw["data"]]
    )
    monkeypatch.setattr(
        "meta_morphis.scryfall.service.save_cards_to_cache", 
        lambda conn, cards: None
    )
    monkeypatch.setattr(
        "meta_morphis.scryfall.service._fetch_updates_for_outdated", 
        lambda conn, outdated: ([_card(outdated_refreshed.name)], [_card(outdated_not_refreshed.name)])
    )

    result = fetch_cards(conn, meta)

    assert result == [
        _card(fresh.name), 
        _card(outdated_refreshed.name),
        _card(outdated_not_refreshed.name),
        _card(missing.name),
    ]

def test_fetch_cards_raises() -> None:
    conn = sqlite3.connect(":memory:")

    with pytest.raises(RuntimeError):
        fetch_cards(conn, [])

def test_process_batch_request(monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]) -> None:
    conn = sqlite3.connect(":memory:")

    raw: dict[str, Any] = {"object": []}

    monkeypatch.setattr(
        "meta_morphis.scryfall.service.record_bad_name_attempt",
        lambda conn, name: None
    )

    assert _process_batch_request(conn, raw) == []
    captured = capsys.readouterr()
    assert "Scryfall error: no data received" in captured.out

    raw = {"data": []}
    assert _process_batch_request(conn, raw) == []
    captured = capsys.readouterr()
    assert "Scryfall error: no data received" in captured.out

    raw = {
        "data": [
            {"id": "1", "name": "Counterspell"},
            {"id": "2", "name": "Duress"}
        ],
        "not_found": [{"name": "Unknown"}, {"name": "Cancel"}]
    }

    monkeypatch.setattr(
        "meta_morphis.scryfall.service.fetch_single",
        lambda name: {"id": "3", "name": name} if name != "Unknown" else None
    )
    
    assert _process_batch_request(conn, raw) == [
        _card("Counterspell", card_id="1"),
        _card("Duress", card_id="2"),
        _card("Cancel", card_id="3"),
    ]

def test_process_batch_request_accepts_fuzzy_match_with_different_name(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    conn = sqlite3.connect(":memory:")

    monkeypatch.setattr(
        "meta_morphis.scryfall.service.record_bad_name_attempt",
        lambda conn, name: pytest.fail("a resolved fuzzy match must not be recorded as a bad name")
    )
    monkeypatch.setattr(
        "meta_morphis.scryfall.service.fetch_single",
        lambda name: {"id": "1", "name": "Snapcaster Mage"}
    )

    raw: dict[str, Any] = {
        "data": [],
        "not_found": [{"name": "Snapcaster Mag"}],
    }

    result = _process_batch_request(conn, raw)

    assert result == [_card("Snapcaster Mage", card_id="1")]
    captured = capsys.readouterr()
    assert "Bad name" not in captured.out