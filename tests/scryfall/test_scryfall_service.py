import sqlite3
from pathlib import Path
from typing import Any

import pytest
from pytest import CaptureFixture, MonkeyPatch

from meta_morphis import config
from meta_morphis.models.card import Card
from meta_morphis.models.meta import MetaEntry
from meta_morphis.scryfall.repo import (
    get_card_from_cache,
    save_cards_to_cache,
    should_skip_lookup,
)
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

def test_classify_cards(conn: sqlite3.Connection, monkeypatch: MonkeyPatch) -> None:
    fresh_meta = MetaEntry(
        name="Duress",
        rank=10,
        percent=15,
        avg_copies=2
    )
    outdated_meta = MetaEntry(
        name="Counterspell",
        rank=5,
        percent=10,
        avg_copies=3.2
    )
    missing_meta = MetaEntry(
        name="Llanowar Elf",
        rank=1,
        percent=25,
        avg_copies=3.9
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

def test_classify_cards_skips_outdated_card_within_cooldown(conn: sqlite3.Connection, monkeypatch: MonkeyPatch) -> None:
    # A refresh recently confirmed to fail for this name used to be
    # retried every single run regardless, since should_skip_lookup
    # was only ever consulted on the cache-miss branch - never for a
    # cached-but-outdated card. That's 2 Scryfall requests per stale
    # card, forever, for a name that's already known to fail.

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

# A negative age means the card was cached by a clock that ran ahead
def test_classify_cards_treats_future_cached_card_as_outdated(conn: sqlite3.Connection, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "meta_morphis.scryfall.service.should_skip_lookup",
        lambda conn, name: False
    )
    monkeypatch.setattr(
        "meta_morphis.scryfall.service.get_card_from_cache",
        lambda conn, name: _card(name, age=-3600)
    )

    fresh, outdated, missing = _classify_cards(conn, [MetaEntry(name="Counterspell", rank=1)])

    assert fresh == []
    assert [c.name for c in outdated] == ["Counterspell"]
    assert missing == []

def test_fetch_updates_for_outdated(conn: sqlite3.Connection, monkeypatch: MonkeyPatch) -> None:
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

def test_fetch_updates_for_outdated_renamed_card_not_also_unrecognized(conn: sqlite3.Connection, monkeypatch: MonkeyPatch) -> None:
    # a Scryfall errata rename (or a fuzzy correction) can give a refreshed card a
    # different name than it was cached under. Comparing the OLD requested name against
    # the SET OF NEW names used to conclude the old name was "not
    # found" even though it WAS refreshed - just under a different name
    # - so the same physical card ended up in both `updates` and `unrecognized`.

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
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
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

def test_fetch_cards(conn: sqlite3.Connection, monkeypatch: MonkeyPatch) -> None:
    fresh = MetaEntry(
        name="Duress",
        rank=10,
        percent=15,
        avg_copies=2
    )
    outdated_refreshed = MetaEntry(
        name="Counterspell",
        rank=5,
        percent=10,
        avg_copies=3.2
    )
    outdated_not_refreshed = MetaEntry(
        name="Fling",
        rank=20,
        percent=4,
        avg_copies=1.1
    )
    missing = MetaEntry(
        name="Llanowar Elf",
        rank=1,
        percent=25,
        avg_copies=3.9
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

def test_fetch_cards_raises(conn: sqlite3.Connection) -> None:
    with pytest.raises(RuntimeError):
        fetch_cards(conn, [])

# Make sure that when more than 75 cards requested and any of the batch calls
# fails, the caller will be notified
def test_fetch_cards_reports_unreachable_missing_batch(
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:

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

def test_process_batch_request(conn: sqlite3.Connection, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]) -> None:
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
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
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
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
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

# Split cards are looked up by their lookup_name ("Wear"), not Goldfish's
# full "A // B" name - that's what gets queued and sent to Scryfall
def test_classify_cards_uses_lookup_name(conn: sqlite3.Connection, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("meta_morphis.scryfall.service.should_skip_lookup", lambda conn, name: False)
    monkeypatch.setattr("meta_morphis.scryfall.service.get_card_from_cache", lambda conn, name: None)

    _, _, missing = _classify_cards(conn, [MetaEntry(name="Wear // Tear", lookup_name="Wear")])

    assert missing == ["Wear"]

# Refreshed and newly fetched cards are each read back through a second
# connection, which only sees committed data. They're tested separately on
# purpose: in one run, committing the newly fetched cards also commits a
# pending refresh, which would hide a missing commit on the refresh path.
def test_fetch_cards_commits_refreshed_card(db_file: Path, monkeypatch: MonkeyPatch) -> None:
    writer = sqlite3.connect(db_file)
    with writer:
        save_cards_to_cache(writer, [Card.from_raw({"id": "old", "name": "Counterspell"})])
        writer.execute("UPDATE cards SET updated_at = 0")

    monkeypatch.setattr(
        "meta_morphis.scryfall.service.fetch_batch",
        lambda names: {"data": [{"id": "new", "name": "Counterspell"}]}
    )

    fetch_cards(writer, [MetaEntry(name="Counterspell")])
    writer.close()

    reader = sqlite3.connect(db_file)
    refreshed = get_card_from_cache(reader, "Counterspell")
    reader.close()

    assert refreshed is not None
    assert refreshed.id == "new"
    assert refreshed.age < 60

def test_fetch_cards_commits_newly_fetched_card(db_file: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "meta_morphis.scryfall.service.fetch_batch",
        lambda names: {"data": [{"id": "1", "name": "Shock"}]}
    )

    writer = sqlite3.connect(db_file)
    fetch_cards(writer, [MetaEntry(name="Shock")])
    writer.close()

    reader = sqlite3.connect(db_file)
    fetched = get_card_from_cache(reader, "Shock")
    reader.close()

    assert fetched is not None

# The counterpart to the outage test: a CONFIRMED miss (both exact and fuzzy
# found nothing) must start the cooldown, or the name is re-queried every run
def test_process_batch_request_records_confirmed_bad_name(conn: sqlite3.Connection, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("meta_morphis.scryfall.service.fetch_single", lambda name: None)

    _process_batch_request(conn, {"data": [], "not_found": [{"name": "Bogus Card"}]})

    assert should_skip_lookup(conn, "Bogus Card") is True

# A card missing a required field is skipped with a message instead of
# crashing the whole batch, and the rest of the batch still comes through
def test_process_batch_request_skips_malformed_card(conn: sqlite3.Connection) -> None:
    raw: dict[str, Any] = {"data": [{"name": "No Id Card"}, {"id": "1", "name": "Shock"}]}

    cards, unresolved = _process_batch_request(conn, raw)

    assert [c.name for c in cards] == ["Shock"]
    assert unresolved == ["No Id Card"]

# An outdated card whose refreshed entry can't be parsed used to vanish
# from the output instead of falling back to its stale cached copy
def test_fetch_updates_for_outdated_keeps_card_with_malformed_refresh(conn: sqlite3.Connection, monkeypatch: MonkeyPatch) -> None:
    outdated = [_card("Sai, Master Thopterist"), _card("Counterspell")]

    monkeypatch.setattr(
        "meta_morphis.scryfall.service.fetch_batch",
        lambda names: {
            "data": [{"name": "Sai, Master Thopterist"}, {"id": "2", "name": "Counterspell"}],
            "not_found": [],
        }
    )

    updates, unrecognized = _fetch_updates_for_outdated(conn, outdated)

    assert [c.name for c in updates] == ["Counterspell"]
    assert [c.name for c in unrecognized] == ["Sai, Master Thopterist"]
