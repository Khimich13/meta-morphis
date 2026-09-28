import sqlite3

import pytest
from pytest import MonkeyPatch

from meta_morphis.db.init_db import init_db
from meta_morphis.meta.repo import (
    get_meta_from_cache,
    save_meta_to_cache,
    update_meta_timestamp,
)
from meta_morphis.meta.service import get_meta_cards
from meta_morphis.models.meta import MetaEntry


@pytest.fixture
def conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    return conn

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
        "meta_morphis.meta.service.config.FORMATS",
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
        "meta_morphis.meta.service.config.FORMATS",
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
        "meta_morphis.meta.service.config.FORMATS",
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
        "meta_morphis.meta.service.config.FORMATS",
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
        "meta_morphis.meta.service.config.FORMATS",
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