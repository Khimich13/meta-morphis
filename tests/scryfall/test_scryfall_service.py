import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from pytest import LogCaptureFixture, MonkeyPatch

from meta_morphis import config
from meta_morphis.models.card import Card
from meta_morphis.models.meta import MetaEntry
from meta_morphis.scryfall.repo import (
    add_alias,
    get_card_from_cache,
    record_bad_name_attempt,
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


def _card(name: str, age: int = 0, card_id: str = "test", oracle_id: str | None = None) -> Card:
    raw = {"id": card_id, "name": name}
    if oracle_id:
        raw["oracle_id"] = oracle_id
    card = Card.from_raw(raw)
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
            _card(name, age=config.SCRYFALL_REFRESH_RATE + 1, oracle_id="o1")
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
        lambda conn, name: _card(name, age=-3600, oracle_id="o1")
    )

    fresh, outdated, missing = _classify_cards(conn, [MetaEntry(name="Counterspell", rank=1)])

    assert fresh == []
    assert [c.name for c in outdated] == ["Counterspell"]
    assert missing == []

# The refresh asks by oracle_id. A stale card cached without one is
# fetched by name instead, like a card that isn't cached at all
def test_classify_cards_fetches_a_stale_card_without_oracle_id_by_name(conn: sqlite3.Connection) -> None:
    save_cards_to_cache(conn, [_card("Counterspell")])
    conn.execute("UPDATE cards SET updated_at = 0")

    fresh, outdated, missing = _classify_cards(conn, [MetaEntry(name="Counterspell")])

    assert fresh == [] and outdated == []
    assert missing == ["Counterspell"]

# One card is refreshed, the other Scryfall no longer has: its stale copy
# is kept, and the miss starts the cooldown
def test_fetch_updates_for_outdated(conn: sqlite3.Connection, monkeypatch: MonkeyPatch) -> None:
    outdated = [_card("Unknown", oracle_id="o-unknown"), _card("Cancel", oracle_id="o-cancel")]

    asked: list[list[str]] = []
    def answer(oracle_ids: list[str]) -> dict[str, Any]:
        asked.append(oracle_ids)
        return {
            "data": [{"id": "2", "oracle_id": "o-cancel", "name": "Cancel"}],
            "not_found": [{"oracle_id": "o-unknown"}],
        }
    monkeypatch.setattr("meta_morphis.scryfall.service.fetch_by_oracle_ids", answer)

    updates, unrecognized = _fetch_updates_for_outdated(conn, outdated)

    assert asked == [["o-unknown", "o-cancel"]]
    assert [c.id for c in updates] == ["2"]
    assert unrecognized == [outdated[0]]
    assert should_skip_lookup(conn, "Unknown") is True
    assert should_skip_lookup(conn, "Cancel") is False

# A batch that couldn't be reached must be reported, not silently dropped
def test_fetch_updates_for_outdated_reports_unreachable_batch(
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch, caplog: LogCaptureFixture
) -> None:
    outdated = [_card("Counterspell", oracle_id="o1"), _card("Duress", oracle_id="o2")]

    def raise_unavailable(oracle_ids: list[str]) -> dict[str, Any] | None:
        raise RequestUnavailable("Scryfall is down")

    monkeypatch.setattr("meta_morphis.scryfall.service.fetch_by_oracle_ids", raise_unavailable)

    updates, unrecognized = _fetch_updates_for_outdated(conn, outdated)

    assert updates == []
    assert unrecognized == outdated
    assert "2 outdated card" in caplog.text
    assert "unreachable" in caplog.text

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
        lambda conn, raw, asked: ([_card(c["name"]) for c in raw["data"]], [])
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
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch, caplog: LogCaptureFixture
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
    assert "1 missing card" in caplog.text
    assert "unreachable" in caplog.text

def test_process_batch_request(conn: sqlite3.Connection, monkeypatch: MonkeyPatch, caplog: LogCaptureFixture) -> None:
    raw: dict[str, Any] = {"object": []}

    monkeypatch.setattr(
        "meta_morphis.scryfall.service.record_bad_name_attempt",
        lambda conn, name: None
    )

    assert _process_batch_request(conn, raw, []) == ([], [])
    assert "Scryfall error: no data received" in caplog.text

    # Start fresh, so the next check proves a second message was logged
    caplog.clear()
    raw = {"data": []}
    assert _process_batch_request(conn, raw, []) == ([], [])
    assert "Scryfall error: no data received" in caplog.text

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

    asked = ["Counterspell", "Unknown", "Duress", "Cancel"]
    assert _process_batch_request(conn, raw, asked) == (
        [
            _card("Counterspell", card_id="1"),
            _card("Duress", card_id="2"),
            _card("Cancel", card_id="3"),
        ],
        ["Unknown"],
    )

def test_process_batch_request_accepts_fuzzy_match_with_different_name(
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch, caplog: LogCaptureFixture
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

    result = _process_batch_request(conn, raw, ["Snapcaster Mag"])

    assert result == ([_card("Snapcaster Mage", card_id="1")], [])
    assert "Bad name" not in caplog.text

    # The exact spelling that was searched for gets its own alias
    # too, not just the canonical name it resolved to.
    found = get_card_from_cache(conn, "Snapcaster Mag")
    assert found is not None
    assert found.name == "Snapcaster Mage"

# If a bad response is not confirmed that it's a genuine "doesn't exist"
# than it shouldn't go to the 7-day card_lookup_failures ban list
def test_process_batch_request_does_not_record_failure_on_outage(
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch, caplog: LogCaptureFixture
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

    result = _process_batch_request(conn, raw, ["Counterspell"])

    assert result == ([], ["Counterspell"])
    assert "Bad name" not in caplog.text
    assert "Counterspell" in caplog.text

# A split card is looked up by its full name, not by one face: Start // Fire
# is cached and owns the face name "Fire", so looking up Fire // Ice by "Fire"
# would hand back the wrong card
def test_classify_cards_looks_up_a_split_card_by_its_full_name(conn: sqlite3.Connection) -> None:
    start_fire = Card.from_raw({
        "id": "sf", "name": "Start // Fire", "type_line": "Sorcery",
        "card_faces": [
            {"name": "Start", "mana_cost": "2W", "type_line": "Sorcery"},
            {"name": "Fire", "mana_cost": "2R", "type_line": "Sorcery"},
        ],
    })
    save_cards_to_cache(conn, [start_fire])

    fresh, outdated, missing = _classify_cards(conn, [MetaEntry(name="Fire // Ice")])

    assert fresh == [] and outdated == []
    assert missing == ["Fire // Ice"]

# MTGGoldfish lists a double-faced card by its front face, but a failed
# refresh is recorded under the full name the refresh asked Scryfall for.
# The cooldown has to find that record, or the card is retried every run.
def test_classify_cards_skips_outdated_double_faced_card_within_cooldown(conn: sqlite3.Connection) -> None:
    delver = Card.from_raw({
        "id": "d", "name": "Delver of Secrets // Insectile Aberration",
        "card_faces": [
            {"name": "Delver of Secrets", "type_line": "Creature"},
            {"name": "Insectile Aberration", "type_line": "Creature"},
        ],
    })
    save_cards_to_cache(conn, [delver])
    conn.execute("UPDATE cards SET updated_at = 0")
    record_bad_name_attempt(conn, delver.name)

    fresh, outdated, missing = _classify_cards(conn, [MetaEntry(name="Delver of Secrets")])

    assert [c.name for c in fresh] == [delver.name]
    assert outdated == [] and missing == []

# Refreshed and newly fetched cards are each read back through a second
# connection, which only sees committed data. They're tested separately on
# purpose: in one run, committing the newly fetched cards also commits a
# pending refresh, which would hide a missing commit on the refresh path.
def test_fetch_cards_commits_refreshed_card(db_file: Path, monkeypatch: MonkeyPatch) -> None:
    writer = sqlite3.connect(db_file)
    with writer:
        save_cards_to_cache(writer, [Card.from_raw({"id": "old", "oracle_id": "o1", "name": "Counterspell"})])
        writer.execute("UPDATE cards SET updated_at = 0")

    monkeypatch.setattr(
        "meta_morphis.scryfall.service.fetch_by_oracle_ids",
        lambda oracle_ids: {"data": [{"id": "new", "oracle_id": "o1", "name": "Counterspell"}]}
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

    _process_batch_request(conn, {"data": [], "not_found": [{"name": "Bogus Card"}]}, ["Bogus Card"])

    assert should_skip_lookup(conn, "Bogus Card") is True

# A card missing a required field is skipped with a message instead of
# crashing the whole batch, and the rest of the batch still comes through
def test_process_batch_request_skips_malformed_card(conn: sqlite3.Connection) -> None:
    raw: dict[str, Any] = {"data": [{"name": "No Id Card"}, {"id": "1", "name": "Shock"}]}

    cards, unresolved = _process_batch_request(conn, raw, ["No Id Card", "Shock"])

    assert [c.name for c in cards] == ["Shock"]
    assert unresolved == ["No Id Card"]

# An entry of the wrong shape - null, or card_faces: null - is skipped the
# same way. It used to raise TypeError past _to_card and lose the batch's
# good cards with it
def test_process_batch_request_skips_card_of_wrong_shape(conn: sqlite3.Connection) -> None:
    raw: dict[str, Any] = {"data": [
        None,
        {"id": "1", "name": "No Faces", "card_faces": None},
        {"id": "2", "name": "Shock"},
    ]}

    cards, unresolved = _process_batch_request(conn, raw, ["Null Card", "No Faces", "Shock"])

    assert [c.name for c in cards] == ["Shock"]
    assert unresolved == ["Null Card", "No Faces"]
    found = get_card_from_cache(conn, "Shock")
    assert found is not None

# Unpaired, a null entry has no name to report - it is only skipped
def test_process_batch_request_skips_null_card_when_the_counts_differ(conn: sqlite3.Connection) -> None:
    raw: dict[str, Any] = {"data": [None, {"id": "2", "name": "Shock"}], "not_found": []}

    cards, unresolved = _process_batch_request(conn, raw, ["Shock"])

    assert [c.name for c in cards] == ["Shock"]
    assert unresolved == []

# An outdated card whose refreshed entry can't be parsed used to vanish
# from the output instead of falling back to its stale cached copy
def test_fetch_updates_for_outdated_keeps_card_with_malformed_refresh(conn: sqlite3.Connection, monkeypatch: MonkeyPatch) -> None:
    outdated = [_card("Sai, Master Thopterist", oracle_id="o1"), _card("Counterspell", oracle_id="o2")]

    monkeypatch.setattr(
        "meta_morphis.scryfall.service.fetch_by_oracle_ids",
        lambda oracle_ids: {
            "data": [
                {"oracle_id": "o1", "name": "Sai, Master Thopterist"},
                {"id": "2", "oracle_id": "o2", "name": "Counterspell"},
            ],
            "not_found": [],
        }
    )

    updates, unrecognized = _fetch_updates_for_outdated(conn, outdated)

    assert [c.name for c in updates] == ["Counterspell"]
    assert [c.name for c in unrecognized] == ["Sai, Master Thopterist"]

# Scryfall can rename a card (an errata rename). The refresh asks by
# oracle_id, so it gets the card under its new name. The old row must
# not stay: its names would still lead to the stale copy, and it would
# be refreshed again every run. A double-faced card listed by its front
# face shows that every old name moves to the new card.
def test_fetch_cards_moves_old_names_to_a_renamed_card(
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch
) -> None:
    save_cards_to_cache(conn, [Card.from_raw({
        "id": "1", "oracle_id": "o1", "name": "Old Front // Old Back",
        "card_faces": [
            {"name": "Old Front", "type_line": "Creature"},
            {"name": "Old Back", "type_line": "Creature"},
        ],
    })])
    conn.execute("UPDATE cards SET updated_at = 0")

    renamed = {
        "id": "1", "oracle_id": "o1", "name": "New Front // New Back",
        "card_faces": [
            {"name": "New Front", "type_line": "Creature"},
            {"name": "New Back", "type_line": "Creature"},
        ],
    }
    asked: list[list[str]] = []
    def answer(oracle_ids: list[str]) -> dict[str, Any]:
        asked.append(oracle_ids)
        return {"data": [renamed], "not_found": []}
    monkeypatch.setattr("meta_morphis.scryfall.service.fetch_by_oracle_ids", answer)

    first_run = fetch_cards(conn, [MetaEntry(name="Old Front")])
    second_run = fetch_cards(conn, [MetaEntry(name="Old Front")])

    assert [c.name for c in first_run] == ["New Front // New Back"]
    assert [c.name for c in second_run] == ["New Front // New Back"]
    assert asked == [["o1"]]
    assert conn.execute("SELECT name FROM cards").fetchall() == [("new front // new back",)]

# A cached row whose oracle_id can't be read (corrupt JSON, or none in
# it) used to stay when Scryfall answered its name with a renamed card: add_alias refused the name, the fetched card was
# dropped and the name recorded as a bad lookup - so after every cooldown
# the card was left out of the export again. The row is replaced instead.
@pytest.mark.parametrize("blob", ['"broken"', "{not json", json.dumps({"id": "1", "name": "Old"})])
def test_process_batch_request_replaces_an_unreadable_row_a_rename_answers(
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch, blob: str
) -> None:
    save_cards_to_cache(conn, [Card.from_raw({"id": "1", "oracle_id": "o1", "name": "Old"})])
    conn.execute("UPDATE cards SET json = ?", (blob,))

    renamed = {"id": "1", "oracle_id": "o1", "name": "New"}
    monkeypatch.setattr("meta_morphis.scryfall.service.fetch_single", lambda name: renamed)

    raw: dict[str, Any] = {"data": [], "not_found": [{"name": "Old"}]}
    cards, unresolved = _process_batch_request(conn, raw, ["Old"])

    assert [c.name for c in cards] == ["New"]
    assert unresolved == []
    assert should_skip_lookup(conn, "Old") is False
    assert conn.execute("SELECT name FROM cards").fetchall() == [("new",)]
    found = get_card_from_cache(conn, "Old")
    assert found is not None and found.name == "New"

# The same holds the other way round: an answer whose own oracle_id can't
# be read used to be refused as a different card, recorded as a bad lookup,
# and the stale copy stayed frozen under its old name. It replaces the row.
def test_process_batch_request_takes_a_rename_whose_oracle_id_is_unreadable(
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch
) -> None:
    save_cards_to_cache(conn, [Card.from_raw({"id": "1", "oracle_id": "o1", "name": "Old"})])

    renamed = {"id": "1", "name": "New"}
    monkeypatch.setattr("meta_morphis.scryfall.service.fetch_single", lambda name: renamed)

    raw: dict[str, Any] = {"data": [], "not_found": [{"name": "Old"}]}
    cards, unresolved = _process_batch_request(conn, raw, ["Old"])

    assert [c.name for c in cards] == ["New"]
    assert unresolved == []
    assert should_skip_lookup(conn, "Old") is False
    assert conn.execute("SELECT name FROM cards").fetchall() == [("new",)]
    found = get_card_from_cache(conn, "Old")
    assert found is not None and found.name == "New"

# Each card in a batch answer is paired with the name it answers by
# skipping the names Scryfall didn't find. If one went missing without a
# not_found entry, every later pair would be wrong and would hand one
# card's names to another - so nothing is paired then.
def test_process_batch_request_pairs_nothing_when_the_counts_differ(
    conn: sqlite3.Connection, caplog: LogCaptureFixture
) -> None:
    save_cards_to_cache(conn, [_card("Counterspell", card_id="1")])

    raw: dict[str, Any] = {"data": [{"id": "2", "name": "Duress"}], "not_found": []}
    cards, unresolved = _process_batch_request(conn, raw, ["Counterspell", "Duress"])

    assert [c.name for c in cards] == ["Duress"]
    assert unresolved == []
    found = get_card_from_cache(conn, "Counterspell")
    assert found is not None and found.name == "Counterspell"
    assert "not checking them for renamed cards" in caplog.text

# Two names on the list can point at one cached card (here an old
# spelling and the new one). When it goes stale, Scryfall is asked about
# it once: asking twice would fetch and save it twice.
def test_fetch_cards_asks_once_for_a_stale_card_two_names_share(
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch
) -> None:
    card = {"id": "1", "oracle_id": "o1", "name": "New"}
    save_cards_to_cache(conn, [Card.from_raw(card)])
    add_alias(conn, "Old", "New")
    conn.execute("UPDATE cards SET updated_at = 0")

    asked: list[list[str]] = []
    def answer(oracle_ids: list[str]) -> dict[str, Any]:
        asked.append(oracle_ids)
        return {"data": [card], "not_found": []}
    monkeypatch.setattr("meta_morphis.scryfall.service.fetch_by_oracle_ids", answer)

    result = fetch_cards(conn, [MetaEntry(name="Old"), MetaEntry(name="New")])

    assert asked == [["o1"]]
    assert [c.name for c in result] == ["New"]

# A fresh card two list names share comes back once, not once per name
def test_classify_cards_keeps_one_copy_of_a_fresh_card_two_names_share(conn: sqlite3.Connection) -> None:
    save_cards_to_cache(conn, [Card.from_raw({"id": "1", "oracle_id": "o1", "name": "New"})])
    add_alias(conn, "Old", "New")

    fresh, outdated, missing = _classify_cards(conn, [MetaEntry(name="Old"), MetaEntry(name="New")])

    assert [c.name for c in fresh] == ["New"]
    assert outdated == []
    assert missing == []

# A stale card two names share that can't be refreshed is kept once and
# counted once - it used to be in `unrecognized` twice
def test_fetch_cards_keeps_one_copy_of_a_shared_stale_card_it_could_not_refresh(
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch, caplog: LogCaptureFixture
) -> None:
    save_cards_to_cache(conn, [Card.from_raw({"id": "1", "oracle_id": "o1", "name": "New"})])
    add_alias(conn, "Old", "New")
    conn.execute("UPDATE cards SET updated_at = 0")

    def raise_unavailable(oracle_ids: list[str]) -> dict[str, Any] | None:
        raise RequestUnavailable("Scryfall is down")
    monkeypatch.setattr("meta_morphis.scryfall.service.fetch_by_oracle_ids", raise_unavailable)

    result = fetch_cards(conn, [MetaEntry(name="Old"), MetaEntry(name="New")])

    assert [c.name for c in result] == ["New"]
    assert "Could not refresh 1 outdated card(s) - using the cached copies" in caplog.text

# add_alias also turns down a name another card already claimed (first
# claim wins). The card Scryfall answered with is still the right one,
# so it stays in the run and the name is not recorded as a bad lookup.
# Treating that refusal like a fuzzy match onto another card used to
# drop the card and start the name's cooldown.
def test_process_batch_request_keeps_a_card_whose_alias_another_card_claimed(
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch, caplog: LogCaptureFixture
) -> None:
    save_cards_to_cache(conn, [Card.from_raw({"id": "2", "oracle_id": "o2", "name": "Owner"})])
    add_alias(conn, "Shared", "Owner")

    answer = {"id": "1", "oracle_id": "o1", "name": "Answer"}
    monkeypatch.setattr("meta_morphis.scryfall.service.fetch_single", lambda name: answer)

    raw: dict[str, Any] = {"data": [], "not_found": [{"name": "Shared"}]}
    cards, unresolved = _process_batch_request(conn, raw, ["Shared"])

    assert [c.name for c in cards] == ["Answer"]
    assert unresolved == []
    assert should_skip_lookup(conn, "Shared") is False
    found = get_card_from_cache(conn, "Shared")
    assert found is not None and found.name == "Owner"
    assert "already belongs to another card" in caplog.text
