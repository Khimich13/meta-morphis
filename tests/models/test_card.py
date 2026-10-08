from typing import Any

import pytest

from meta_morphis.models.card import Card


def test_single_face_card() -> None:
    raw = {
        "id": "123",
        "name": "Test Card",
        "mana_cost": "{1}{G}",
        "type_line": "Creature",
    }
    card = Card.from_raw(raw)
    assert card.mana_cost == "{1}{G}"
    assert card.faces == []

def test_dual_face_card() -> None:
    raw: dict[str, Any] = {
        "id": "123",
        "name": "Split Card",
        "card_faces": [
            {"name": "Face A", "mana_cost": "{R}", "type_line": "Instant"},
            {"name": "Face B", "mana_cost": "{G}", "type_line": "Sorcery"},
        ]
    }
    card = Card.from_raw(raw)
    assert len(card.faces) == 2
    assert card.mana_cost == raw["card_faces"][0]["mana_cost"]

def test_missing_mana_cost() -> None:
    raw = {
        "id": "123",
        "name": "Test",
        "type_line": "Creature",
    }
    card = Card.from_raw(raw)
    assert card.mana_cost is None
def test_new_fields_default_when_absent() -> None:
    # Minimal objects, as the cache and service tests build them, must
    # keep parsing - every new field is optional.
    card = Card.from_raw({"id": "1", "name": "Bare"})
    assert card.oracle_id is None
    assert card.layout == "normal"
    assert card.cmc is None
    assert card.color_identity == []
    assert card.keywords == []
    assert card.image_uris is None
    assert card.image_sides() == []
    [face] = card.gameplay_faces()
    assert face.name == "Bare"
    assert face.type_line == ""
    assert face.oracle_text == ""

def test_single_face_card_gameplay_fields() -> None:
    raw: dict[str, Any] = {
        "id": "4c9c9b16",
        "oracle_id": "b94c0336",
        "name": "Hydroblast",
        "layout": "normal",
        "cmc": 1.0,
        "color_identity": ["U"],
        "colors": ["U"],
        "keywords": [],
        "mana_cost": "{U}",
        "type_line": "Instant",
        "oracle_text": "Choose one —\n• Counter target spell if it's red.",
        "artist": "Lake Hurwitz",
        "scryfall_uri": "https://scryfall.com/card/ema/55/hydroblast",
        "image_uris": {"grid": "front.webp", "art": "art.webp"},
    }
    card = Card.from_raw(raw)
    assert card.oracle_id == "b94c0336"
    assert card.cmc == 1.0
    assert card.faces == []

    [face] = card.gameplay_faces()
    assert face.name == "Hydroblast"
    assert face.mana_cost == "{U}"
    assert face.oracle_text == raw["oracle_text"]
    assert face.colors == ["U"]
    assert face.artist == "Lake Hurwitz"

    [side] = card.image_sides()
    assert side.image_uris == raw["image_uris"]
    assert side.artist == "Lake Hurwitz"

def test_transform_card_has_an_image_side_per_face() -> None:
    raw: dict[str, Any] = {
        "id": "24c0d87b",
        "name": "Fable of the Mirror-Breaker // Reflection of Kiki-Jiki",
        "layout": "transform",
        "type_line": "Enchantment — Saga // Enchantment Creature — Goblin Shaman",
        "artist": "Joseph Meehan",
        "card_faces": [
            {"name": "Fable of the Mirror-Breaker", "mana_cost": "{2}{R}",
             "type_line": "Enchantment — Saga", "colors": ["R"],
             "image_uris": {"grid": "front.webp"}},
            {"name": "Reflection of Kiki-Jiki", "mana_cost": "",
             "type_line": "Enchantment Creature — Goblin Shaman", "colors": ["R"],
             "power": "2", "toughness": "2",
             "image_uris": {"grid": "back.webp"}},
        ],
    }
    card = Card.from_raw(raw)
    front, back = card.gameplay_faces()
    assert back.mana_cost is None
    assert (back.power, back.toughness) == ("2", "2")
    # Face without its own artist falls back to the card's
    assert front.artist == "Joseph Meehan"

    sides = card.image_sides()
    assert [s.image_uris["grid"] for s in sides] == ["front.webp", "back.webp"]
    assert all(s.artist == "Joseph Meehan" for s in sides)

def test_split_card_has_one_image_side_and_face_colors_fall_back() -> None:
    raw: dict[str, Any] = {
        "id": "room",
        "name": "Unholy Annex // Ritual Chamber",
        "layout": "split",
        "colors": ["B"],
        "artist": "Some Artist",
        "image_uris": {"grid": "room.webp"},
        "card_faces": [
            {"name": "Unholy Annex", "mana_cost": "{2}{B}", "type_line": "Enchantment — Room"},
            {"name": "Ritual Chamber", "mana_cost": "{3}{B}{B}", "type_line": "Enchantment — Room"},
        ],
    }
    card = Card.from_raw(raw)
    assert [f.colors for f in card.gameplay_faces()] == [["B"], ["B"]]
    [side] = card.image_sides()
    assert side.image_uris == {"grid": "room.webp"}
    assert side.artist == "Some Artist"

def test_face_missing_type_line_is_still_malformed() -> None:
    raw: dict[str, Any] = {
        "id": "1", "name": "Broken",
        "card_faces": [{"name": "Broken"}],
    }
    with pytest.raises(KeyError):
        Card.from_raw(raw)
