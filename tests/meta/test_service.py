import pytest

from meta_morphis.meta.service import get_meta_cards

def test_get_meta_cards_uses_cache(monkeypatch):
    conn = object()

    monkeypatch.setattr(
        "meta_morphis.meta.service.should_refresh_meta",
        lambda conn, fmt: False
    )
    monkeypatch.setattr(
        "meta_morphis.meta.service.load_cached_meta",
        lambda conn, fmt: ["cached"]
    )

    result = get_meta_cards(conn, "pauper")

    assert result == ["cached"]

def test_get_meta_cards_scraper_success(monkeypatch):
    conn = object()

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
        lambda url: ["new-meta"]
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

    assert result == ["new-meta"]
    assert saved == [["new-meta"]]
    assert updated == ["pauper"]

def test_get_meta_cards_scraper_fail_uses_cache(monkeypatch):
    conn = object()

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
        lambda conn, fmt: ["cached-meta"]
    )

    result = get_meta_cards(conn, "pauper")

    assert result == ["cached-meta"]

def test_get_meta_cards_scraper_fail_and_no_cache(monkeypatch):
    conn = object()

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