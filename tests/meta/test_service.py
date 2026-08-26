import sqlite3

import pytest
from pytest import MonkeyPatch

from meta_morphis.meta.service import get_meta_cards
from meta_morphis.models.meta import MetaEntry


def test_get_meta_cards_uses_cache(monkeypatch: MonkeyPatch) -> None:
    conn = sqlite3.connect(":memory:")

    monkeypatch.setattr(
        "meta_morphis.meta.service.should_refresh_meta",
        lambda conn, fmt: False
    )
    monkeypatch.setattr(
        "meta_morphis.meta.service.load_cached_meta",
        lambda conn, fmt: [MetaEntry("cached", 0, 0, 0)]
    )

    result = get_meta_cards(conn, "pauper")

    assert [m.name for m in result] == ["cached"]

def test_get_meta_cards_scraper_success(monkeypatch: MonkeyPatch) -> None:
    conn = sqlite3.connect(":memory:")

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

def test_get_meta_cards_scraper_fail_uses_cache(monkeypatch: MonkeyPatch) -> None:
    conn = sqlite3.connect(":memory:")

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
        "meta_morphis.meta.service.load_cached_meta",
        lambda conn, fmt: [MetaEntry("cached-meta", 0, 0, 0)]
    )

    result = get_meta_cards(conn, "pauper")

    assert [m.name for m in result] == ["cached-meta"]

def test_get_meta_cards_scraper_fail_and_no_cache(monkeypatch: MonkeyPatch) -> None:
    conn = sqlite3.connect(":memory:")

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
        "meta_morphis.meta.service.load_cached_meta",
        lambda conn, fmt: []
    )

    with pytest.raises(RuntimeError):
        get_meta_cards(conn, "pauper")