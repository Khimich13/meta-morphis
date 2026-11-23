import sqlite3
import time
from datetime import date
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from meta_morphis.meta.decklists import DeckCount
from meta_morphis.meta.repo import (
    get_decks_to,
    get_meta_from_cache,
    get_meta_timestamp,
    save_meta_to_cache,
    update_meta_timestamp,
)
from meta_morphis.meta.service import get_meta_cards
from meta_morphis.models.meta import MetaEntry


def _counted(monkeypatch: MonkeyPatch, meta: list[MetaEntry] | None) -> list[str]:
    """count_meta_cards counts `meta`, to 2026-11-19, or fails for None;
    returns the formats it counted"""
    asked: list[str] = []

    def fake_count(format_name: str) -> DeckCount | None:
        asked.append(format_name)
        return None if meta is None else DeckCount(meta, date(2026, 11, 19))

    monkeypatch.setattr("meta_morphis.meta.service.count_meta_cards", fake_count)
    return asked


def _saved(conn: sqlite3.Connection, *names: str, at: int | None = None) -> None:
    """A count of these cards saved for Pauper, at `at` (Unix time)"""
    meta = [MetaEntry(name, rank, 0, 0) for rank, name in enumerate(names, start=1)]
    with conn:
        save_meta_to_cache(conn, meta, "pauper")
        update_meta_timestamp(conn, "pauper", date(2026, 11, 1))
        if at is not None:
            conn.execute("UPDATE meta_refresh SET last_updated = ?", (at,))


def test_a_recent_count_is_used_without_counting_again(
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch
) -> None:
    _saved(conn, "Hydroblast")
    asked = _counted(monkeypatch, [MetaEntry("Ponder", 1)])

    result = get_meta_cards(conn, "pauper")

    assert [m.name for m in result] == ["Hydroblast"]
    assert asked == []


def test_an_old_count_is_replaced(
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch
) -> None:
    _saved(conn, "Hydroblast", at=int(time.time()) - 2 * 24 * 60 * 60)
    asked = _counted(monkeypatch, [MetaEntry("Ponder", 1, 40.0, 3.9)])

    result = get_meta_cards(conn, "pauper")

    assert asked == ["pauper"]
    assert result == [MetaEntry("Ponder", 1, 40.0, 3.9)]
    assert get_meta_from_cache(conn, "pauper") == result
    assert abs(time.time() - (get_meta_timestamp(conn, "pauper") or 0)) < 60
    assert get_decks_to(conn, "pauper") == "2026-11-19"


@pytest.mark.parametrize("count", [None, []])
def test_a_failed_or_empty_count_uses_the_last_one(
    conn: sqlite3.Connection,
    monkeypatch: MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    count: list[MetaEntry] | None,
) -> None:
    # None: the archive couldn't be listed; []: it had no decks
    counted_at = int(time.time()) - 2 * 24 * 60 * 60
    _saved(conn, "Hydroblast", at=counted_at)
    _counted(monkeypatch, count)

    result = get_meta_cards(conn, "pauper")

    assert [m.name for m in result] == ["Hydroblast"]
    # Still the old time, so the export can tell how old the count is,
    # and still the day of the old count's newest decks
    assert get_meta_timestamp(conn, "pauper") == counted_at
    assert get_decks_to(conn, "pauper") == "2026-11-01"
    assert "Could not count the pauper decks" in caplog.text


def test_a_failed_count_with_none_before_fails(
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch
) -> None:
    _counted(monkeypatch, None)

    with pytest.raises(RuntimeError, match="pauper decks were never counted"):
        get_meta_cards(conn, "pauper")


# Validated before the cache check, so a leftover row for a format no
# longer in config can't be served silently
@pytest.mark.parametrize("saved", [False, True])
def test_an_unknown_format_fails(
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch, saved: bool
) -> None:
    if saved:
        with conn:
            save_meta_to_cache(conn, [MetaEntry("Brainstorm", 1)], "legacy")
            update_meta_timestamp(conn, "legacy", None)
    asked = _counted(monkeypatch, [MetaEntry("Brainstorm", 1)])

    with pytest.raises(ValueError, match="legacy"):
        get_meta_cards(conn, "legacy")
    assert asked == []


def test_commander_is_ranked_from_scryfalls_card_data(
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch
) -> None:
    asked = _counted(monkeypatch, [MetaEntry("Ponder", 1)])
    read: list[tuple[Path, str, int]] = []

    def fake_ranks(path: Path, format_name: str, limit: int) -> list[MetaEntry]:
        read.append((path, format_name, limit))
        return [MetaEntry("Sol Ring", 1), MetaEntry("Command Tower", 2)]

    monkeypatch.setattr("meta_morphis.meta.service.read_edhrec_ranks", fake_ranks)

    result = get_meta_cards(conn, "commander", Path("cards.jsonl.gz"))

    assert [m.name for m in result] == ["Sol Ring", "Command Tower"]
    assert read == [(Path("cards.jsonl.gz"), "commander", 1000)]
    # Not counted from Magic Online's decklists
    assert asked == []
    assert get_meta_from_cache(conn, "commander") == result
    # Scryfall doesn't say how recent EDHREC's rank is
    assert get_meta_timestamp(conn, "commander") is not None
    assert get_decks_to(conn, "commander") is None


def test_a_card_with_no_numbers_is_saved_too(
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch
) -> None:
    _counted(monkeypatch, [MetaEntry("Weird Row")])

    get_meta_cards(conn, "pauper")

    row = conn.execute(
        "SELECT rank, percent, avg_copies FROM meta WHERE name = ?", ("Weird Row",)
    ).fetchone()
    assert row == (None, None, None)


# Read back through a second connection, which only sees committed data -
# the shared `conn` fixture can't tell whether a write was ever committed
def test_a_new_count_is_committed(db_file: Path, monkeypatch: MonkeyPatch) -> None:
    _counted(monkeypatch, [MetaEntry("Lightning Bolt", 1, 25.0, 3.5)])

    writer = sqlite3.connect(db_file)
    get_meta_cards(writer, "pauper")
    writer.close()

    reader = sqlite3.connect(db_file)
    cached = get_meta_from_cache(reader, "pauper")
    last_updated = get_meta_timestamp(reader, "pauper")
    reader.close()

    assert [m.name for m in cached] == ["Lightning Bolt"]
    assert abs(time.time() - (last_updated or 0)) < 60
