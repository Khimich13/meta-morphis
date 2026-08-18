import pytest

import config

from meta_morphis.scryfall.service import (
    fetch_cards,
    fetch_one_by_one,
    classify_cards,
    refresh_outdated,
    process_batch_request
)

from meta_morphis.models.meta import MetaEntry

def test_fetch_one_by_one(capsys, monkeypatch):
    conn = object()

    cache = "Lightning Bolt"
    fetch = "Shock"

    names = ["Lightning Bolt", "Shock", "Unknown"]

    monkeypatch.setattr(
        "meta_morphis.scryfall.service.get_card_from_cache",
        lambda conn, name: cache if name == "Lightning Bolt" else None
    )

    monkeypatch.setattr("time.sleep", lambda x: None)

    monkeypatch.setattr(
        "meta_morphis.scryfall.service.fetch_single",
        lambda name: fetch if name == "Shock" else None
    )

    result = fetch_one_by_one(conn, names)

    captured = capsys.readouterr()

    assert "Not found: Unknown" in captured.out
    assert result == ["Lightning Bolt", "Shock"]

def test_classify_cards(monkeypatch):
    conn = object()

    fresh_meta = MetaEntry(
        name= "Duress",
        rank= 10,
        percent= 15,
        deck_count= 2
    )
    outdated_meta = MetaEntry(
        name= "Counterspell",
        rank= 5,
        percent= 10,
        deck_count= 3.2
    )
    missing_meta = MetaEntry(
        name= "Llanowar Elf",
        rank= 1,
        percent= 25,
        deck_count= 3.9
    )

    meta = [fresh_meta, outdated_meta, missing_meta]

    monkeypatch.setattr(
        "meta_morphis.scryfall.service.get_card_from_cache",
        lambda conn, name: {f"{name}": []} if name != "Llanowar Elf" else None
    )

    monkeypatch.setattr(
        "meta_morphis.scryfall.service.get_card_age",
        lambda conn, name: 0 if name == "Duress" else config.SCRYFALL_REFRESH_RATE + 1
    )

    result = classify_cards(conn, meta)

    fresh_result, outdated_result, missing_result = result

    assert fresh_result == [{"Duress": []}]
    assert outdated_result == [{"Counterspell": []}]
    assert missing_result == ["Llanowar Elf"]

def test_refresh_outdated(monkeypatch):
    conn = object()

    outdated = [
        {"name": "Counterspell"}, 
        {"name": "Duress"}, 
        {"name": "Unknown"}, 
        {"name": "Cancel"}]

    fetch_batch_response = {
        "data": [{"name": "Counterspell"}, {"name": "Duress"}],
        "not_found": [{"name": "Unknown"}, {"name": "Cancel"}]
    }

    monkeypatch.setattr(
        "meta_morphis.scryfall.service.fetch_batch",
        lambda names: fetch_batch_response
    )

    monkeypatch.setattr(
        "meta_morphis.scryfall.service.get_card_from_cache", 
        lambda conn, name: {"name": "Cancel"} if name == "Cancel" else None
    )

    monkeypatch.setattr(
        "meta_morphis.scryfall.service.fetch_single", 
        lambda name: None
    )

    result = refresh_outdated(conn, outdated)

    refreshed, not_refreshed = result

    assert refreshed == [{"name": "Counterspell"}, {"name": "Duress"}, {"name": "Cancel"}]
    assert not_refreshed == [{"name": "Unknown"}]

def test_fetch_cards(monkeypatch):
    conn = object()

    fresh = MetaEntry(
        name= "Duress",
        rank= 10,
        percent= 15,
        deck_count= 2
    )
    outdated_refreshed = MetaEntry(
        name= "Counterspell",
        rank= 5,
        percent= 10,
        deck_count= 3.2
    )
    outdated_not_refreshed = MetaEntry(
        name= "Fling",
        rank= 20,
        percent= 4,
        deck_count= 1.1
    )
    missing = MetaEntry(
        name= "Llanowar Elf",
        rank= 1,
        percent= 25,
        deck_count= 3.9
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
        {"name": missing.name},
        {"name": outdated_refreshed.name},
        {"name": outdated_not_refreshed.name}
    ]

def test_fetch_cards_raises():
    conn = object()

    with pytest.raises(RuntimeError):
        fetch_cards(conn, [])

def test_process_batch_request(monkeypatch, capsys):
    conn = object()

    raw = {"object": []}
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
        "meta_morphis.scryfall.service.fetch_one_by_one", 
        lambda conn, names: ([{"name": "Cancel"}])
    )
    
    assert process_batch_request(conn, raw) == [
        {"name": "Counterspell"}, 
        {"name": "Duress"}, 
        {"name": "Cancel"}
    ]