import logging
import sqlite3
import time
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from meta_morphis.meta.repo import (
    get_meta_from_cache,
    save_meta_to_cache,
    update_meta_timestamp,
)
from meta_morphis.meta.service import get_meta_cards, list_changes
from meta_morphis.models.meta import MetaEntry


def test_get_meta_cards_uses_cache(conn: sqlite3.Connection, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "meta_morphis.meta.service.should_refresh_meta",
        lambda conn, fmt: False
    )
    monkeypatch.setattr(
        "meta_morphis.meta.service.get_meta_from_cache",
        lambda conn, fmt: [MetaEntry("cached", 0, 0, 0)]
    )

    result = get_meta_cards(conn, "pauper")

    assert [m.name for m in result] == ["cached"]

def test_get_meta_cards_scraper_success(conn: sqlite3.Connection, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "meta_morphis.meta.service.should_refresh_meta",
        lambda conn, fmt: True
    )

    monkeypatch.setattr(
        "meta_morphis.meta.service.config.GOLDFISH_LIST_URLS",
        {"pauper": "http://fake-url"}
    )

    monkeypatch.setattr(
        "meta_morphis.meta.service.scrape_meta_cards",
        lambda url: [MetaEntry("new-meta", 0, 0, 0)]
    )

    saved = []
    monkeypatch.setattr(
        "meta_morphis.meta.service.save_meta_to_cache",
        lambda conn, meta, fmt: saved.append(meta)
    )

    updated = []
    monkeypatch.setattr(
        "meta_morphis.meta.service.update_meta_timestamp",
        lambda conn, fmt: updated.append(fmt)
    )

    result = get_meta_cards(conn, "pauper")

    assert [m.name for m in result] == ["new-meta"]
    assert saved == [[MetaEntry("new-meta", 0, 0, 0)]]
    assert updated == ["pauper"]

def test_get_meta_cards_saves_rows_with_unparseable_fields(conn: sqlite3.Connection, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "meta_morphis.meta.service.should_refresh_meta",
        lambda conn, fmt: True
    )
    monkeypatch.setattr(
        "meta_morphis.meta.service.config.GOLDFISH_LIST_URLS",
        {"pauper": "http://fake-url"}
    )
    monkeypatch.setattr(
        "meta_morphis.meta.service.scrape_meta_cards",
        lambda url: [MetaEntry("Weird Row")]
    )

    result = get_meta_cards(conn, "pauper")

    assert [m.name for m in result] == ["Weird Row"]

    row = conn.execute(
        "SELECT rank, percent, avg_copies FROM meta WHERE name = ?",
        ("Weird Row",)
    ).fetchone()
    assert row == (None, None, None)

def test_get_meta_cards_scraper_returns_empty_list_uses_cache(conn: sqlite3.Connection, monkeypatch: MonkeyPatch) -> None:
    with conn:
        save_meta_to_cache(conn, [MetaEntry("cached-meta", 1, 10.0, 2.0)], "pauper")
        update_meta_timestamp(conn, "pauper")

    monkeypatch.setattr(
        "meta_morphis.meta.service.should_refresh_meta",
        lambda conn, fmt: True
    )
    monkeypatch.setattr(
        "meta_morphis.meta.service.config.GOLDFISH_LIST_URLS",
        {"pauper": "http://fake-url"}
    )
    monkeypatch.setattr(
        "meta_morphis.meta.service.scrape_meta_cards",
        lambda url: []
    )

    result = get_meta_cards(conn, "pauper")

    assert [m.name for m in result] == ["cached-meta"]
    assert [m.name for m in get_meta_from_cache(conn, "pauper")] == ["cached-meta"]

def test_get_meta_cards_scraper_fail_uses_cache(conn: sqlite3.Connection, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "meta_morphis.meta.service.should_refresh_meta",
        lambda conn, fmt: True
    )

    monkeypatch.setattr(
        "meta_morphis.meta.service.config.GOLDFISH_LIST_URLS",
        {"pauper": "http://fake-url"}
    )

    monkeypatch.setattr(
        "meta_morphis.meta.service.scrape_meta_cards",
        lambda url: None
    )

    monkeypatch.setattr(
        "meta_morphis.meta.service.get_meta_from_cache",
        lambda conn, fmt: [MetaEntry("cached-meta", 0, 0, 0)]
    )

    result = get_meta_cards(conn, "pauper")

    assert [m.name for m in result] == ["cached-meta"]

def test_get_meta_cards_scraper_fail_and_no_cache(conn: sqlite3.Connection, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "meta_morphis.meta.service.should_refresh_meta",
        lambda conn, fmt: True
    )

    monkeypatch.setattr(
        "meta_morphis.meta.service.config.GOLDFISH_LIST_URLS",
        {"pauper": "http://fake-url"}
    )

    monkeypatch.setattr(
        "meta_morphis.meta.service.scrape_meta_cards",
        lambda url: None
    )

    monkeypatch.setattr(
        "meta_morphis.meta.service.get_meta_from_cache",
        lambda conn, fmt: []
    )

    with pytest.raises(RuntimeError):
        get_meta_cards(conn, "pauper")
# An unknown format used to escape as a bare KeyError after the cache check
def test_get_meta_cards_unknown_format_raises(conn: sqlite3.Connection, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "meta_morphis.meta.service.scrape_meta_cards",
        lambda url: pytest.fail("an unknown format must not be scraped")
    )

    with pytest.raises(ValueError, match="legacy"):
        get_meta_cards(conn, "legacy")

# Validation happens before the cache check, so a leftover cache row for a
# format no longer in config can't be served silently
def test_get_meta_cards_unknown_format_raises_even_with_cached_rows(conn: sqlite3.Connection) -> None:
    with conn:
        save_meta_to_cache(conn, [MetaEntry(name="Brainstorm", rank=1)], "legacy")
        update_meta_timestamp(conn, "legacy")

    with pytest.raises(ValueError, match="legacy"):
        get_meta_cards(conn, "legacy")

# Read back through a second connection, which only sees committed data -
# the shared `conn` fixture can't tell whether a write was ever committed
def test_get_meta_cards_commits_scraped_meta(db_file: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "meta_morphis.meta.service.scrape_meta_cards",
        lambda url: [MetaEntry("Lightning Bolt", 1, 25.0, 3.5)]
    )

    writer = sqlite3.connect(db_file)
    get_meta_cards(writer, "pauper")
    writer.close()

    reader = sqlite3.connect(db_file)
    cached = get_meta_from_cache(reader, "pauper")
    last_updated = reader.execute(
        "SELECT last_updated FROM meta_refresh WHERE format = 'pauper'"
    ).fetchone()[0]
    reader.close()

    assert [m.name for m in cached] == ["Lightning Bolt"]
    assert abs(time.time() - last_updated) < 60

def _entries(*names: str) -> list[MetaEntry]:
    return [MetaEntry(name, rank, 0, 0) for rank, name in enumerate(names, start=1)]

def test_list_changes_names_cards_that_entered_and_left() -> None:
    before = _entries("Hydroblast", "Ponder", "Lightning Bolt")
    after = _entries("Hydroblast", "Guttersnipe", "Lightning Bolt", "Writhing Chrysalis")

    assert list_changes(before, after) == (["Guttersnipe", "Writhing Chrysalis"], ["Ponder"])

def test_list_changes_ignores_spelling_and_order() -> None:
    before = _entries("Lorien Revealed", "Hydroblast")
    after = _entries("Hydroblast", "Lórien Revealed")

    assert list_changes(before, after) == ([], [])

def _refresh(monkeypatch: MonkeyPatch, saved: list[MetaEntry], scraped: list[MetaEntry]) -> None:
    monkeypatch.setattr("meta_morphis.meta.service.should_refresh_meta", lambda conn, fmt: True)
    monkeypatch.setattr(
        "meta_morphis.meta.service.config.GOLDFISH_LIST_URLS", {"pauper": "http://fake-url"}
    )
    monkeypatch.setattr("meta_morphis.meta.service.scrape_meta_cards", lambda url: scraped)
    monkeypatch.setattr("meta_morphis.meta.service.get_meta_from_cache", lambda conn, fmt: saved)
    monkeypatch.setattr("meta_morphis.meta.service.save_meta_to_cache", lambda conn, meta, fmt: None)
    monkeypatch.setattr("meta_morphis.meta.service.update_meta_timestamp", lambda conn, fmt: None)

def test_refresh_logs_cards_that_entered_and_left(
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    _refresh(monkeypatch, _entries("Hydroblast", "Ponder"), _entries("Hydroblast", "Guttersnipe"))

    get_meta_cards(conn, "pauper")

    assert "1 card entered the pauper list: Guttersnipe" in caplog.text
    assert "1 card left the pauper list: Ponder" in caplog.text

def test_refresh_logs_an_unchanged_list(
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    _refresh(monkeypatch, _entries("Hydroblast"), _entries("Hydroblast"))

    get_meta_cards(conn, "pauper")

    assert "The pauper list did not change" in caplog.text

def test_first_refresh_logs_no_changes(
    conn: sqlite3.Connection, monkeypatch: MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # Nothing saved yet: every card would count as "entered", which says nothing
    caplog.set_level(logging.INFO)
    _refresh(monkeypatch, [], _entries("Hydroblast", "Ponder"))

    get_meta_cards(conn, "pauper")

    assert "entered" not in caplog.text
    assert "did not change" not in caplog.text
