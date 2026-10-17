import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from pytest import MonkeyPatch

from meta_morphis import config
from meta_morphis.export import build_card, build_export, export_all, export_format
from meta_morphis.models.card import Card
from meta_morphis.models.meta import MetaEntry


def _raw(name: str, oracle_id: str = "oid", **extra: Any) -> dict[str, Any]:
    # Scryfall's picture links carry the printing's id, like these
    printing = "id-" + name
    return {
        "id": printing,
        "oracle_id": oracle_id,
        "name": name,
        "image_uris": {
            "grid": f"grid/{printing}.webp",
            "normal": f"normal/{printing}.jpg",
            "art": f"art/{printing}.webp",
        },
        "artist": "Some Artist",
        **extra,
    }

# 2026-10-17T19:18:03Z, as Unix time
FETCHED = 1792264683

def _list_fetched(monkeypatch: MonkeyPatch, fetched: int | None, now: int = FETCHED + 60) -> None:
    """The MTGGoldfish list was fetched at `fetched`, and it is `now`"""
    monkeypatch.setattr("meta_morphis.export.get_meta_timestamp", lambda conn, name: fetched)
    monkeypatch.setattr("meta_morphis.export.time.time", lambda: now)

def test_build_card_single_faced() -> None:
    card = Card.from_raw(_raw("Hydroblast", oracle_id="b94c0336"))
    assert build_card(card) == {
        "oracle_id": "b94c0336",
        "name": "Hydroblast",
        "images": ["grid/id-Hydroblast.webp"],
        "art": "art/id-Hydroblast.webp",
        "artist": "Some Artist",
    }

def test_build_card_falls_back_to_jpg_images() -> None:
    card = Card.from_raw(
        _raw("Old Card", image_uris={
            "normal": "normal/id-Old Card.jpg",
            "art_crop": "art_crop/id-Old Card.jpg",
        })
    )
    built = build_card(card)
    assert built is not None
    assert built["images"] == ["normal/id-Old Card.jpg"]
    assert built["art"] == "art_crop/id-Old Card.jpg"

def test_build_card_double_faced_has_both_pictures() -> None:
    card = Card.from_raw({
        "id": "24c0d87b",
        "oracle_id": "c0957e5e",
        "name": "Fable of the Mirror-Breaker // Reflection of Kiki-Jiki",
        "artist": "Joseph Meehan",
        "card_faces": [
            {"name": "Fable of the Mirror-Breaker", "type_line": "Enchantment — Saga",
             "image_uris": {"grid": "front/24c0d87b.webp", "art": "art/front/24c0d87b.webp"}},
            {"name": "Reflection of Kiki-Jiki", "type_line": "Enchantment Creature",
             "image_uris": {"grid": "back/24c0d87b.webp", "art": "art/back/24c0d87b.webp"}},
        ],
    })
    built = build_card(card)
    assert built is not None
    assert built["images"] == ["front/24c0d87b.webp", "back/24c0d87b.webp"]
    # The artwork asked about is the front side's
    assert built["art"] == "art/front/24c0d87b.webp"
    assert built["artist"] == "Joseph Meehan"

def test_build_card_without_id_or_picture_is_left_out() -> None:
    no_id = Card.from_raw({"id": "1", "name": "No Id", "image_uris": {"grid": "x.webp"}})
    no_picture = Card.from_raw({"id": "2", "oracle_id": "oid", "name": "No Picture"})
    assert build_card(no_id) is None
    assert build_card(no_picture) is None

def test_build_card_without_art_or_artist_is_left_out() -> None:
    no_art = Card.from_raw(_raw("No Art", image_uris={"grid": "grid/id-No Art.webp"}))
    no_artist = Card.from_raw(_raw("No Artist", artist=None))
    assert build_card(no_art) is None
    assert build_card(no_artist) is None

# The full card shown after answering must be the same printing as the
# artwork in the question
def test_build_card_with_pictures_of_different_printings_is_left_out() -> None:
    mixed = Card.from_raw(_raw("Mixed", image_uris={
        "grid": "grid/id-Mixed.webp",
        "art": "art/another-printing.webp",
    }))
    assert build_card(mixed) is None

def test_build_export_sorts_by_name_and_skips_unusable_cards() -> None:
    cards = [
        Card.from_raw(_raw("Pyroblast", oracle_id="p")),
        Card.from_raw({"id": "2", "oracle_id": "x", "name": "No Picture"}),
        Card.from_raw(_raw("Hydroblast", oracle_id="h")),
    ]
    data = build_export("pauper", cards, "2026-10-17T19:18:03Z")
    assert data["format"] == "pauper"
    assert [c["name"] for c in data["cards"]] == ["Hydroblast", "Pyroblast"]

def test_export_format_writes_the_file(
    conn: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    meta = [MetaEntry(name="Lórien Revealed", rank=1)]
    cards = [Card.from_raw(_raw("Lórien Revealed", oracle_id="l"))]
    monkeypatch.setattr("meta_morphis.export.get_meta_cards", lambda conn, name: meta)
    _list_fetched(monkeypatch, FETCHED)
    monkeypatch.setattr("meta_morphis.export.fetch_cards", lambda conn, meta: cards)
    monkeypatch.setattr("meta_morphis.export.get_display_printing", lambda conn, card: card)
    monkeypatch.setattr(config, "EXPORT_MIN_CARDS", 1)

    caplog.set_level(logging.INFO)
    path = export_format(conn, "pauper", tmp_path / "data")

    assert path == tmp_path / "data" / "pauper.json"
    assert f"Wrote {path}: 1 card" in caplog.text
    text = path.read_text(encoding="utf-8")
    # Written as real characters, not \u escapes
    assert "Lórien Revealed" in text
    assert json.loads(text) == {
        "format": "pauper",
        "list_updated": "2026-10-17T19:18:03Z",
        "cards": [{
            "oracle_id": "l",
            "name": "Lórien Revealed",
            "images": ["grid/id-Lórien Revealed.webp"],
            "art": "art/id-Lórien Revealed.webp",
            "artist": "Some Artist",
        }],
    }

# A failed fetch must not replace the file with an empty or half-empty one
def test_export_format_fails_with_too_few_cards(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    cards = [Card.from_raw(_raw("Hydroblast", oracle_id="h"))]
    monkeypatch.setattr("meta_morphis.export.get_meta_cards", lambda conn, name: [])
    _list_fetched(monkeypatch, FETCHED)
    monkeypatch.setattr("meta_morphis.export.fetch_cards", lambda conn, meta: cards)
    monkeypatch.setattr("meta_morphis.export.get_display_printing", lambda conn, card: card)
    monkeypatch.setattr(config, "EXPORT_MIN_CARDS", 2)

    with pytest.raises(RuntimeError, match="Only 1 usable cards"):
        export_format(conn, "pauper", tmp_path / "data")

    assert not (tmp_path / "data" / "pauper.json").exists()

def test_export_format_uses_the_chosen_printing(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    default = Card.from_raw(_raw("Lightning Bolt", oracle_id="bolt"))
    chosen = Card.from_raw({**_raw("Lightning Bolt", oracle_id="bolt"),
                            "id": "m10",
                            "artist": "Christopher Moeller",
                            "image_uris": {"grid": "grid/m10.webp", "art": "art/m10.webp"}})
    monkeypatch.setattr("meta_morphis.export.get_meta_cards", lambda conn, name: [])
    _list_fetched(monkeypatch, FETCHED)
    monkeypatch.setattr("meta_morphis.export.fetch_cards", lambda conn, meta: [default])
    monkeypatch.setattr("meta_morphis.export.get_display_printing", lambda conn, card: chosen)
    monkeypatch.setattr(config, "EXPORT_MIN_CARDS", 1)

    path = export_format(conn, "pauper", tmp_path)

    [card] = json.loads(path.read_text(encoding="utf-8"))["cards"]
    assert card["images"] == ["grid/m10.webp"]
    assert card["art"] == "art/m10.webp"
    assert card["artist"] == "Christopher Moeller"

@pytest.mark.parametrize("age_days, publishes", [(2, True), (3, True), (4, False)])
def test_export_format_refuses_an_old_list(
    conn: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    age_days: int,
    publishes: bool,
) -> None:
    # A list this old means fetching it has failed for days: fail the run,
    # so GitHub reports it, rather than publish the old list again
    cards = [Card.from_raw(_raw("Hydroblast", oracle_id="h"))]
    monkeypatch.setattr("meta_morphis.export.get_meta_cards", lambda conn, name: [])
    monkeypatch.setattr("meta_morphis.export.fetch_cards", lambda conn, meta: cards)
    monkeypatch.setattr("meta_morphis.export.get_display_printing", lambda conn, card: card)
    monkeypatch.setattr(config, "EXPORT_MIN_CARDS", 1)
    _list_fetched(monkeypatch, FETCHED, now=FETCHED + age_days * 24 * 60 * 60)

    if publishes:
        export_format(conn, "pauper", tmp_path)
        assert (tmp_path / "pauper.json").exists()
    else:
        with pytest.raises(RuntimeError, match="4 days ago - not publishing"):
            export_format(conn, "pauper", tmp_path)
        assert not (tmp_path / "pauper.json").exists()

def test_export_format_fails_without_any_list(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr("meta_morphis.export.get_meta_cards", lambda conn, name: [])
    _list_fetched(monkeypatch, None)

    with pytest.raises(RuntimeError, match="never fetched"):
        export_format(conn, "pauper", tmp_path)

def test_export_all_keeps_going_when_one_format_fails(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    # Modern was exported before and now fails; Standard never worked
    (tmp_path / "modern.json").write_text('{"old": true}', encoding="utf-8")

    def fake_export(conn: sqlite3.Connection, format_name: str, out_dir: Path) -> Path:
        if format_name in ("modern", "standard"):
            raise RuntimeError("MTGGoldfish's page changed")
        path = out_dir / f"{format_name}.json"
        path.write_text("{}", encoding="utf-8")
        return path

    monkeypatch.setattr("meta_morphis.export.export_format", fake_export)

    failed = export_all(conn, ["pauper", "modern", "standard", "pioneer"], tmp_path)

    assert failed == ["modern", "standard"]
    # The formats after the failed ones were still written
    assert (tmp_path / "pioneer.json").exists()
    # Modern keeps its old file
    assert json.loads((tmp_path / "modern.json").read_text(encoding="utf-8")) == {"old": True}
    # Standard has no file, so the app isn't offered it
    formats = json.loads((tmp_path / "formats.json").read_text(encoding="utf-8"))
    assert formats == {"formats": ["pauper", "modern", "pioneer"]}

def test_export_all_reports_no_failures(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    def fake_export(conn: sqlite3.Connection, format_name: str, out_dir: Path) -> Path:
        path = out_dir / f"{format_name}.json"
        path.write_text("{}", encoding="utf-8")
        return path

    monkeypatch.setattr("meta_morphis.export.export_format", fake_export)

    assert export_all(conn, ["pauper", "pioneer"], tmp_path) == []
    formats = json.loads((tmp_path / "formats.json").read_text(encoding="utf-8"))
    assert formats == {"formats": ["pauper", "pioneer"]}
