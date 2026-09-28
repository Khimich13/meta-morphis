import sqlite3
from typing import Any

import pytest
from pytest import CaptureFixture, MonkeyPatch

from meta_morphis import config
from meta_morphis.db.init_db import init_db
from meta_morphis.models.card import Card
from meta_morphis.models.meta import MetaEntry
from meta_morphis.scryfall.repo import get_card_from_cache
from meta_morphis.scryfall.service import (
    _classify_cards,
    _fetch_updates_for_outdated,
    _process_batch_request,
    fetch_cards,
)
from meta_morphis.utils.http import RequestUnavailable


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

def test_classify_cards_skips_outdated_card_within_cooldown(monkeypatch: MonkeyPatch) -> None:
    # A refresh recently confirmed to fail for this name used to be 
    # retried every single run regardless, since should_skip_lookup 
    # was only ever consulted on the cache-miss branch - never for a 
    # cached-but-outdated card. That's 2 Scryfall requests per stale 
    # card, forever, for a name that's already known to fail.
    conn = sqlite3.connect(":memory:")

    monkeypatch.setattr(
        "meta_morphis.scryfall.service.should_skip_lookup",
        lambda conn, name: True
    )
    monkeypatch.setattr(
        "meta_morphis.scryfall.service.get_card_from_cache",
        lambda conn, name: _card(name, age=config.SCRYFALL_REFRESH_RATE + 1)
    )

    fresh, outdated, missing = _classify_cards(conn, [MetaEntry(name="Sai, Master Thopterist", rank=1)])

    assert [c.name for c in fresh] == ["Sai, Master Thopterist"]
    assert outdated == []
    assert missing == []

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
        lambda conn, raw: (
            [_card(c["name"]) for c in raw["data"]],
            [item["name"] for item in raw.get("not_found", [])],
        )
    )

    result = _fetch_updates_for_outdated(conn, outdated)

    updates, unrecognized = result

    assert updates == [_card("Cancel")]
    assert unrecognized == [_card("Unknown")]

def test_fetch_updates_for_outdated_renamed_card_not_also_unrecognized(monkeypatch: MonkeyPatch) -> None:
    # a Scryfall errata rename (or a fuzzy correction) can give a refreshed card a
    # different name than it was cached under. Comparing the OLD requested name against
    # the SET OF NEW names used to conclude the old name was "not
    # found" even though it WAS refreshed - just under a different name
    # - so the same physical card ended up in both `updates` and `unrecognized`.
    conn = sqlite3.connect(":memory:")

    outdated = [_card("Æther Vial")]

    monkeypatch.setattr(
        "meta_morphis.scryfall.service.fetch_batch",
        lambda names: {"data": [], "not_found": [{"name": n} for n in names]}
    )
    monkeypatch.setattr(
        "meta_morphis.scryfall.service._process_batch_request",
        lambda conn, raw: ([_card("Aether Vial")], [])
    )

    updates, unrecognized = _fetch_updates_for_outdated(conn, outdated)

    assert [c.name for c in updates] == ["Aether Vial"]
    assert unrecognized == []

# A batch that couldn't be reached must be reported, not silently dropped
def test_fetch_updates_for_outdated_reports_unreachable_batch(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    conn = sqlite3.connect(":memory:")

    outdated = [_card("Counterspell"), _card("Duress")]

    def raise_unavailable(names: list[str]) -> dict[str, Any] | None:
        raise RequestUnavailable("Scryfall is down")

    monkeypatch.setattr("meta_morphis.scryfall.service.fetch_batch", raise_unavailable)

    updates, unrecognized = _fetch_updates_for_outdated(conn, outdated)

    assert updates == []
    assert unrecognized == outdated
    captured = capsys.readouterr()
    assert "2 outdated card" in captured.out
    assert "unreachable" in captured.out

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
        lambda conn, raw: ([_card(c["name"]) for c in raw["data"]], [])
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

# Make sure that when more than 75 cards requested and any of the batch calls
# fails, the caller will be notified
def test_fetch_cards_reports_unreachable_missing_batch(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    
    conn = sqlite3.connect(":memory:")

    fresh_meta = MetaEntry(name="Duress", rank=1, percent=10, avg_copies=2)
    missing_meta = MetaEntry(name="Counterspell", rank=2, percent=20, avg_copies=3)

    monkeypatch.setattr(
        "meta_morphis.scryfall.service._classify_cards",
        lambda conn, meta: ([_card("Duress")], [], ["Counterspell"])
    )

    def raise_unavailable(names: list[str]) -> dict[str, Any] | None:
        raise RequestUnavailable("Scryfall is down")

    monkeypatch.setattr("meta_morphis.scryfall.service.fetch_batch", raise_unavailable)

    result = fetch_cards(conn, [fresh_meta, missing_meta])

    assert result == [_card("Duress")]
    captured = capsys.readouterr()
    assert "1 missing card" in captured.out
    assert "unreachable" in captured.out

def test_process_batch_request(monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]) -> None:
    conn = sqlite3.connect(":memory:")

    raw: dict[str, Any] = {"object": []}

    monkeypatch.setattr(
        "meta_morphis.scryfall.service.record_bad_name_attempt",
        lambda conn, name: None
    )

    assert _process_batch_request(conn, raw) == ([], [])
    captured = capsys.readouterr()
    assert "Scryfall error: no data received" in captured.out

    raw = {"data": []}
    assert _process_batch_request(conn, raw) == ([], [])
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

    assert _process_batch_request(conn, raw) == (
        [
            _card("Counterspell", card_id="1"),
            _card("Duress", card_id="2"),
            _card("Cancel", card_id="3"),
        ],
        ["Unknown"],
    )

def test_process_batch_request_accepts_fuzzy_match_with_different_name(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    conn = sqlite3.connect(":memory:")
    init_db(conn)

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

    assert result == ([_card("Snapcaster Mage", card_id="1")], [])
    captured = capsys.readouterr()
    assert "Bad name" not in captured.out

    # The exact spelling that was searched for gets its own alias
    # too, not just the canonical name it resolved to.
    found = get_card_from_cache(conn, "Snapcaster Mag")
    assert found is not None
    assert found.name == "Snapcaster Mage"

# If a bad response is not confirmed that it's a genuine "doesn't exist"
# than it shouldn't go to the 7-day card_lookup_failures ban list
def test_process_batch_request_does_not_record_failure_on_outage(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    conn = sqlite3.connect(":memory:")

    monkeypatch.setattr(
        "meta_morphis.scryfall.service.record_bad_name_attempt",
        lambda conn, name: pytest.fail("a transient outage must not be recorded as a bad name")
    )

    def raise_unavailable(name: str) -> dict[str, Any] | None:
        raise RequestUnavailable("Scryfall is down")

    monkeypatch.setattr("meta_morphis.scryfall.service.fetch_single", raise_unavailable)

    raw: dict[str, Any] = {
        "data": [],
        "not_found": [{"name": "Counterspell"}],
    }

    result = _process_batch_request(conn, raw)

    assert result == ([], ["Counterspell"])
    captured = capsys.readouterr()
    assert "Bad name" not in captured.out
    assert "Counterspell" in captured.out