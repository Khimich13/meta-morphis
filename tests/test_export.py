import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from pytest import MonkeyPatch

from meta_morphis import config

from meta_morphis.export import build_card, build_export, export_format
from meta_morphis.models.card import Card
from meta_morphis.models.meta import MetaEntry


def _raw(name: str, oracle_id: str = "oid", **extra: Any) -> dict[str, Any]:
    return {
        "id": "id-" + name,
        "oracle_id": oracle_id,
        "name": name,
        "image_uris": {
            "grid": f"{name}.webp",
            "normal": f"{name}.jpg",
            "art": f"{name}-art.webp",
        },
        "artist": "Some Artist",
        **extra,
    }

def test_build_card_single_faced() -> None:
    card = Card.from_raw(_raw("Hydroblast", oracle_id="b94c0336"))
    assert build_card(card) == {
        "oracle_id": "b94c0336",
        "name": "Hydroblast",
        "images": ["Hydroblast.webp"],
        "art": "Hydroblast-art.webp",
        "artist": "Some Artist",
    }

def test_build_card_falls_back_to_jpg_images() -> None:
    card = Card.from_raw(
        _raw("Old Card", image_uris={"normal": "old.jpg", "art_crop": "old-art.jpg"})
    )
    built = build_card(card)
    assert built is not None
    assert built["images"] == ["old.jpg"]
    assert built["art"] == "old-art.jpg"

def test_build_card_double_faced_has_both_pictures() -> None:
    card = Card.from_raw({
        "id": "24c0d87b",
        "oracle_id": "c0957e5e",
        "name": "Fable of the Mirror-Breaker // Reflection of Kiki-Jiki",
        "artist": "Joseph Meehan",
        "card_faces": [
            {"name": "Fable of the Mirror-Breaker", "type_line": "Enchantment — Saga",
             "image_uris": {"grid": "front.webp", "art": "front-art.webp"}},
            {"name": "Reflection of Kiki-Jiki", "type_line": "Enchantment Creature",
             "image_uris": {"grid": "back.webp", "art": "back-art.webp"}},
        ],
    })
    built = build_card(card)
    assert built is not None
    assert built["images"] == ["front.webp", "back.webp"]
    # The artwork asked about is the front side's
    assert built["art"] == "front-art.webp"
    assert built["artist"] == "Joseph Meehan"

def test_build_card_without_id_or_picture_is_left_out() -> None:
    no_id = Card.from_raw({"id": "1", "name": "No Id", "image_uris": {"grid": "x.webp"}})
    no_picture = Card.from_raw({"id": "2", "oracle_id": "oid", "name": "No Picture"})
    assert build_card(no_id) is None
    assert build_card(no_picture) is None

def test_build_card_without_art_or_artist_is_left_out() -> None:
    no_art = Card.from_raw(_raw("No Art", image_uris={"grid": "x.webp"}))
    no_artist = Card.from_raw(_raw("No Artist", artist=None))
    assert build_card(no_art) is None
    assert build_card(no_artist) is None

def test_build_export_sorts_by_name_and_skips_unusable_cards() -> None:
    cards = [
        Card.from_raw(_raw("Pyroblast", oracle_id="p")),
        Card.from_raw({"id": "2", "oracle_id": "x", "name": "No Picture"}),
        Card.from_raw(_raw("Hydroblast", oracle_id="h")),
    ]
    data = build_export("pauper", cards)
    assert data["format"] == "pauper"
    assert [c["name"] for c in data["cards"]] == ["Hydroblast", "Pyroblast"]

def test_export_format_writes_the_file(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    meta = [MetaEntry(name="Lórien Revealed", rank=1)]
    cards = [Card.from_raw(_raw("Lórien Revealed", oracle_id="l"))]
    monkeypatch.setattr("meta_morphis.export.get_meta_cards", lambda conn, name: meta)
    monkeypatch.setattr("meta_morphis.export.fetch_cards", lambda conn, meta: cards)
    monkeypatch.setattr(config, "EXPORT_MIN_CARDS", 1)

    path = export_format(conn, "pauper", tmp_path / "data")

    assert path == tmp_path / "data" / "pauper.json"
    text = path.read_text(encoding="utf-8")
    # Written as real characters, not \u escapes
    assert "Lórien Revealed" in text
    assert json.loads(text) == {
        "format": "pauper",
        "cards": [{
            "oracle_id": "l",
            "name": "Lórien Revealed",
            "images": ["Lórien Revealed.webp"],
            "art": "Lórien Revealed-art.webp",
            "artist": "Some Artist",
        }],
    }

# A failed fetch must not replace the file with an empty or half-empty one
def test_export_format_fails_with_too_few_cards(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    cards = [Card.from_raw(_raw("Hydroblast", oracle_id="h"))]
    monkeypatch.setattr("meta_morphis.export.get_meta_cards", lambda conn, name: [])
    monkeypatch.setattr("meta_morphis.export.fetch_cards", lambda conn, meta: cards)
    monkeypatch.setattr(config, "EXPORT_MIN_CARDS", 2)

    with pytest.raises(RuntimeError, match="Only 1 usable cards"):
        export_format(conn, "pauper", tmp_path / "data")

    assert not (tmp_path / "data" / "pauper.json").exists()
