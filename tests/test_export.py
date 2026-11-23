import errno
import io
import json
import logging
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from PIL import Image, ImageDraw
from pytest import MonkeyPatch

from meta_morphis import config, name_in_text
from meta_morphis.export import (
    BackSide,
    ExportCard,
    _bulk_file_is_old,
    art_box,
    back_side,
    build_card,
    build_every_card,
    build_export,
    card_kind,
    cost_part,
    creature_type,
    export_all,
    export_every_card,
    export_format,
    face_of,
    horizontal_sides,
    image_urls,
    is_basic_land,
    list_changes,
    main_type,
    measure_new_symbols,
    name_boxes,
    pick_cards,
    power_toughness,
    read_new_pictures,
    report_left_out,
    shown_name,
    sides_to_read,
    spell_part,
    split_halves,
    title_name_box,
    write_json,
)
from meta_morphis.models.card import Card
from meta_morphis.models.meta import MetaEntry
from meta_morphis.name_in_text import READER_VERSION, NameInText, ReadText
from meta_morphis.set_symbols import SetSymbols
from meta_morphis.utils.text import normalize_name


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
            "large": f"large/{printing}.jpg",
            "art": f"art/{printing}.webp",
        },
        "artist": "Some Artist",
        "frame": "2015",
        **extra,
    }


# 2026-10-17T19:18:03Z, as Unix time
FETCHED = 1792264683


def _list_fetched(
    monkeypatch: MonkeyPatch, fetched: int | None, now: int = FETCHED + 60
) -> None:
    """The format's decks were counted at `fetched`, and it is `now`"""
    monkeypatch.setattr(
        "meta_morphis.export.get_meta_timestamp", lambda conn, name: fetched
    )
    monkeypatch.setattr("meta_morphis.export.time.time", lambda: now)


def test_build_card_single_faced() -> None:
    card = Card.from_raw(_raw("Hydroblast", oracle_id="b94c0336", type_line="Instant"))
    expected: ExportCard = {
        "oracle_id": "b94c0336",
        "name": "Hydroblast",
        "images": ["grid/id-Hydroblast.webp"],
        "large_images": ["large/id-Hydroblast.jpg"],
        "art_box": [0.079, 0.114, 0.840, 0.440],
        "name_box": None,
        "name_text_boxes": [],
        "art": "art/id-Hydroblast.webp",
        "artist": "Some Artist",
        "art_from": None,
        "horizontal": [False],
        "back": None,
        "spell": None,
        "halves": None,
        "type": "instant",
        "cost": None,
        "power_toughness": None,
        "creature_type": None,
    }
    assert build_card(card) == expected


def test_build_card_falls_back_to_jpg_images() -> None:
    card = Card.from_raw(
        _raw(
            "Old Card",
            image_uris={
                "normal": "normal/id-Old Card.jpg",
                "art_crop": "art_crop/id-Old Card.jpg",
            },
        )
    )
    built = build_card(card)
    assert built is not None
    assert built["images"] == ["normal/id-Old Card.jpg"]
    assert built["art"] == "art_crop/id-Old Card.jpg"
    # No large picture: the app zooms into the normal one
    assert built["large_images"] == []


def test_build_card_double_faced_has_both_pictures() -> None:
    card = Card.from_raw(
        {
            "id": "24c0d87b",
            "oracle_id": "c0957e5e",
            "name": "Fable of the Mirror-Breaker // Reflection of Kiki-Jiki",
            "artist": "Joseph Meehan",
            "card_faces": [
                {
                    "name": "Fable of the Mirror-Breaker",
                    "type_line": "Enchantment — Saga",
                    "image_uris": {
                        "grid": "front/24c0d87b.webp",
                        "large": "large/front/24c0d87b.jpg",
                        "art": "art/front/24c0d87b.webp",
                    },
                },
                {
                    "name": "Reflection of Kiki-Jiki",
                    "type_line": "Enchantment Creature",
                    "image_uris": {
                        "grid": "back/24c0d87b.webp",
                        "large": "large/back/24c0d87b.jpg",
                        "art": "art/back/24c0d87b.webp",
                    },
                },
            ],
        }
    )
    built = build_card(card)
    assert built is not None
    assert built["images"] == ["front/24c0d87b.webp", "back/24c0d87b.webp"]
    assert built["large_images"] == [
        "large/front/24c0d87b.jpg",
        "large/back/24c0d87b.jpg",
    ]
    # The artwork asked about is the front side's, or the back's
    assert built["art"] == "art/front/24c0d87b.webp"
    assert built["artist"] == "Joseph Meehan"
    assert built["back"] == {
        "art": "art/back/24c0d87b.webp",
        "artist": "Joseph Meehan",
        # Not a layout whose back is measured
        "art_box": None,
        "art_from": None,
        "name_box": None,
        "name_text_boxes": [],
        "type": "creature",
    }
    # The question about the front's full picture names the front's type
    assert built["type"] == "enchantment"


def _double_faced(layout: str, back: dict[str, Any], **extra: Any) -> Card:
    return Card.from_raw(
        {
            **_raw("Front // Back", layout=layout, **extra),
            "card_faces": [
                {
                    "name": "Front",
                    "type_line": "Creature — Human",
                    "artist": "Front Artist",
                    "image_uris": {
                        "grid": "front/id-Front // Back.webp",
                        "art": "art/front/id-Front // Back.webp",
                    },
                },
                {
                    "name": "Back",
                    "type_line": "Creature — Horror",
                    "artist": "Back Artist",
                    "image_uris": {
                        "grid": "back/id-Front // Back.webp",
                        "art": "art/back/id-Front // Back.webp",
                    },
                    **back,
                },
            ],
        }
    )


def test_the_back_side_has_its_own_artwork_artist_and_art_box() -> None:
    back = back_side(
        _double_faced("transform", {}, lang="en", released_at="2021-09-24")
    )
    expected: BackSide = {
        "art": "art/back/id-Front // Back.webp",
        "artist": "Back Artist",
        "art_box": [0.079, 0.114, 0.840, 0.440],
        "art_from": None,
        # Its icon on the right, as without a frame effect for one on the
        # left
        "name_box": [0.08, 0.052, 0.75, 0.051],
        "name_text_boxes": [],
        "type": "creature",
    }
    assert back == expected
    # The back's own kind of card: a saga creature, like Summon: Esper
    # Maduin, or a planeswalker, like Ajani, Nacatl Avenger
    saga = back_side(
        _double_faced(
            "transform", {"type_line": "Enchantment Creature — Saga Elemental"}
        )
    )
    walker = back_side(
        _double_faced(
            "transform",
            {"type_line": "Legendary Planeswalker — Ajani", "oracle_text": "+1: X"},
        )
    )
    assert saga and saga["art_box"] == [0.502, 0.208, 0.419, 0.548]
    assert walker and walker["art_box"] == [0.072, 0.101, 0.850, 0.451]
    assert saga["type"] == "creature"
    assert walker["type"] == "planeswalker"
    # A modal double-faced card's back has the usual art box too
    modal = back_side(_double_faced("modal_dfc", {"type_line": "Land"}))
    assert modal and modal["art_box"] == [0.079, 0.114, 0.840, 0.440]
    assert modal["type"] == "land"


def test_summon_esper_maduin_is_cut_from_its_large_picture() -> None:
    # Scryfall's artwork of it has text above and below
    esper = _double_faced(
        "transform",
        {
            "name": "Summon: Esper Maduin",
            "type_line": "Enchantment Creature — Saga Elemental",
            "image_uris": {
                "grid": "back/id-Front // Back.webp",
                "large": "large/back/id-Front // Back.jpg",
                "art": "art/back/id-Front // Back.webp",
            },
        },
    )
    back = back_side(esper)
    assert back and back["art_from"] == {
        "picture": "large/back/id-Front // Back.jpg",
        "box": [0.502, 0.208, 0.419, 0.548],
    }
    # Scryfall's artwork stays, for when the app can't cut its own
    assert back["art"] == "art/back/id-Front // Back.webp"
    # Another saga creature keeps Scryfall's artwork alone
    other = back_side(
        _double_faced(
            "transform",
            {
                "type_line": "Enchantment Creature — Saga Elemental",
                "image_uris": {
                    "grid": "back/id-Front // Back.webp",
                    "large": "large/back/id-Front // Back.jpg",
                    "art": "art/back/id-Front // Back.webp",
                },
            },
        )
    )
    assert other and other["art_from"] is None


def test_summon_esper_maduin_is_named_without_summon() -> None:
    assert shown_name("Esper Origins // Summon: Esper Maduin") == (
        "Esper Origins // Esper Maduin"
    )
    # Every other name stays as it is
    assert shown_name("Fable of the Mirror-Breaker // Reflection of Kiki-Jiki") == (
        "Fable of the Mirror-Breaker // Reflection of Kiki-Jiki"
    )
    assert shown_name("Summon: Bahamut") == "Summon: Bahamut"


def test_no_art_box_on_a_battles_back() -> None:
    back = back_side(_double_faced("battle", {}))
    assert back and back["art_box"] is None


def test_no_back_side_without_its_artwork_or_artist_or_of_another_printing() -> None:
    no_art = _double_faced(
        "transform", {"image_uris": {"grid": "back/id-Front // Back.webp"}}
    )
    # A face without an artist takes the card's, so neither has one
    no_artist = _double_faced("transform", {"artist": None}, artist=None)
    other = _double_faced("transform", {"image_uris": {"art": "art/back/other.webp"}})
    assert back_side(no_art) is None
    assert back_side(no_artist) is None
    assert back_side(other) is None
    # The card itself is still asked by its front
    built = build_card(no_art)
    assert built is not None and built["back"] is None


def test_build_card_large_pictures_all_sides_or_none() -> None:
    # A back side without a large picture: none at all, never mixed sizes
    card = Card.from_raw(
        {
            "id": "x1",
            "oracle_id": "x",
            "name": "Front // Back",
            "artist": "A",
            "card_faces": [
                {
                    "name": "Front",
                    "type_line": "Creature",
                    "image_uris": {
                        "grid": "front/x1.webp",
                        "large": "large/front/x1.jpg",
                        "art": "art/front/x1.webp",
                    },
                },
                {
                    "name": "Back",
                    "type_line": "Creature",
                    "image_uris": {"grid": "back/x1.webp"},
                },
            ],
        }
    )
    built = build_card(card)
    assert built is not None
    assert built["large_images"] == []


@pytest.mark.parametrize(
    "frame, box",
    [
        ("1993", [0.113, 0.094, 0.781, 0.449]),
        ("1997", [0.119, 0.100, 0.764, 0.443]),
        ("2003", [0.088, 0.119, 0.826, 0.435]),
        ("2015", [0.079, 0.114, 0.840, 0.440]),
    ],
)
def test_art_box_follows_the_frame(frame: str, box: list[float]) -> None:
    assert art_box(Card.from_raw(_raw("Card", frame=frame, type_line="Instant"))) == box


def test_art_box_of_sagas_classes_and_planeswalkers() -> None:
    saga = Card.from_raw(
        _raw("Urza's Saga", layout="saga", type_line="Enchantment Land — Urza's Saga")
    )
    talent = Card.from_raw(
        _raw("Stormchaser's Talent", layout="class", type_line="Enchantment — Class")
    )
    short = Card.from_raw(
        _raw(
            "Teferi",
            type_line="Legendary Planeswalker — Teferi",
            oracle_text="Static.\n+1: One.\n−3: Two.",
        )
    )
    long = Card.from_raw(
        _raw(
            "Jace",
            type_line="Legendary Planeswalker — Jace",
            oracle_text="Static.\n+1: One.\n−1: Two.\n−8: Three.",
        )
    )
    assert art_box(saga) == [0.502, 0.113, 0.418, 0.724]
    assert art_box(talent) == [0.076, 0.113, 0.418, 0.724]
    assert art_box(short) == [0.072, 0.101, 0.850, 0.451]
    assert art_box(long) == [0.073, 0.101, 0.849, 0.382]


def test_art_box_of_a_double_faced_saga_is_its_front_side() -> None:
    fable = Card.from_raw(
        {
            **_raw(
                "Fable of the Mirror-Breaker // Reflection of Kiki-Jiki",
                layout="transform",
            ),
            "card_faces": [
                {
                    "name": "Fable of the Mirror-Breaker",
                    "type_line": "Enchantment — Saga",
                },
                {
                    "name": "Reflection of Kiki-Jiki",
                    "type_line": "Enchantment Creature — Goblin",
                },
            ],
        }
    )
    assert art_box(fable) == [0.502, 0.113, 0.418, 0.724]


def test_no_art_box_without_a_single_measured_one() -> None:
    split = Card.from_raw(
        _raw("Wear // Tear", layout="split", type_line="Instant // Instant")
    )
    future = Card.from_raw(_raw("Future Card", frame="future", type_line="Creature"))
    old_walker = Card.from_raw(
        _raw("Old Walker", frame="1997", type_line="Planeswalker — Someone")
    )
    unknown = Card.from_raw(
        _raw("New Layout", layout="something_new", type_line="Creature")
    )
    assert art_box(split) is None
    assert art_box(future) is None
    assert art_box(old_walker) is None
    assert art_box(unknown) is None


def _english(name: str, **extra: Any) -> Card:
    return Card.from_raw(_raw(name, lang="en", type_line="Instant", **extra))


@pytest.mark.parametrize(
    "frame, box",
    [
        ("1993", [0.075, 0.033, 0.823, 0.058]),
        ("1997", [0.085, 0.048, 0.813, 0.046]),
        ("2003", [0.08, 0.05, 0.818, 0.054]),
        ("2015", [0.08, 0.052, 0.828, 0.051]),
    ],
)
def test_name_box_follows_the_frame(frame: str, box: list[float]) -> None:
    # A land: no mana cost, so the name's area runs to near the bar's end
    card = _english("Ice Tunnel", frame=frame, oracle_text="Tap: Add one mana.")
    assert title_name_box(card) == box


def test_name_box_ends_before_the_mana_cost() -> None:
    # Three symbols of 0.0515, and the gap of 0.02, before 0.928
    card = _english(
        "Lórien Revealed", mana_cost="{3}{U}{U}", oracle_text="Draw three cards."
    )
    assert title_name_box(card) == [0.08, 0.052, 0.6735, 0.051]


def test_name_box_starts_after_an_icon() -> None:
    lesson = _english("Firebending Lesson", mana_cost="{R}", frame_effects=["lesson"])
    tombstone = _english("Lava Dart", frame="1997", frame_effects=["tombstone"])
    assert title_name_box(lesson) == [0.165, 0.052, 0.6915, 0.051]
    assert title_name_box(tombstone) == [0.105, 0.048, 0.793, 0.046]


TITLE = [0.08, 0.052, 0.828, 0.051]
IN_TEXT = [[0.1, 0.7, 0.2, 0.03]]


class _ReadAs:
    """Reads every picture with the same result, and remembers which"""

    def __init__(self, boxes: list[list[float]] | None) -> None:
        self.boxes = boxes
        self.cards: list[str] = []

    def __call__(self, card: Card) -> list[list[float]] | None:
        self.cards.append(card.name)
        return self.boxes


def test_the_name_in_the_text_is_covered_where_the_picture_shows_it() -> None:
    # In the rules text, in the flavor text, in lower case, or a legend's
    # short name
    in_text = _english(
        "Lava Dart", oracle_text="Lava Dart deals 1 damage to any target."
    )
    in_flavor = _english("Annul", flavor_text="Annul it all.")
    lower_case = _english(
        "Birds of Paradise",
        flavor_text="Long ago, birds of paradise littered the skies.",
    )
    legend = _english(
        "Ragavan, Nimble Pilferer",
        oracle_text="Whenever Ragavan deals combat damage, create a Treasure.",
    )
    for card in (in_text, in_flavor, lower_case, legend):
        assert name_boxes(card, _ReadAs(IN_TEXT)) == (title_name_box(card), IN_TEXT)
        # Not found everywhere for sure, or not read at all: not asked
        assert name_boxes(card, _ReadAs(None)) == (None, [])
        assert name_boxes(card) == (None, [])


def test_the_text_is_read_only_when_it_may_show_the_name() -> None:
    plain = _english("Counterspell", oracle_text="Counter target spell.")
    read = _ReadAs(IN_TEXT)
    assert name_boxes(plain, read) == (TITLE, [])
    assert read.cards == []


def test_a_planeswalkers_picture_is_always_read() -> None:
    # Its text never names it, but its type line does: "— Teferi"
    teferi = Card.from_raw(
        _raw(
            "Teferi, Time Raveler",
            lang="en",
            mana_cost="{1}{W}{U}",
            type_line="Legendary Planeswalker — Teferi",
            oracle_text="Each opponent can cast spells only as a sorcery.",
        )
    )
    read = _ReadAs(IN_TEXT)
    assert name_boxes(teferi, read) == (title_name_box(teferi), IN_TEXT)
    assert read.cards == ["Teferi, Time Raveler"]
    # Not read, or not for sure: not asked
    assert name_boxes(teferi) == (None, [])


def test_a_planeswalkers_text_is_read_from_its_artworks_bottom() -> None:
    for lines, top in (
        (3, name_in_text.PLANESWALKER_TEXT_TOP),
        (4, name_in_text.PLANESWALKER_LONG_TEXT_TOP),
    ):
        walker = Card.from_raw(
            _raw(
                "Teferi, Time Raveler",
                lang="en",
                type_line="Legendary Planeswalker — Teferi",
                oracle_text="\n".join(["Draw a card."] * lines),
            )
        )
        box = art_box(walker)
        assert box is not None
        assert round(box[1] + box[3], 3) == top
        assert name_in_text.areas_to_read(walker)[0][1] == top


def test_the_text_is_read_for_a_word_of_the_name_in_the_flavor_text() -> None:
    # "Lórien" alone, with its accent and in the possessive, or a plural
    lorien = _english(
        "Lórien Revealed",
        oracle_text="Draw three cards.",
        flavor_text="Lórien's trees hide the Naith.",
    )
    frog = _english("Psychic Frog", flavor_text="Frogs croak.")
    # Only "of", too short to tell anything
    relic = _english("Relic of Progenitus", flavor_text="Made of bone.")
    read = _ReadAs([])
    for card in (lorien, frog, relic):
        name_boxes(card, read)
    assert read.cards == ["Lórien Revealed", "Psychic Frog"]


def test_the_text_is_read_for_an_old_printing_that_refers_to_itself() -> None:
    # Printed with its name where the Oracle text now says "this land"
    old = _english(
        "Volatile Fjord",
        oracle_text="This land enters tapped.",
        released_at="2021-02-05",
        set_type="expansion",
    )
    # A reprint keeps its old text, however new
    reprint = _english(
        "Baleful Strix",
        oracle_text="When this creature enters, draw a card.",
        released_at="2026-10-19",
        set_type="masters",
    )
    new = _english(
        "Seam Rip",
        oracle_text="When this enchantment enters, exile a card.",
        released_at="2025-08-01",
        set_type="expansion",
    )
    read = _ReadAs([])
    assert name_boxes(old, read) == (TITLE, [])
    assert name_boxes(reprint, read) == (TITLE, [])
    assert name_boxes(new, read) == (TITLE, [])
    assert read.cards == ["Volatile Fjord", "Baleful Strix"]


def test_the_text_is_read_for_a_summon_type_line() -> None:
    # "Summon Ball Lightning": an old creature's type line could be its name
    old = Card.from_raw(
        _raw(
            "Ball Lightning",
            lang="en",
            type_line="Creature — Elemental",
            released_at="1997-03-24",
            oracle_text="Trample",
        )
    )
    new = Card.from_raw(
        _raw(
            "Ball Lightning",
            lang="en",
            type_line="Creature — Elemental",
            released_at="2010-07-16",
            oracle_text="Trample",
        )
    )
    read = _ReadAs([])
    name_boxes(old, read)
    name_boxes(new, read)
    assert read.cards == ["Ball Lightning"]


def test_a_keyword_reminder_that_refers_to_itself_needs_no_reading() -> None:
    # A keyword's reminder text is printed "this card" on old printings too
    looting = _english(
        "Faithless Looting",
        keywords=["Flashback"],
        released_at="2019-06-14",
        set_type="masters",
        oracle_text="Draw two cards, then discard two cards.\n"
        "Flashback {2}{R} (You may cast this card from your graveyard for its "
        "flashback cost. Then exile it.)",
    )
    # Other reminder text may print the name
    arbor = _english(
        "Dryad Arbor",
        released_at="2024-08-02",
        set_type="masters",
        oracle_text="(This land isn't a spell, it's affected by summoning sickness, "
        'and it has "{T}: Add {G}.")',
    )
    assert name_boxes(looting) == (TITLE, [])
    assert name_boxes(arbor) == (None, [])


def test_a_saga_class_or_case_has_a_name_box_like_a_normal_card() -> None:
    for layout in ("saga", "class", "case"):
        assert title_name_box(_english("Some Card", layout=layout)) == TITLE


def test_the_text_is_read_for_a_class_or_case_that_refers_to_itself() -> None:
    # Printed "When Stormchaser's Talent enters" before Foundations
    talent = _english(
        "Stormchaser's Talent",
        layout="class",
        oracle_text="When this Class enters, create a token.",
        released_at="2024-08-02",
        set_type="expansion",
    )
    case = _english(
        "Case of the Uneaten Feast",
        layout="case",
        oracle_text="Solved — Sacrifice this Case: Return a creature card.",
        released_at="2024-02-09",
        set_type="expansion",
    )
    read = _ReadAs(IN_TEXT)
    for card in (talent, case):
        assert name_boxes(card, read) == (TITLE, IN_TEXT)
    assert read.cards == ["Stormchaser's Talent", "Case of the Uneaten Feast"]


def test_the_type_line_of_a_saga_is_read_when_it_has_a_word_of_the_name() -> None:
    # However new the printing: the name is in its type line
    urzas = Card.from_raw(
        _raw(
            "Urza's Saga",
            lang="en",
            layout="saga",
            type_line="Enchantment Land — Urza's Saga",
            oracle_text="I — This Saga gains an ability.",
            released_at="2030-01-01",
            set_type="expansion",
        )
    )
    other = _english(
        "The Misty Mountains Cold",
        layout="saga",
        oracle_text="I — Sacrifice this Saga.",
        released_at="2030-01-01",
        set_type="expansion",
    )
    read = _ReadAs(IN_TEXT)
    assert name_boxes(urzas, read) == (TITLE, IN_TEXT)
    assert name_boxes(other, read) == (TITLE, [])
    assert read.cards == ["Urza's Saga"]


def _transform(front: dict[str, Any], **extra: Any) -> Card:
    return Card.from_raw(
        {
            **_raw("Front // Back", lang="en", layout="transform", **extra),
            "card_faces": [
                {"type_line": "Creature — Human", **front},
                {"name": "Back", "type_line": "Creature — Horror"},
            ],
        }
    )


def test_a_transform_card_is_asked_by_its_front() -> None:
    # Its name starts after the icon, and ends before the front's mana cost
    delver = _transform(
        {
            "name": "Delver of Secrets",
            "mana_cost": "{U}",
            "oracle_text": "Transform this creature.",
        },
        released_at="2025-01-24",
        set_type="masters",
    )
    read = _ReadAs(IN_TEXT)
    assert name_boxes(delver, read) == ([0.16, 0.052, 0.6965, 0.051], IN_TEXT)
    # Read for the front's own name, on the front's picture
    assert read.cards == ["Delver of Secrets"]


def test_a_transform_card_is_read_for_its_front_text_only() -> None:
    plain = _transform(
        {"name": "Plain Front", "oracle_text": "Flying"}, released_at="2021-09-24"
    )
    read = _ReadAs(IN_TEXT)
    assert name_boxes(plain, read) == ([0.16, 0.052, 0.748, 0.051], [])
    assert read.cards == []


def test_a_transform_cards_back_is_asked_by_its_own_name() -> None:
    # Delver of Secrets' back: its icon on the right, where a mana cost
    # would be, and the name where a normal card's starts
    delver = _transform(
        {"name": "Delver of Secrets", "mana_cost": "{U}"},
        released_at="2021-09-24",
    )
    read = _ReadAs(IN_TEXT)
    assert name_boxes(delver, read, side=1) == ([0.08, 0.052, 0.75, 0.051], [])
    # A sun and moon on the left, as on its front: the name starts after
    # it, and runs to the title bar's end
    glutton = _transform(
        {"name": "Graveyard Trespasser"},
        frame_effects=["sunmoondfc"],
        released_at="2021-09-24",
    )
    assert name_boxes(glutton, read, side=1) == ([0.16, 0.052, 0.748, 0.051], [])
    assert read.cards == []


def test_a_transform_cards_back_is_read_for_its_own_text() -> None:
    # Older than "this creature" printed as the Oracle text says it
    card = Card.from_raw(
        {
            **_raw("Front // Back", lang="en", layout="transform"),
            "released_at": "2021-09-24",
            "card_faces": [
                {"name": "Front", "type_line": "Creature — Human"},
                {
                    "name": "Back",
                    "type_line": "Creature — Horror",
                    "oracle_text": "Whenever this creature attacks, draw a card.",
                },
            ],
        }
    )
    read = _ReadAs(IN_TEXT)
    assert name_boxes(card, read, side=1) == ([0.08, 0.052, 0.75, 0.051], IN_TEXT)
    assert read.cards == ["Back"]


def _modal(front: dict[str, Any], back: dict[str, Any]) -> Card:
    return Card.from_raw(
        {
            **_raw("Front // Back", lang="en", layout="modal_dfc"),
            "released_at": "2024-06-14",
            "set_type": "draft_innovation",
            "card_faces": [
                {"name": "Front", "type_line": "Instant", **front},
                {"name": "Back", "type_line": "Land", **back},
            ],
        }
    )


def test_a_modal_double_faced_card_is_asked_by_either_side() -> None:
    # Sink into Stupor // Soporific Springs: each side's name starts after
    # the icon on the left, and is read for in its own text only
    sink = _modal(
        {
            "name": "Sink into Stupor",
            "mana_cost": "{1}{U}{U}",
            "oracle_text": "Return target spell to its owner's hand.",
        },
        {"name": "Soporific Springs", "oracle_text": "{T}: Add {U}."},
    )
    read = _ReadAs(IN_TEXT)
    assert name_boxes(sink, read) == ([0.16, 0.052, 0.5935, 0.051], [])
    assert name_boxes(sink, read, side=1) == ([0.16, 0.052, 0.748, 0.051], [])
    assert read.cards == []


def test_a_modal_double_faced_cards_sides_are_read_for_their_own_names() -> None:
    walters = _modal(
        {"name": "Jennifer Walters", "oracle_text": "Transform Jennifer Walters."},
        {"name": "The Sensational She-Hulk", "oracle_text": "Reach"},
    )
    read = _ReadAs(IN_TEXT)
    assert name_boxes(walters, read) == ([0.16, 0.052, 0.748, 0.051], IN_TEXT)
    assert name_boxes(walters, read, side=1) == ([0.16, 0.052, 0.748, 0.051], [])
    assert read.cards == ["Jennifer Walters"]


def test_a_battles_back_is_never_asked_by_its_picture() -> None:
    battle = _double_faced("battle", {}, lang="en")
    assert name_boxes(battle, side=1) == (None, [])


def test_a_transform_saga_is_read_as_a_saga() -> None:
    fable = face_of(
        _transform(
            {"name": "Fable of the Mirror-Breaker", "type_line": "Enchantment — Saga"}
        ),
        0,
    )
    assert fable.layout == "saga"
    assert fable.name == "Fable of the Mirror-Breaker"


def test_a_planeswalkers_name_box_is_higher_and_thinner() -> None:
    # Three symbols of 0.0485, and the gap of 0.02, before 0.921
    walker = Card.from_raw(
        _raw(
            "Teferi, Time Raveler",
            lang="en",
            mana_cost="{1}{W}{U}",
            type_line="Legendary Planeswalker — Teferi",
        )
    )
    assert title_name_box(walker) == [0.072, 0.042, 0.6835, 0.04]


def test_no_name_box_for_more_than_one_name_another_language_or_frame() -> None:
    adventure = _english("Bonecrusher Giant // Stomp", layout="adventure")
    french = Card.from_raw(_raw("Triskelion", lang="fr", type_line="Artifact Creature"))
    future = _english("Future Card", frame="future")
    # Only the modern frame's planeswalkers are measured
    old_walker = Card.from_raw(
        _raw(
            "Garruk Wildspeaker",
            lang="en",
            frame="2003",
            type_line="Legendary Planeswalker — Garruk",
        )
    )
    assert title_name_box(old_walker) is None
    assert title_name_box(adventure) is None
    assert title_name_box(french) is None
    assert title_name_box(future) is None


def test_the_cost_box_runs_from_its_first_symbol_to_the_bars_end() -> None:
    # Three symbols of 0.0515 before 0.928, 0.01 more on the left for the
    # shadow and 0.004 on the right for the rim
    card = _english("Lórien Revealed", mana_cost="{3}{U}{U}")
    assert cost_part(card) == {
        "mana_cost": "{3}{U}{U}",
        "box": [0.7635, 0.052, 0.1685, 0.051],
    }


def test_a_planeswalkers_cost_box_is_higher_and_thinner() -> None:
    # Three symbols of 0.0485 before 0.921, and the same room around
    walker = Card.from_raw(
        _raw(
            "Teferi, Time Raveler",
            mana_cost="{1}{W}{U}",
            type_line="Legendary Planeswalker — Teferi",
        )
    )
    assert cost_part(walker) == {
        "mana_cost": "{1}{W}{U}",
        "box": [0.7655, 0.042, 0.1595, 0.04],
    }


def test_a_cost_of_zero_is_asked_about() -> None:
    ornithopter = _english("Ornithopter", mana_cost="{0}")
    assert cost_part(ornithopter) == {
        "mana_cost": "{0}",
        "box": [0.8665, 0.052, 0.0655, 0.051],
    }


def test_the_1997_frames_cost_has_its_own_measures() -> None:
    # Three symbols of 0.052 before 0.926 - not the name's 0.046 and 0.918
    card = _english("Hypnotic Specter", mana_cost="{1}{B}{B}", frame="1997")
    assert cost_part(card) == {
        "mana_cost": "{1}{B}{B}",
        "box": [0.76, 0.048, 0.17, 0.046],
    }
    assert title_name_box(card) == [0.085, 0.048, 0.675, 0.046]


def test_no_cost_without_one_or_with_more_than_one_or_in_a_frame_not_measured() -> None:
    land = _english("Ice Tunnel")
    adventure = _english(
        "Bonecrusher Giant // Stomp", mana_cost="{2}{R}", layout="adventure"
    )
    transform = _english(
        "Delver of Secrets // Insectile Aberration", mana_cost="{U}", layout="transform"
    )
    future = _english("Future Card", mana_cost="{U}", frame="future")
    old_walker = Card.from_raw(
        _raw(
            "Garruk Wildspeaker",
            mana_cost="{2}{G}{G}",
            frame="2003",
            type_line="Legendary Planeswalker — Garruk",
        )
    )
    for card in [land, adventure, transform, future, old_walker]:
        assert cost_part(card) is None, card.name


def _creature(name: str, power: str, toughness: str, **extra: Any) -> Card:
    return Card.from_raw(
        _raw(
            name,
            type_line="Creature — Bird Horror",
            power=power,
            toughness=toughness,
            **extra,
        )
    )


def test_power_and_toughness_in_their_frames_box() -> None:
    strix = _creature("Baleful Strix", "1", "1")
    assert power_toughness(strix) == {
        "power": "1",
        "toughness": "1",
        "box": [0.8, 0.9, 0.118, 0.0368],
    }
    mongrel = _creature("Wild Mongrel", "2", "2", frame="2003")
    assert power_toughness(mongrel) == {
        "power": "2",
        "toughness": "2",
        "box": [0.765, 0.902, 0.138, 0.036],
    }


def test_an_adventures_power_and_toughness_are_its_main_parts() -> None:
    giant = Card.from_raw(
        _raw(
            "Bonecrusher Giant // Stomp",
            layout="adventure",
            card_faces=[
                {
                    "name": "Bonecrusher Giant",
                    "type_line": "Creature — Giant",
                    "power": "4",
                    "toughness": "3",
                },
                {"name": "Stomp", "type_line": "Instant — Adventure"},
            ],
        )
    )
    built = power_toughness(giant)
    assert built is not None
    assert (built["power"], built["toughness"]) == ("4", "3")


def test_no_power_and_toughness_asked_unless_whole_numbers_in_a_measured_box() -> None:
    goyf = _creature("Tarmogoyf", "*", "1+*")
    rumbler = _creature("Char-Rumbler", "-1", "3")
    old = _creature("Hypnotic Specter", "2", "2", frame="1997")
    spacecraft = Card.from_raw(
        _raw(
            "Uthros Scanship",
            type_line="Artifact — Spacecraft",
            power="4",
            toughness="4",
        )
    )
    transform = _double_faced("transform", {"power": "3", "toughness": "2"})
    instant = _english("Counterspell")
    for card in [goyf, rumbler, old, spacecraft, transform, instant]:
        assert power_toughness(card) is None, card.name


# Where the test set's symbol starts on the type line
SYMBOLS = {"tst": 0.87}


def _typed(name: str, type_line: str, **extra: Any) -> Card:
    return Card.from_raw(_raw(name, type_line=type_line, set="tst", **extra))


def test_creature_types_and_their_line_up_to_the_set_symbol() -> None:
    mage = _typed("Meddling Mage", "Creature — Human Wizard")
    # From the line's start to 3 pixels before the symbol
    assert creature_type(mage, SYMBOLS) == {
        "types": ["Human", "Wizard"],
        "box": [0.078, 0.569, 0.786, 0.043],
    }
    karn = _typed("Karn, Argent Defender", "Legendary Artifact Creature — Golem")
    built = creature_type(karn, SYMBOLS)
    assert built is not None
    assert built["types"] == ["Golem"]


def test_an_adventures_creature_types_are_its_main_parts() -> None:
    borrower = Card.from_raw(
        _raw(
            "Brazen Borrower // Petty Theft",
            layout="adventure",
            set="tst",
            card_faces=[
                {"name": "Brazen Borrower", "type_line": "Creature — Faerie Rogue"},
                {"name": "Petty Theft", "type_line": "Instant — Adventure"},
            ],
        )
    )
    built = creature_type(borrower, SYMBOLS)
    assert built is not None
    assert built["types"] == ["Faerie", "Rogue"]


def test_no_creature_types_asked_when_the_name_has_them_all() -> None:
    king = _typed("Goblin King", "Creature — Goblin")
    rats = _typed("Ravenous Rats", "Creature — Rat")
    # Asked: the name has the Goblin but not the Warrior
    warchief = _typed("Goblin Warchief", "Creature — Goblin Warrior")
    # Asked: a Rat is in "Pirate", but no word of the name starts with it
    pirate = _typed("Pirate Captain", "Creature — Rat")
    assert creature_type(king, SYMBOLS) is None
    assert creature_type(rats, SYMBOLS) is None
    assert creature_type(warchief, SYMBOLS) is not None
    assert creature_type(pirate, SYMBOLS) is not None


def test_no_creature_types_asked_of_other_cards_or_frames() -> None:
    old = _typed("Wild Mongrel", "Creature — Dog", frame="2003")
    transform = _double_faced("transform", {"power": "3", "toughness": "2"}, set="tst")
    instant = _english("Counterspell", set="tst")
    equipment = _typed("Bonesplitter", "Artifact — Equipment")
    kindred = _typed("Bitterblossom", "Kindred Enchantment — Faerie")
    for card in [old, transform, instant, equipment, kindred]:
        assert creature_type(card, SYMBOLS) is None, card.name


def test_no_creature_types_asked_without_the_sets_symbol_measured() -> None:
    mage = _typed("Meddling Mage", "Creature — Human Wizard")
    assert creature_type(mage, {}) is None
    assert creature_type(mage, {"tst": None}) is None


def _symbol_picture(
    symbol: tuple[int, int] | None = (420, 450), text_to: int = 200
) -> bytes:
    """A modern frame's type line, 488 by 680: a light bar, dark text from
    the line's start to `text_to`, and a set symbol from and to the
    columns given - both drawn as thin upright strokes, as print is all
    edges"""
    image = Image.new("L", (488, 680), 200)
    draw = ImageDraw.Draw(image)
    for x in range(40, text_to, 4):
        draw.rectangle([x, 392, x + 1, 410], fill=20)
    if symbol:
        for x in range(symbol[0], symbol[1], 4):
            draw.rectangle([x, 390, x + 1, 412], fill=20)
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def test_new_sets_symbols_are_measured_on_the_shortest_type_line(
    monkeypatch: MonkeyPatch,
) -> None:
    short = _typed("Ravager", "Creature — Ox")
    long = _typed("Ancient Ravager", "Legendary Creature — Human Soldier")
    pictures = {
        image_urls(short)[0]: _symbol_picture(),
        image_urls(long)[0]: _symbol_picture(text_to=410),
    }
    asked: list[str] = []

    def download(url: str) -> bytes | None:
        asked.append(url)
        return pictures.get(url)

    monkeypatch.setattr(name_in_text, "_download", download)
    for card in (short, long):
        card.raw["set"] = "new"
    measured = measure_new_symbols([long, short], {"old": 0.85})
    assert measured == {"old": 0.85, "new": round(420 / 488, 4)}
    assert asked == [image_urls(short)[0]]


def test_a_set_not_measured_on_any_card_is_left_out(monkeypatch: MonkeyPatch) -> None:
    # No symbol on the first; the text runs up to it on the second
    cards = [_typed("Ravager", "Creature — Ox"), _typed("Pillager", "Creature — Orc")]
    pictures = iter([_symbol_picture(symbol=None), _symbol_picture(text_to=410)])
    monkeypatch.setattr(name_in_text, "_download", lambda url: next(pictures))
    assert measure_new_symbols(cards, {}) == {"tst": None}


def test_a_set_whose_picture_cant_be_downloaded_is_tried_next_time(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(name_in_text, "_download", lambda url: None)
    assert measure_new_symbols([_typed("Ravager", "Creature — Ox")], {}) == {}


def test_horizontal_sides() -> None:
    upright = Card.from_raw(_raw("Counterspell"))
    split = Card.from_raw(_raw("Wear // Tear", layout="split", keywords=["Fuse"]))
    aftermath = Card.from_raw(
        _raw("Commit // Memory", layout="split", keywords=["Aftermath"])
    )
    battle = Card.from_raw(
        {
            **_raw("Invasion of Gobakhan"),
            "image_uris": None,
            "layout": "battle",
            "card_faces": [
                {
                    "name": "Invasion of Gobakhan",
                    "type_line": "Battle — Siege",
                    "image_uris": {"grid": "front.webp", "art": "art/front.webp"},
                },
                {
                    "name": "Lightshield Array",
                    "type_line": "Artifact",
                    "image_uris": {"grid": "back.webp", "art": "art/back.webp"},
                },
            ],
        }
    )
    assert horizontal_sides(upright) == [False]
    assert horizontal_sides(split) == [True]
    assert horizontal_sides(aftermath) == [False]
    # Only the front of a battle is printed sideways
    assert horizontal_sides(battle) == [True, False]


def test_build_card_without_id_or_picture_is_left_out() -> None:
    no_id = Card.from_raw(
        {"id": "1", "name": "No Id", "image_uris": {"grid": "x.webp"}}
    )
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
    mixed = Card.from_raw(
        _raw(
            "Mixed",
            image_uris={
                "grid": "grid/id-Mixed.webp",
                "art": "art/another-printing.webp",
            },
        )
    )
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


# Two names on the list can lead to one card, e.g. after a rename
def test_build_export_keeps_one_copy_of_each_card(
    caplog: pytest.LogCaptureFixture,
) -> None:
    cards = [
        # Unusable, so it doesn't stop the usable copy after it
        Card.from_raw(
            _raw(
                "Mixed",
                oracle_id="m",
                image_uris={
                    "grid": "grid/id-Mixed.webp",
                    "art": "art/another-printing.webp",
                },
            )
        ),
        Card.from_raw(_raw("New Name", oracle_id="n")),
        Card.from_raw(_raw("Old Name", oracle_id="n")),
        Card.from_raw(_raw("Mixed Fixed", oracle_id="m")),
    ]
    data = build_export("pauper", cards, "2026-10-17T19:18:03Z")
    assert [c["name"] for c in data["cards"]] == ["Mixed Fixed", "New Name"]
    assert "Leaving out 'Old Name' - the same card as 'New Name'" in caplog.text


def _every(*names_and_ids: tuple[str, str], **extra: Any) -> list[Card]:
    return [
        Card.from_raw(_raw(name, oracle_id=oracle_id, **extra))
        for name, oracle_id in names_and_ids
    ]


def test_every_card_goes_in_the_file_of_its_oracle_ids_start() -> None:
    cards = _every(
        ("Pyroblast", "a1-p"), ("Hydroblast", "a1-h"), ("Counterspell", "07-c")
    )
    files = build_every_card(cards)
    assert {key: [c["name"] for c in cards] for key, cards in files.items()} == {
        "07": ["Counterspell"],
        "a1": ["Hydroblast", "Pyroblast"],
    }
    # In order, so the files don't reshuffle between runs
    assert list(files) == ["07", "a1"]


def test_every_card_leaves_out_what_the_lists_leave_out(
    caplog: pytest.LogCaptureFixture,
) -> None:
    cards = [
        *_every(("Island", "00-i"), type_line="Basic Land — Island"),
        Card.from_raw({"id": "2", "oracle_id": "00-x", "name": "No Picture"}),
        # Not made into a file name
        *_every(("Odd Id", "../x")),
        *_every(("Counterspell", "00-c")),
    ]
    files = build_every_card(cards)
    assert [c["name"] for c in files["00"]] == ["Counterspell"]
    assert list(files) == ["00"]
    assert "Leaving out 2 cards with no oracle id" in caplog.text
    assert "No Picture, Odd Id" in caplog.text


def test_every_card_leaves_out_a_name_of_two_cards(
    caplog: pytest.LogCaptureFixture,
) -> None:
    cards = _every(("Twin", "00-a"), ("twin", "01-b"), ("Single", "02-c"))
    assert list(build_every_card(cards)) == ["02"]
    assert "Leaving out 'Twin' - 2 cards have that name" in caplog.text


def test_every_card_is_asked_by_the_readings_given() -> None:
    # A name in its text box, covered where the reading found it
    cards = _every(
        ("Masticore", "00-m"),
        type_line="Artifact Creature — Masticore",
        oracle_text="Masticore deals 1 damage to target creature.",
        lang="en",
    )
    assert build_every_card(cards)["00"][0]["name_box"] is None
    read = _ReadAs([[0.1, 0.7, 0.2, 0.03]])
    built = build_every_card(cards, read)["00"][0]
    assert built["name_text_boxes"] == [[0.1, 0.7, 0.2, 0.03]]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def test_export_every_card_writes_the_index_and_each_file(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "EXPORT_MIN_EVERY_CARD", 3)
    # From an earlier run: cards still in a file, and a file with none now
    cards_dir = tmp_path / "cards"
    cards_dir.mkdir()
    (cards_dir / "a1.json").write_text('{"cards": []}', encoding="utf-8")
    (cards_dir / "ff.json").write_text('{"cards": []}', encoding="utf-8")

    cards = _every(
        ("Pyroblast", "a1-p"), ("Hydroblast", "a1-h"), ("Counterspell", "07-c")
    )
    assert export_every_card(cards, tmp_path) == cards_dir / "index.json"

    assert sorted(f.name for f in cards_dir.iterdir()) == [
        "07.json",
        "a1.json",
        "index.json",
    ]
    assert _read_json(cards_dir / "index.json") == {
        "07": ["Counterspell"],
        "a1": ["Hydroblast", "Pyroblast"],
    }
    a1 = _read_json(cards_dir / "a1.json")
    assert [card["oracle_id"] for card in a1["cards"]] == ["a1-h", "a1-p"]
    assert a1["cards"][0] == build_card(cards[1])


def test_export_every_card_with_too_few_cards_keeps_the_old_files(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "EXPORT_MIN_EVERY_CARD", 3)
    cards_dir = tmp_path / "cards"
    cards_dir.mkdir()
    (cards_dir / "index.json").write_text('{"00": ["Old"]}', encoding="utf-8")

    with pytest.raises(RuntimeError, match="Only 2 cards usable in Scryfall's data"):
        export_every_card(_every(("A", "00-a"), ("B", "01-b")), tmp_path)

    assert sorted(f.name for f in cards_dir.iterdir()) == ["index.json"]
    assert _read_json(cards_dir / "index.json") == {"00": ["Old"]}


def _on_list(*cards: Card) -> tuple[list[MetaEntry], dict[str, Card]]:
    """A list of these cards, and the cards read_cards found for it"""
    meta = [MetaEntry(name=card.name) for card in cards]
    return meta, {normalize_name(card.name): card for card in cards}


def test_export_format_writes_the_file(
    conn: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    meta, cards = _on_list(Card.from_raw(_raw("Lórien Revealed", oracle_id="l")))
    _list_fetched(monkeypatch, FETCHED)
    monkeypatch.setattr(config, "EXPORT_MIN_CARDS", 1)

    caplog.set_level(logging.INFO)
    path = export_format(conn, "pauper", "all", meta, cards, tmp_path / "data")

    assert path == tmp_path / "data" / "pauper.json"
    assert f"Wrote {path}: 1 card" in caplog.text
    text = path.read_text(encoding="utf-8")
    # Written as real characters, not \u escapes
    assert "Lórien Revealed" in text
    assert json.loads(text) == {
        "format": "pauper",
        "list_updated": "2026-10-17T19:18:03Z",
        "cards": [
            {
                "oracle_id": "l",
                "name": "Lórien Revealed",
                "images": ["grid/id-Lórien Revealed.webp"],
                "large_images": ["large/id-Lórien Revealed.jpg"],
                "art_box": [0.079, 0.114, 0.840, 0.440],
                "name_box": None,
                "name_text_boxes": [],
                "art": "art/id-Lórien Revealed.webp",
                "artist": "Some Artist",
                "art_from": None,
                "horizontal": [False],
                "back": None,
                "spell": None,
                "halves": None,
                "type": "card",
                "cost": None,
                "power_toughness": None,
                "creature_type": None,
            }
        ],
    }


# A failed fetch must not replace the file with an empty or half-empty one
def test_export_format_fails_with_too_few_cards(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    meta, cards = _on_list(Card.from_raw(_raw("Hydroblast", oracle_id="h")))
    _list_fetched(monkeypatch, FETCHED)
    monkeypatch.setattr(config, "EXPORT_MIN_CARDS", 2)

    with pytest.raises(RuntimeError, match="Only 1 usable cards"):
        export_format(conn, "pauper", "all", meta, cards, tmp_path / "data")

    assert not (tmp_path / "data" / "pauper.json").exists()


def test_write_json_keeps_the_old_file_when_writing_fails(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    path = tmp_path / "pauper.json"
    path.write_text('{"old": true}', encoding="utf-8")
    real_write_text = Path.write_text

    def disk_full(self: Path, text: str, *args: Any, **kwargs: Any) -> int:
        # Half the file gets written, then the disk is full
        real_write_text(self, text[: len(text) // 2], *args, **kwargs)
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(Path, "write_text", disk_full)
    with pytest.raises(OSError, match="No space left"):
        write_json(path, {"format": "pauper", "cards": []})

    assert json.loads(path.read_text(encoding="utf-8")) == {"old": True}
    # Nor is the half-written file left behind to be published
    assert list(tmp_path.iterdir()) == [path]


def test_export_format_exports_the_cards_on_its_list(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    # read_cards found cards for every list; this list has two of them,
    # one spelled another way, and a name no card was found for
    bolt = Card.from_raw(_raw("Lightning Bolt", oracle_id="bolt"))
    lorien = Card.from_raw(_raw("Lórien Revealed", oracle_id="lorien"))
    _, cards = _on_list(
        bolt, lorien, Card.from_raw(_raw("Counterspell", oracle_id="c"))
    )
    meta = [
        MetaEntry(name="Lorien Revealed"),
        MetaEntry(name="Lightning Bolt"),
        MetaEntry(name="Lightnig Bolt"),
    ]
    _list_fetched(monkeypatch, FETCHED)
    monkeypatch.setattr(config, "EXPORT_MIN_CARDS", 1)

    path = export_format(conn, "pauper", "all", meta, cards, tmp_path)

    written = json.loads(path.read_text(encoding="utf-8"))["cards"]
    assert [card["name"] for card in written] == ["Lightning Bolt", "Lórien Revealed"]


@pytest.mark.parametrize("age_days, publishes", [(2, True), (3, True), (4, False)])
def test_export_format_refuses_an_old_list(
    conn: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    age_days: int,
    publishes: bool,
) -> None:
    # A count this old means counting has failed for days: fail the run,
    # so GitHub reports it, rather than publish the old list again
    meta, cards = _on_list(Card.from_raw(_raw("Hydroblast", oracle_id="h")))
    monkeypatch.setattr(config, "EXPORT_MIN_CARDS", 1)
    _list_fetched(monkeypatch, FETCHED, now=FETCHED + age_days * 24 * 60 * 60)

    if publishes:
        export_format(conn, "pauper", "all", meta, cards, tmp_path)
        assert (tmp_path / "pauper.json").exists()
    else:
        with pytest.raises(RuntimeError, match="4 days ago - not publishing"):
            export_format(conn, "pauper", "all", meta, cards, tmp_path)
        assert not (tmp_path / "pauper.json").exists()


def test_export_format_fails_without_any_list(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    _list_fetched(monkeypatch, None)

    with pytest.raises(RuntimeError, match="pauper decks were never counted"):
        export_format(conn, "pauper", "all", [], {}, tmp_path)


FakeExport = Callable[
    [
        sqlite3.Connection,
        str,
        str,
        list[MetaEntry],
        dict[str, Card],
        Path,
        ReadText,
        SetSymbols,
    ],
    Path,
]


def _fake_export(fails: tuple[str, ...] = ()) -> FakeExport:
    """export_format that writes an empty file, or fails for the named lists"""

    def fake_export(
        conn: sqlite3.Connection,
        format_name: str,
        kind: str,
        meta: list[MetaEntry],
        cards: dict[str, Card],
        out_dir: Path,
        read_text: ReadText,
        symbols: SetSymbols,
    ) -> Path:
        name = config.list_name(format_name, kind)
        if name in fails:
            raise RuntimeError("Too few usable cards")
        path = out_dir / f"{name}.json"
        path.write_text("{}", encoding="utf-8")
        return path

    return fake_export


# Where export_all is told Scryfall's card data is; read_cards is faked
BULK = Path("cards.jsonl.gz")


def _lists_and_cards(
    monkeypatch: MonkeyPatch,
    counts: dict[str, list[str]] | None = None,
    unreachable: tuple[str, ...] = (),
) -> list[set[str]]:
    """Each format's decks have these cards, and can't be counted for
    the formats in `unreachable`; read_cards finds nothing. Returns the
    names read_cards was asked about, a set for each time it was called."""

    def fake_meta(conn: sqlite3.Connection, format_name: str) -> Any:
        if format_name in unreachable:
            raise RuntimeError("The pauper decks were never counted")
        return [MetaEntry(name=card) for card in (counts or {}).get(format_name, [])]

    asked: list[set[str]] = []

    def fake_read(path: Path, names: set[str]) -> dict[str, Card]:
        assert path == BULK
        asked.append(set(names))
        return {}

    monkeypatch.setattr("meta_morphis.export.get_meta_cards", fake_meta)
    monkeypatch.setattr("meta_morphis.export.read_cards", fake_read)
    return asked


def test_export_all_keeps_going_when_one_list_fails(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    # Modern's lands list was exported before and now fails; Standard's
    # "all" list never worked
    (tmp_path / "modern-lands.json").write_text('{"old": true}', encoding="utf-8")
    _lists_and_cards(monkeypatch)
    monkeypatch.setattr(
        "meta_morphis.export.export_format", _fake_export(("modern-lands", "standard"))
    )

    failed = export_all(
        conn, ["pauper", "modern", "standard"], ["all", "lands"], tmp_path, BULK
    )

    assert failed == ["modern-lands", "standard"]
    # The lists after the failed ones were still written
    assert (tmp_path / "standard-lands.json").exists()
    # Modern keeps its old lands file
    old = json.loads((tmp_path / "modern-lands.json").read_text(encoding="utf-8"))
    assert old == {"old": True}
    # Standard has no "all" list, so the app isn't offered the format
    formats = json.loads((tmp_path / "formats.json").read_text(encoding="utf-8"))
    assert formats == {
        "formats": ["pauper", "modern"],
        "lists": {"pauper": ["all", "lands"], "modern": ["all", "lands"]},
    }


def test_export_all_removes_a_half_written_file_of_a_killed_run(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    # The last run was killed while writing pauper.json; its temporary
    # file is still there, and the finished file from the run before
    (tmp_path / "pauper.json").write_text('{"old": true}', encoding="utf-8")
    (tmp_path / "pauper.json.tmp").write_text('{"form', encoding="utf-8")
    (tmp_path / "cards").mkdir()
    (tmp_path / "cards" / "00.json").write_text('{"cards": []}', encoding="utf-8")
    (tmp_path / "cards" / "00.json.tmp").write_text('{"ca', encoding="utf-8")
    _lists_and_cards(monkeypatch)
    monkeypatch.setattr("meta_morphis.export.export_format", _fake_export(("pauper",)))

    export_all(conn, ["pauper"], ["all"], tmp_path, BULK)

    # The half-written file is gone, not published; the old file stays
    assert sorted(f.name for f in tmp_path.iterdir()) == [
        "cards",
        "formats.json",
        "pauper.json",
    ]
    # Also one of every card's files
    assert [f.name for f in (tmp_path / "cards").iterdir()] == ["00.json"]
    assert json.loads((tmp_path / "pauper.json").read_text(encoding="utf-8")) == {
        "old": True
    }


def test_export_all_reports_no_failures(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    _lists_and_cards(monkeypatch)
    monkeypatch.setattr("meta_morphis.export.export_format", _fake_export())

    assert export_all(conn, ["pauper"], ["all", "creatures"], tmp_path, BULK) == []
    assert (tmp_path / "pauper-creatures.json").exists()
    formats = json.loads((tmp_path / "formats.json").read_text(encoding="utf-8"))
    assert formats == {"formats": ["pauper"], "lists": {"pauper": ["all", "creatures"]}}


def test_export_all_reads_the_card_data_once_for_every_format(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    asked = _lists_and_cards(
        monkeypatch,
        {"pauper": ["Lightning Bolt", "Bojuka Bog"], "modern": ["Ragavan"]},
    )
    monkeypatch.setattr("meta_morphis.export.export_format", _fake_export())

    export_all(conn, ["pauper", "modern"], ["all", "lands"], tmp_path, BULK)

    assert asked == [{"Lightning Bolt", "Bojuka Bog", "Ragavan"}]


def test_export_all_keeps_going_when_a_format_cant_be_counted(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    asked = _lists_and_cards(
        monkeypatch,
        {"pauper": ["Lightning Bolt"], "modern": ["Ragavan, Nimble Pilferer"]},
        unreachable=("pauper",),
    )
    monkeypatch.setattr("meta_morphis.export.export_format", _fake_export())

    # Every list of the format fails, reported in the order of the lists
    failed = export_all(conn, ["pauper", "modern"], ["all", "lands"], tmp_path, BULK)

    assert failed == ["pauper", "pauper-lands"]
    assert asked == [{"Ragavan, Nimble Pilferer"}]
    assert (tmp_path / "modern-lands.json").exists()
    assert not (tmp_path / "pauper-lands.json").exists()


def test_export_all_without_card_data_keeps_every_file(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    # No copy of Scryfall's card data was ever downloaded
    def read_cards_without_a_file(path: Path, names: set[str]) -> dict[str, Card]:
        raise FileNotFoundError(path)

    (tmp_path / "pauper.json").write_text('{"old": true}', encoding="utf-8")
    _lists_and_cards(monkeypatch)
    monkeypatch.setattr("meta_morphis.export.read_cards", read_cards_without_a_file)
    monkeypatch.setattr("meta_morphis.export.export_format", _fake_export())

    failed = export_all(conn, ["pauper"], ["all", "lands"], tmp_path, BULK)

    assert failed == ["pauper", "pauper-lands"]
    old = json.loads((tmp_path / "pauper.json").read_text(encoding="utf-8"))
    assert old == {"old": True}
    formats = json.loads((tmp_path / "formats.json").read_text(encoding="utf-8"))
    assert formats == {"formats": ["pauper"], "lists": {"pauper": ["all"]}}


@pytest.mark.parametrize("age_days, old", [(6, False), (7, False), (8, True)])
def test_old_card_data_is_reported(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    age_days: int,
    old: bool,
) -> None:
    path = tmp_path / "cards.jsonl.gz"
    path.write_bytes(b"")
    monkeypatch.setattr(
        "meta_morphis.export.bulk_file_age", lambda path: age_days * config.DAY
    )

    assert _bulk_file_is_old(path) is old
    assert ("8 days old - downloading it has failed" in caplog.text) is old


def test_missing_card_data_is_reported_by_the_lists_instead(tmp_path: Path) -> None:
    assert _bulk_file_is_old(tmp_path / "cards.jsonl.gz") is False


@pytest.mark.parametrize(
    "type_line, basic",
    [
        ("Basic Land — Mountain", True),
        ("Basic Snow Land — Island", True),
        ("Basic Land", True),  # Wastes
        ("Land", False),
        ("Snow Land", False),
        ("Legendary Land", False),
        ("Artifact Land", False),
    ],
)
def test_is_basic_land(type_line: str, basic: bool) -> None:
    assert is_basic_land(Card.from_raw(_raw("Some Land", type_line=type_line))) is basic


def _two_sided(name: str, front: str, back: str) -> Card:
    """A card with two faces of these type lines"""
    front_name, back_name = name.split(" // ")
    return Card.from_raw(
        _raw(
            name,
            card_faces=[
                {"name": front_name, "type_line": front},
                {"name": back_name, "type_line": back},
            ],
        )
    )


@pytest.mark.parametrize(
    "card, kind",
    [
        (Card.from_raw(_raw("Bojuka Bog", type_line="Land")), "lands"),
        (
            Card.from_raw(
                _raw("Urza's Saga", type_line="Enchantment Land — Urza's Saga")
            ),
            "lands",
        ),
        (
            Card.from_raw(
                _raw("Dryad Arbor", type_line="Land Creature — Forest Dryad")
            ),
            "lands",
        ),
        (
            Card.from_raw(_raw("Myr Enforcer", type_line="Artifact Creature — Myr")),
            "creatures",
        ),
        (Card.from_raw(_raw("Lightning Bolt", type_line="Instant")), "spells"),
        (
            Card.from_raw(_raw("Jace", type_line="Legendary Planeswalker — Jace")),
            "spells",
        ),
        (
            Card.from_raw(_raw("Smuggler's Copter", type_line="Artifact — Vehicle")),
            "spells",
        ),
        # By the front: an adventure, a spell with a land on its back
        (
            _two_sided(
                "Bonecrusher Giant // Stomp", "Creature — Giant", "Instant — Adventure"
            ),
            "creatures",
        ),
        (
            _two_sided("Sink into Stupor // Soporific Springs", "Instant", "Land"),
            "spells",
        ),
        (
            _two_sided("Brightclimb Pathway // Grimclimb Pathway", "Land", "Land"),
            "lands",
        ),
        (_two_sided("Fire // Ice", "Instant", "Instant"), "spells"),
    ],
)
def test_card_kind(card: Card, kind: str) -> None:
    assert card_kind(card) == kind


def test_pick_cards_takes_the_most_played_of_each_kind(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "LIST_SIZE", 2)
    bolt = Card.from_raw(_raw("Lightning Bolt", type_line="Instant"))
    knife = Card.from_raw(_raw("Pumpkin Bombardment", type_line="Sorcery"))
    _, cards = _on_list(
        Card.from_raw(_raw("Island", type_line="Basic Land — Island")),
        bolt,
        Card.from_raw(_raw("Bojuka Bog", type_line="Land")),
        Card.from_raw(_raw("Myr Enforcer", type_line="Artifact Creature — Myr")),
        knife,
        Card.from_raw(_raw("Ponder", type_line="Sorcery")),
    )
    # Its name on Magic Online leads to the same card
    cards[normalize_name("Knife Trick")] = knife
    # In the order of the count: most played first
    meta = [
        MetaEntry(name=name)
        for name in [
            "Island",
            "Lightning Bolt",
            "No Such Card",
            "Bojuka Bog",
            "Knife Trick",
            "Pumpkin Bombardment",
            "Myr Enforcer",
            "Ponder",
        ]
    ]

    def picked(kind: str) -> list[str]:
        return [card.name for card in pick_cards(meta, cards, kind)]

    assert picked("all") == ["Lightning Bolt", "Pumpkin Bombardment"]
    assert picked("spells") == ["Lightning Bolt", "Pumpkin Bombardment"]
    assert picked("creatures") == ["Myr Enforcer"]
    assert picked("lands") == ["Bojuka Bog"]

    monkeypatch.setattr(config, "LIST_SIZE", 4)
    assert picked("all") == [
        "Lightning Bolt",
        "Pumpkin Bombardment",
        "Myr Enforcer",
        "Ponder",
    ]


def test_list_names() -> None:
    assert config.list_name("pauper", "all") == "pauper"
    assert config.list_name("pauper", "lands") == "pauper-lands"


def test_list_changes_names_cards_that_entered_and_left() -> None:
    before = ["Hydroblast", "Ponder", "Lightning Bolt"]
    after = ["Hydroblast", "Guttersnipe", "Lightning Bolt", "Writhing Chrysalis"]

    assert list_changes(before, after) == (
        ["Guttersnipe", "Writhing Chrysalis"],
        ["Ponder"],
    )


def test_list_changes_ignores_spelling_and_order() -> None:
    assert list_changes(
        ["Lorien Revealed", "Hydroblast"], ["Hydroblast", "Lórien Revealed"]
    ) == ([], [])


def _export_twice(
    conn: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    before: list[str],
    after: list[str],
) -> None:
    """Exports Pauper's "all" list with the cards `before`, if any, and
    then with the cards `after`"""
    _list_fetched(monkeypatch, FETCHED)
    monkeypatch.setattr(config, "EXPORT_MIN_CARDS", 1)
    for names in (before, after):
        if names:
            meta, cards = _on_list(
                *(Card.from_raw(_raw(name, oracle_id=name)) for name in names)
            )
            export_format(conn, "pauper", "all", meta, cards, tmp_path)


def test_export_format_logs_cards_that_entered_and_left(
    conn: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    _export_twice(
        conn,
        tmp_path,
        monkeypatch,
        ["Hydroblast", "Ponder"],
        ["Hydroblast", "Guttersnipe"],
    )

    assert "1 card entered the pauper list: Guttersnipe" in caplog.text
    assert "1 card left the pauper list: Ponder" in caplog.text


def test_export_format_logs_an_unchanged_list(
    conn: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    _export_twice(conn, tmp_path, monkeypatch, ["Hydroblast"], ["Hydroblast"])

    assert "The pauper list did not change" in caplog.text


def test_a_first_export_logs_no_changes(
    conn: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # No file yet: every card would count as "entered", which says nothing
    caplog.set_level(logging.INFO)
    _export_twice(conn, tmp_path, monkeypatch, [], ["Hydroblast", "Ponder"])

    assert "entered" not in caplog.text
    assert "did not change" not in caplog.text


def test_report_left_out_adds_to_the_github_job_summary(
    monkeypatch: MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    page = tmp_path / "summary.md"
    page.write_text("Earlier step\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(page))
    report_left_out(["Left out on 1 card:", "- Masticore: unsure"])
    assert "- Masticore: unsure" in caplog.text
    assert page.read_text(encoding="utf-8") == (
        "Earlier step\n### Cards asked only by their artwork\n"
        "Left out on 1 card:\n- Masticore: unsure\n"
    )
    # Nothing left out: nothing added
    report_left_out([])
    assert page.read_text(encoding="utf-8").endswith("- Masticore: unsure\n")


def _two_part(layout: str, **extra: Any) -> Card:
    """An adventure or prepare card, as Scryfall gives it: one picture,
    and both parts in card_faces"""
    fields: dict[str, Any] = {
        "lang": "en",
        "layout": layout,
        "released_at": "2026-04-24",
        "set_type": "expansion",
        "card_faces": [
            {
                "name": "Brazen Borrower",
                "mana_cost": "{1}{U}{U}",
                "type_line": "Creature — Faerie Rogue",
                "oracle_text": "Flash\nFlying",
            },
            {
                "name": "Petty Theft",
                "mana_cost": "{1}{U}",
                "type_line": "Instant — Adventure",
                "oracle_text": "Return target nonland permanent.",
            },
        ],
    }
    return Card.from_raw(_raw("Brazen Borrower // Petty Theft", **{**fields, **extra}))


@pytest.mark.parametrize(
    "layout, spell_box",
    [
        # Two symbols of 0.0435, and the gap of 0.02, before 0.479
        ("adventure", [0.08, 0.637, 0.292, 0.032]),
        # Two symbols of 0.0445, and the gap of 0.02, before 0.931
        ("prepare", [0.514, 0.637, 0.308, 0.032]),
    ],
)
def test_each_part_of_a_card_with_a_spell_has_its_own_name_box(
    layout: str, spell_box: list[float]
) -> None:
    card = _two_part(layout)
    # The main part's, in a normal card's title bar, before its own cost
    assert name_boxes(card) == ([0.08, 0.052, 0.6735, 0.051], [])
    assert spell_part(card) == {
        "name": "Petty Theft",
        "name_box": spell_box,
        "name_text_boxes": [],
        "type": "instant",
    }
    # The main part's type, not the spell's
    assert build_card(card)["type"] == "creature"  # type: ignore[index]


def test_each_part_is_read_for_its_own_name() -> None:
    read: list[str] = []

    def read_text(card: Card) -> list[list[float]] | None:
        read.append(card.name)
        return [[0.1, 0.8, 0.2, 0.03]] if card.name == "Brazen Borrower" else None

    # Printed with the name where the Oracle text says "this creature",
    # and the spell's name in the main part's text
    card = _two_part(
        "adventure",
        released_at="2019-10-04",
        card_faces=[
            {
                "name": "Brazen Borrower",
                "mana_cost": "{1}{U}{U}",
                "type_line": "Creature — Faerie Rogue",
                "oracle_text": "This creature can block only creatures with flying.",
            },
            {
                "name": "Petty Theft",
                "mana_cost": "{1}{U}",
                "type_line": "Instant — Adventure",
                "oracle_text": "Return target nonland permanent.",
            },
        ],
    )
    assert name_boxes(card, read_text)[1] == [[0.1, 0.8, 0.2, 0.03]]
    # "This creature" is the main part: the spell's name is in its title
    # bar alone, and isn't read for
    spell = spell_part(card, read_text)
    assert spell and spell["name_box"] == [0.08, 0.637, 0.292, 0.032]
    assert read == ["Brazen Borrower"]

    # The spell's name in the main part's text: read for it, and here
    # it can't be covered, so the spell is never asked about
    named = _two_part(
        "adventure",
        card_faces=[
            {
                "name": "Brazen Borrower",
                "mana_cost": "{1}{U}{U}",
                "type_line": "Creature — Faerie Rogue",
                "oracle_text": "You may cast Petty Theft twice.",
            },
            {
                "name": "Petty Theft",
                "mana_cost": "{1}{U}",
                "type_line": "Instant — Adventure",
                "oracle_text": "Return target nonland permanent.",
            },
        ],
    )
    read.clear()
    spell = spell_part(named, read_text)
    assert spell and spell["name_box"] is None
    assert read == ["Petty Theft"]


def test_a_spell_is_asked_by_its_picture_only_in_the_modern_frame() -> None:
    spell = spell_part(_two_part("adventure", frame="2003"))
    assert spell and spell["name_box"] is None
    french = spell_part(_two_part("adventure", lang="fr"))
    assert french and french["name_box"] is None


def test_only_adventure_and_prepare_cards_have_a_spell() -> None:
    built = build_card(_two_part("prepare"))
    assert built and built["spell"] and built["spell"]["name"] == "Petty Theft"
    assert spell_part(Card.from_raw(_raw("Wear // Tear", layout="split"))) is None
    assert spell_part(Card.from_raw(_raw("Counterspell"))) is None


def _split(name: str, faces: list[tuple[str, str, str]], **extra: Any) -> Card:
    """A split card printed sideways, as Scryfall gives it: one picture,
    and both halves in card_faces, as (name, mana cost, type line)"""
    card_faces = [
        {
            "name": face,
            "mana_cost": cost,
            "type_line": kind,
            "oracle_text": "Draw a card.",
        }
        for face, cost, kind in faces
    ]
    fields: dict[str, Any] = {
        "lang": "en",
        "layout": "split",
        "released_at": "2024-09-27",
        "set_type": "expansion",
        "card_faces": card_faces,
    }
    return Card.from_raw(_raw(name, **{**fields, **extra}))


WEAR_TEAR = [("Wear", "{1}{R}", "Instant"), ("Tear", "{W}", "Instant")]
ROOM = [
    ("Unholy Annex", "{2}{B}", "Enchantment — Room"),
    ("Ritual Chamber", "{3}{B}{B}", "Enchantment — Room"),
]


def test_each_half_of_a_split_card_has_its_own_name_box() -> None:
    fused = _split("Wear // Tear", WEAR_TEAR, keywords=["Fuse"])
    room = _split(
        "Unholy Annex // Ritual Chamber", ROOM, type_line="Enchantment — Room"
    )
    # The first half's bar is the lower one, each name's box below its cost
    assert split_halves(fused) == [
        {"name": "Wear", "name_box": [0.077, 0.5911, 0.052, 0.3089], "type": "instant"},
        {"name": "Tear", "name_box": [0.077, 0.0945, 0.052, 0.3455], "type": "instant"},
    ]
    assert split_halves(room) == [
        {
            "name": "Unholy Annex",
            "name_box": [0.058, 0.5899, 0.0555, 0.3051],
            "type": "Room",
        },
        {
            "name": "Ritual Chamber",
            "name_box": [0.058, 0.1685, 0.0555, 0.2695],
            "type": "Room",
        },
    ]
    # The card has no one name to cover
    assert build_card(fused)["name_box"] is None  # type: ignore[index]


def test_a_split_half_is_asked_by_its_artwork_only_where_its_name_isnt_measured() -> (
    None
):
    # A split card without fuse, in another language, or with the name
    # in the other half's text
    plain = _split("Wear // Tear", WEAR_TEAR)
    french = _split("Wear // Tear", WEAR_TEAR, keywords=["Fuse"], lang="fr")
    named = _split(
        "Wear // Tear",
        WEAR_TEAR,
        keywords=["Fuse"],
        card_faces=[
            {
                "name": "Wear",
                "mana_cost": "{1}{R}",
                "type_line": "Instant",
                "oracle_text": "Draw a card.",
            },
            {
                "name": "Tear",
                "mana_cost": "{W}",
                "type_line": "Instant",
                "oracle_text": "Cast Wear.",
            },
        ],
    )
    assert [half["name_box"] for half in split_halves(plain) or []] == [None, None]
    assert [half["name_box"] for half in split_halves(french) or []] == [None, None]
    assert [half["name_box"] for half in split_halves(named) or []] == [
        None,
        [0.077, 0.0945, 0.052, 0.3455],
    ]


def test_no_halves_but_of_a_split_card_printed_sideways_in_the_modern_frame() -> None:
    aftermath = _split("Wear // Tear", WEAR_TEAR, keywords=["Aftermath"])
    old = _split("Wear // Tear", WEAR_TEAR, keywords=["Fuse"], frame="2003")
    assert split_halves(aftermath) is None
    # Asked about whole, by both halves' type
    aftermath_card = _split(
        "Wear // Tear",
        WEAR_TEAR,
        keywords=["Aftermath"],
        type_line="Instant // Instant",
    )
    assert build_card(aftermath_card)["type"] == "instant"  # type: ignore[index]
    assert split_halves(old) is None
    assert split_halves(Card.from_raw(_raw("Counterspell"))) is None


@pytest.mark.parametrize(
    "type_line, expected",
    [
        ("Creature — Faerie Rogue", "creature"),
        ("Basic Land — Island", "land"),
        ("Legendary Planeswalker — Jace", "planeswalker"),
        ("Battle — Siege", "battle"),
        ("Artifact — Equipment", "artifact"),
        ("Enchantment — Aura", "enchantment"),
        ("Instant", "instant"),
        ("Kindred Sorcery — Elf", "sorcery"),
        # With more than one type, the first in MAIN_TYPES
        ("Artifact Creature — Golem", "creature"),
        ("Enchantment Creature — Saga Elemental", "creature"),
        ("Artifact Land", "land"),
        ("Instant // Sorcery", "instant"),
        # A Room's door, not an enchantment
        ("Enchantment — Room", "Room"),
        ("", "card"),
    ],
)
def test_main_type(type_line: str, expected: str) -> None:
    assert main_type(type_line) == expected


def _with_picture(name: str, **extra: Any) -> Card:
    """A card whose name is in its text, with a picture to read"""
    raw = _raw(
        name,
        lang="en",
        type_line="Instant",
        oracle_text=f"{name} deals 1 damage to any target.",
        **extra,
    )
    raw["image_uris"]["png"] = f"png/id-{name}.png?1"
    return Card.from_raw(raw)


def _reader(monkeypatch: MonkeyPatch, saved: dict[str, Any]) -> NameInText:
    """A NameInText with Tesseract "installed", reading no picture really:
    every one it reads has nothing to cover"""
    monkeypatch.setattr(
        "meta_morphis.name_in_text.shutil.which", lambda name: "/usr/bin/tesseract"
    )
    monkeypatch.setattr(name_in_text, "_download", lambda url: b"png")
    monkeypatch.setattr(name_in_text, "name_in_text", lambda card, picture, words: [])
    return NameInText(saved, frozenset({"goblin"}))


def test_sides_to_read_are_those_that_may_show_their_name() -> None:
    lava_dart = _with_picture("Lava Dart")
    plain = _english("Counterspell", oracle_text="Counter target spell.")
    assert sides_to_read([lava_dart, plain]) == {"id-Lava Dart": lava_dart}


def test_read_new_pictures_reads_only_the_sides_not_read(
    monkeypatch: MonkeyPatch,
) -> None:
    read_before = _with_picture("Lava Dart")
    saved = {
        "id-Lava Dart": {
            "name": "Lava Dart",
            "picture": "png/id-Lava Dart.png?1",
            "reader": READER_VERSION,
            "boxes": [],
        }
    }
    read_text = _reader(monkeypatch, saved)
    downloads: list[str] = []

    def download(url: str) -> bytes:
        downloads.append(url)
        return b"png"

    monkeypatch.setattr(name_in_text, "_download", download)

    def finds_nothing(card: Card, picture: Any, words: Any) -> list[list[float]]:
        picture.content()
        return []

    monkeypatch.setattr(name_in_text, "name_in_text", finds_nothing)
    new = _with_picture("Shock")
    assert read_new_pictures([read_before, new], read_text, 60) == 0
    assert downloads == ["png/id-Shock.png?1"]
    assert read_text.is_read(new)
    # All read: nothing to do
    assert read_new_pictures([read_before, new], read_text, 60) == 0
    assert downloads == ["png/id-Shock.png?1"]


def test_read_new_pictures_starts_none_after_the_time_limit(
    monkeypatch: MonkeyPatch,
) -> None:
    read_text = _reader(monkeypatch, {})
    cards = [_with_picture("Lava Dart"), _with_picture("Shock")]
    assert read_new_pictures(cards, read_text, 0) == 2
    assert not read_text.changed


def test_read_new_pictures_reads_none_without_tesseract(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("meta_morphis.name_in_text.shutil.which", lambda name: None)
    read_text = NameInText({}, frozenset({"goblin"}))
    assert read_new_pictures([_with_picture("Lava Dart")], read_text, 60) == 1
    assert read_text.not_read == {}
