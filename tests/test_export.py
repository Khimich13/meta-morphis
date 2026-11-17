import errno
import json
import logging
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pytest import MonkeyPatch

from meta_morphis import config, name_in_text
from meta_morphis.export import (
    BackSide,
    ExportCard,
    art_box,
    back_side,
    build_card,
    build_export,
    export_all,
    export_format,
    face_of,
    horizontal_sides,
    is_basic_land,
    name_boxes,
    report_left_out,
    shown_name,
    spell_part,
    split_halves,
    title_name_box,
    write_json,
)
from meta_morphis.models.card import Card
from meta_morphis.models.meta import MetaEntry
from meta_morphis.name_in_text import ReadText


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
    """The MTGGoldfish list was fetched at `fetched`, and it is `now`"""
    monkeypatch.setattr(
        "meta_morphis.export.get_meta_timestamp", lambda conn, name: fetched
    )
    monkeypatch.setattr("meta_morphis.export.time.time", lambda: now)


def test_build_card_single_faced() -> None:
    card = Card.from_raw(_raw("Hydroblast", oracle_id="b94c0336"))
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
    }


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
    # A modal double-faced card's back has the usual art box too
    modal = back_side(_double_faced("modal_dfc", {"type_line": "Land"}))
    assert modal and modal["art_box"] == [0.079, 0.114, 0.840, 0.440]


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


def test_a_modal_double_faced_cards_back_is_never_asked_by_its_picture() -> None:
    # Each side names the other one too
    modal = _double_faced("modal_dfc", {}, lang="en")
    assert name_boxes(modal, side=1) == (None, [])


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


# During a rename the old name can still sit fresh in the cache while the
# new one is fetched this run. fetch_cards returns cached cards first, so
# the order can't decide: the newest Scryfall data has the current name.
# In the pipeline the two copies stay different only when no printing was
# chosen for the card - otherwise both are the same chosen printing.
def test_build_export_keeps_the_newest_copy_of_a_card(
    caplog: pytest.LogCaptureFixture,
) -> None:
    old = Card.from_raw(_raw("Old Name", oracle_id="n"))
    old.age = 5 * config.DAY
    new = Card.from_raw(_raw("New Name", oracle_id="n"))
    data = build_export("pauper", [old, new], "2026-10-17T19:18:03Z")
    assert [c["name"] for c in data["cards"]] == ["New Name"]
    assert "Leaving out 'Old Name' - the same card as 'New Name'" in caplog.text


# A clock that ran ahead gives a negative age - that says nothing about
# how new the data is, so the copy with a real age wins
def test_build_export_does_not_take_a_negative_age_as_newest(
    caplog: pytest.LogCaptureFixture,
) -> None:
    ahead = Card.from_raw(_raw("Old Name", oracle_id="n"))
    ahead.age = -config.DAY
    new = Card.from_raw(_raw("New Name", oracle_id="n"))
    new.age = 5 * config.DAY
    data = build_export("pauper", [new, ahead], "2026-10-17T19:18:03Z")
    assert [c["name"] for c in data["cards"]] == ["New Name"]
    assert "Leaving out 'Old Name' - the same card as 'New Name'" in caplog.text


def test_export_format_writes_the_file(
    conn: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    meta = [MetaEntry(name="Lórien Revealed", rank=1)]
    cards = [Card.from_raw(_raw("Lórien Revealed", oracle_id="l"))]
    monkeypatch.setattr(
        "meta_morphis.export.get_meta_cards", lambda conn, format_name, kind: meta
    )
    _list_fetched(monkeypatch, FETCHED)
    monkeypatch.setattr("meta_morphis.export.fetch_cards", lambda conn, meta: cards)
    monkeypatch.setattr(
        "meta_morphis.export.get_display_printings", lambda conn, cards: cards
    )
    monkeypatch.setattr(config, "EXPORT_MIN_CARDS", 1)

    caplog.set_level(logging.INFO)
    path = export_format(conn, "pauper", "all", tmp_path / "data")

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
            }
        ],
    }


# A failed fetch must not replace the file with an empty or half-empty one
def test_export_format_fails_with_too_few_cards(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    cards = [Card.from_raw(_raw("Hydroblast", oracle_id="h"))]
    monkeypatch.setattr(
        "meta_morphis.export.get_meta_cards", lambda conn, format_name, kind: []
    )
    _list_fetched(monkeypatch, FETCHED)
    monkeypatch.setattr("meta_morphis.export.fetch_cards", lambda conn, meta: cards)
    monkeypatch.setattr(
        "meta_morphis.export.get_display_printings", lambda conn, cards: cards
    )
    monkeypatch.setattr(config, "EXPORT_MIN_CARDS", 2)

    with pytest.raises(RuntimeError, match="Only 1 usable cards"):
        export_format(conn, "pauper", "all", tmp_path / "data")

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


def test_export_format_uses_the_chosen_printing(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    default = Card.from_raw(_raw("Lightning Bolt", oracle_id="bolt"))
    chosen = Card.from_raw(
        {
            **_raw("Lightning Bolt", oracle_id="bolt"),
            "id": "m10",
            "artist": "Christopher Moeller",
            "image_uris": {"grid": "grid/m10.webp", "art": "art/m10.webp"},
        }
    )
    monkeypatch.setattr(
        "meta_morphis.export.get_meta_cards", lambda conn, format_name, kind: []
    )
    _list_fetched(monkeypatch, FETCHED)
    monkeypatch.setattr("meta_morphis.export.fetch_cards", lambda conn, meta: [default])
    monkeypatch.setattr(
        "meta_morphis.export.get_display_printings", lambda conn, cards: [chosen]
    )
    monkeypatch.setattr(config, "EXPORT_MIN_CARDS", 1)

    path = export_format(conn, "pauper", "all", tmp_path)

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
    monkeypatch.setattr(
        "meta_morphis.export.get_meta_cards", lambda conn, format_name, kind: []
    )
    monkeypatch.setattr("meta_morphis.export.fetch_cards", lambda conn, meta: cards)
    monkeypatch.setattr(
        "meta_morphis.export.get_display_printings", lambda conn, cards: cards
    )
    monkeypatch.setattr(config, "EXPORT_MIN_CARDS", 1)
    _list_fetched(monkeypatch, FETCHED, now=FETCHED + age_days * 24 * 60 * 60)

    if publishes:
        export_format(conn, "pauper", "all", tmp_path)
        assert (tmp_path / "pauper.json").exists()
    else:
        with pytest.raises(RuntimeError, match="4 days ago - not publishing"):
            export_format(conn, "pauper", "all", tmp_path)
        assert not (tmp_path / "pauper.json").exists()


def test_export_format_fails_without_any_list(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "meta_morphis.export.get_meta_cards", lambda conn, format_name, kind: []
    )
    _list_fetched(monkeypatch, None)

    with pytest.raises(RuntimeError, match="never fetched"):
        export_format(conn, "pauper", "all", tmp_path)


def _fake_export(
    fails: tuple[str, ...] = (),
) -> Callable[[sqlite3.Connection, str, str, Path, ReadText], Path]:
    """export_format that writes an empty file, or fails for the named lists"""

    def fake_export(
        conn: sqlite3.Connection,
        format_name: str,
        kind: str,
        out_dir: Path,
        read_text: ReadText,
    ) -> Path:
        name = config.list_name(format_name, kind)
        if name in fails:
            raise RuntimeError("MTGGoldfish's page changed")
        path = out_dir / f"{name}.json"
        path.write_text("{}", encoding="utf-8")
        return path

    return fake_export


def test_export_all_keeps_going_when_one_list_fails(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    # Modern's lands list was exported before and now fails; Standard's
    # "all" list never worked
    (tmp_path / "modern-lands.json").write_text('{"old": true}', encoding="utf-8")
    monkeypatch.setattr(
        "meta_morphis.export.export_format", _fake_export(("modern-lands", "standard"))
    )

    failed = export_all(
        conn, ["pauper", "modern", "standard"], ["all", "lands"], tmp_path
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
    monkeypatch.setattr("meta_morphis.export.export_format", _fake_export(("pauper",)))

    export_all(conn, ["pauper"], ["all"], tmp_path)

    # The half-written file is gone, not published; the old file stays
    assert sorted(f.name for f in tmp_path.iterdir()) == ["formats.json", "pauper.json"]
    assert json.loads((tmp_path / "pauper.json").read_text(encoding="utf-8")) == {
        "old": True
    }


def test_export_all_reports_no_failures(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr("meta_morphis.export.export_format", _fake_export())

    assert export_all(conn, ["pauper"], ["all", "creatures"], tmp_path) == []
    assert (tmp_path / "pauper-creatures.json").exists()
    formats = json.loads((tmp_path / "formats.json").read_text(encoding="utf-8"))
    assert formats == {"formats": ["pauper"], "lists": {"pauper": ["all", "creatures"]}}


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


def test_export_format_leaves_out_basic_lands_and_needs_fewer_lands(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    cards = [
        Card.from_raw(
            _raw("Mountain", oracle_id="m", type_line="Basic Land — Mountain")
        ),
        Card.from_raw(_raw("Bojuka Bog", oracle_id="b", type_line="Land")),
    ]
    monkeypatch.setattr(
        "meta_morphis.export.get_meta_cards", lambda conn, format_name, kind: []
    )
    _list_fetched(monkeypatch, FETCHED)
    monkeypatch.setattr("meta_morphis.export.fetch_cards", lambda conn, meta: cards)
    monkeypatch.setattr(
        "meta_morphis.export.get_display_printings", lambda conn, cards: cards
    )
    # One card left: enough for a lands list here, too few for any other
    monkeypatch.setattr(config, "EXPORT_MIN_LANDS", 1)
    monkeypatch.setattr(config, "EXPORT_MIN_CARDS", 2)

    path = export_format(conn, "pauper", "lands", tmp_path)

    written = json.loads(path.read_text(encoding="utf-8"))["cards"]
    assert [card["name"] for card in written] == ["Bojuka Bog"]
    with pytest.raises(RuntimeError, match="expected at least 2"):
        export_format(conn, "pauper", "creatures", tmp_path)


def test_list_names_and_addresses() -> None:
    assert config.list_name("pauper", "all") == "pauper"
    assert config.list_name("pauper", "lands") == "pauper-lands"
    assert config.GOLDFISH_LIST_URLS["pauper"] == (
        "https://www.mtggoldfish.com/format-staples/pauper/full/all"
    )
    assert config.GOLDFISH_LIST_URLS["modern-creatures"] == (
        "https://www.mtggoldfish.com/format-staples/modern/full/creatures"
    )
    assert len(config.GOLDFISH_LIST_URLS) == 20


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
    }


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
        {"name": "Wear", "name_box": [0.077, 0.5911, 0.052, 0.3089]},
        {"name": "Tear", "name_box": [0.077, 0.0945, 0.052, 0.3455]},
    ]
    assert split_halves(room) == [
        {"name": "Unholy Annex", "name_box": [0.058, 0.5899, 0.0555, 0.3051]},
        {"name": "Ritual Chamber", "name_box": [0.058, 0.1685, 0.0555, 0.2695]},
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
    assert split_halves(old) is None
    assert split_halves(Card.from_raw(_raw("Counterspell"))) is None
