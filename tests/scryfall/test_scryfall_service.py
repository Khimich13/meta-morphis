import json
import sqlite3
from typing import Any

import pytest
from pytest import CaptureFixture, MonkeyPatch

import config
from meta_morphis.models.card import Card
from meta_morphis.models.meta import MetaEntry
from meta_morphis.scryfall.service import (
    classify_cards,
    fetch_cards,
    process_batch_request,
    refresh_outdated,
)
from meta_morphis.utils.text import normalize_name


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
            Card(
                id="test",
                name=name,
                mana_cost=None,
                type_line="",
                faces=[],
                age=config.SCRYFALL_REFRESH_RATE + 1
            )
            if name == "Counterspell"
            else Card(
                id="test",
                name=name,
                mana_cost=None,
                type_line="",
                faces=[],
                age=0
            )
            if name != "Llanowar Elf"
            else None
        )
    )

    result = classify_cards(conn, meta)

    fresh_result, outdated_result, missing_result = result

    assert fresh_result[0]["name"] == "Duress"
    assert outdated_result[0]["name"] == "Counterspell"
    assert missing_result == ["Llanowar Elf"]

def test_refresh_outdated(monkeypatch: MonkeyPatch) -> None:
    old_age = config.SCRYFALL_REFRESH_RATE
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE cards (
            id TEXT,
            name TEXT UNIQUE NOT NULL,
            json TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE card_lookup_failures (
            name TEXT PRIMARY KEY,
            last_attempt INTEGER
        )
    """)
    conn.execute(
        "INSERT INTO cards VALUES (?, ?, ?, ?)", (
            1,
            normalize_name("Cancel"),
            json.dumps({
                "id": 1,
                "name": "Cancel",
                "mana_cost": "1UU",
                "type_line": "Instant"
            }),
            old_age
        )
    )

    outdated = [
        {"name": "Unknown"}, 
        {"name": "Cancel"}]

    fetch_batch_response = {
        "data": [{"name": "Cancel"}],
        "not_found": [{"name": "Unknown"}]
    }

    monkeypatch.setattr(
        "meta_morphis.scryfall.service.fetch_batch",
        lambda names: fetch_batch_response
    )

    monkeypatch.setattr(
        "meta_morphis.scryfall.service.fetch_single", 
        lambda name: None
    )

    result = refresh_outdated(conn, outdated)

    refreshed, not_refreshed = result

    assert refreshed == [{"name": "Cancel"}]
    assert not_refreshed == [{"name": "Unknown"}]

    row = conn.execute(
        "SELECT updated_at FROM cards WHERE name = ?", (normalize_name("Cancel"),)
    ).fetchone()
    
    assert row != None

    current_age = row[0]

    assert current_age > old_age

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
        "meta_morphis.scryfall.service.classify_cards", 
        lambda conn, meta: (
            [{"name": fresh.name}], 
            [{"name": outdated_refreshed.name}, {"name": outdated_not_refreshed.name}], 
            [missing.name]
        )
    )
    monkeypatch.setattr(
        "meta_morphis.scryfall.service.fetch_batch", 
        lambda names: {"data": [{"name": n} for n in names]}
    )
    monkeypatch.setattr(
        "meta_morphis.scryfall.service.process_batch_request", 
        lambda conn, raw: raw["data"]
    )
    monkeypatch.setattr(
        "meta_morphis.scryfall.service.save_cards_to_cache", 
        lambda conn, cards: None
    )
    monkeypatch.setattr(
        "meta_morphis.scryfall.service.refresh_outdated", 
        lambda conn, outdated: ([{"name": outdated_refreshed.name}], [{"name": outdated_not_refreshed.name}])
    )

    result = fetch_cards(conn, meta)

    assert result == [
        {"name": fresh.name}, 
        {"name": outdated_refreshed.name},
        {"name": outdated_not_refreshed.name},
        {"name": missing.name}
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

    assert process_batch_request(conn, raw) == []
    captured = capsys.readouterr()
    assert "Scryfall error: no data received" in captured.out

    raw = {"data": []}
    assert process_batch_request(conn, raw) == []
    captured = capsys.readouterr()
    assert "Scryfall error: no data received" in captured.out

    raw = {
        "data": [{"name": "Counterspell"}, {"name": "Duress"}],
        "not_found": [{"name": "Unknown"}, {"name": "Cancel"}]
    }

    monkeypatch.setattr(
        "meta_morphis.scryfall.service.fetch_single", 
        lambda name: {"name": name} if name != "Unknown" else None
    )
    
    assert process_batch_request(conn, raw) == [
        {"name": "Counterspell"}, 
        {"name": "Duress"}, 
        {"name": "Cancel"}
    ]