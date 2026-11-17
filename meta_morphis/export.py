"""Writes the card data the web app reads: one <format>.json per format.

Run with: uv run python -m meta_morphis.export
"""

import json
import logging
import math
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

from meta_morphis import config
from meta_morphis.db.connection import get_connection
from meta_morphis.db.init_db import init_db
from meta_morphis.meta.repo import get_meta_timestamp
from meta_morphis.meta.service import get_meta_cards
from meta_morphis.models.card import Card, ImageSide
from meta_morphis.name_in_text import (
    PART_COLUMNS,
    REMINDER,
    TEXT_COLUMNS,
    NameInText,
    ReadText,
    fetch_game_words,
    has_long_text,
    is_planeswalker,
    is_summon_printing,
    name_in_low_type_line,
    never_read,
    normalize,
    part_index,
    part_of,
    printed_texts,
    short_name,
)
from meta_morphis.scryfall.service import fetch_cards, get_display_printings
from meta_morphis.utils.text import card_count

log = logging.getLogger(__name__)


class ArtFrom(TypedDict):
    # A side's large picture, and where its artwork sits on it, as
    # [left, top, width, height]: the app cuts the artwork from it
    picture: str
    box: list[float]


class BackSide(TypedDict):
    # The back side's artwork alone, and who painted it
    art: str
    artist: str
    # Where the artwork sits on the back's picture, as art_box on the
    # front's. None when not measured for its kind of card.
    art_box: list[float] | None
    # As ExportCard's art_from
    art_from: ArtFrom | None
    # Where the name sits on the back's picture, as ExportCard's
    # name_box and name_text_boxes: only a transform or modal
    # double-faced card's back, which shows only its own name
    name_box: list[float] | None
    name_text_boxes: list[list[float]]
    # The back's own type, as ExportCard's type: Insectile Aberration's
    # "creature" on Delver of Secrets
    type: str


class SpellPart(TypedDict):
    # The spell's name: Petty Theft on Brazen Borrower
    name: str
    # Where its name sits on the card's picture, as ExportCard's name_box
    # and name_text_boxes, for the question about the spell alone, with
    # the main part's name left in sight. None when it can't be covered
    # everywhere it shows: then the spell is never asked about.
    name_box: list[float] | None
    name_text_boxes: list[list[float]]
    # Its own type, as ExportCard's type: "instant" or "sorcery"
    type: str


class SplitHalf(TypedDict):
    # The half's name: Wear on Wear // Tear
    name: str
    # Where its name sits on the card's picture, as stored - upright,
    # with the halves' writing running up the side - as [left, top,
    # width, height], for the question about this half alone, with the
    # other half's name left in sight. None when it isn't measured, or
    # may be printed in a text box too: then the half is asked about by
    # its artwork only.
    name_box: list[float] | None
    # Its own type, as ExportCard's type: "instant" on Wear, "Room" on a
    # Room's door
    type: str


class ExportCard(TypedDict):
    oracle_id: str
    name: str
    # One picture per physical side: two for a double-faced card
    images: list[str]
    # The same pictures larger, which the app loads only when the player
    # zooms into the card; empty when Scryfall lacks one for any side
    large_images: list[str]
    # Where the artwork sits on the front picture, as shares of its width
    # and height: [left, top, width, height]. The app flies the artwork
    # into it after a right answer. None for a card without a single art
    # box, such as a split card, or a kind not measured.
    art_box: list[float] | None
    # Where the name sits on the front picture, as [left, top, width,
    # height]: the app paints over it to ask which card it is from the
    # full picture. None when the name might show elsewhere on the card
    # and can't be covered there.
    name_box: list[float] | None
    # Where else the name is printed on the front picture, in the text
    # box, as a list of [left, top, width, height]: one box for each
    # line a name runs over. The app paints over these too. Empty when
    # name_box is None.
    name_text_boxes: list[list[float]]
    # The front side's artwork alone, and who painted it. Scryfall asks
    # for the artist to be named wherever the artwork is shown by itself.
    art: str
    artist: str
    # Where the app cuts the front's artwork from instead, for a side
    # whose `art` catches text around it (see OWN_CROPS). The app shows
    # `art` when it can't. None for every other card.
    art_from: ArtFrom | None
    # For each picture in `images`: whether that side is printed sideways,
    # to be read with the card turned a quarter clockwise. The app turns
    # it the right way up when there is room, in landscape.
    horizontal: list[bool]
    # A double-faced card's back side, which a question may show instead
    # of the front: by its artwork, or a transform or modal double-faced
    # card's by its full picture too. None for a card with one side, or
    # whose back lacks its artwork or artist.
    back: BackSide | None
    # The second, smaller spell printed on an adventure or prepare card
    # (see name_in_text.PART_COLUMNS), which a question may ask about
    # instead of the main part, by its full picture only: the artwork is
    # the main part's. Then name_box and name_text_boxes are the main
    # part's alone, and its spell's name stays in sight when it is asked.
    # None for every other card.
    spell: SpellPart | None
    # The two halves of a split card printed sideways (Wear // Tear, the
    # Rooms), first half first, in the modern frame. A question asks
    # about one half: by its half of `art` - the first half's on the
    # left - or by the full picture with its name covered. Then name_box
    # is None: the card has no one name to cover. None for every other
    # card, which is asked about whole.
    halves: list[SplitHalf] | None
    # The type of what the question about the full picture asks for (see
    # main_type): the front's on a double-faced card, the main part's on
    # one with a spell. "Name the creature"
    type: str


class FormatsFile(TypedDict):
    # The formats the app can offer: those whose "all" list has a file
    formats: list[str]
    # For each of those formats, the lists that have a file, e.g.
    # {"pauper": ["all", "creatures", "spells", "lands"]}
    lists: dict[str, list[str]]


class ExportFile(TypedDict):
    format: str
    # When the list of most played cards was last fetched from MTGGoldfish,
    # in UTC, e.g. "2026-10-17T19:18:03Z" - the app warns when it gets old
    list_updated: str
    cards: list[ExportCard]


def image_urls(card: Card) -> list[str]:
    urls: list[str] = []
    for side in card.image_sides():
        # "grid" is the WebP version of "normal" - same picture, smaller file
        url = side.image_uris.get("grid") or side.image_uris.get("normal")
        if url:
            urls.append(url)
    return urls


def large_image_urls(card: Card) -> list[str]:
    urls = [side.image_uris.get("large") for side in card.image_sides()]
    # All sides or none, so the app never mixes sizes on one card
    return [url for url in urls if url] if all(urls) else []


# Where the artwork sits on each kind of card front, as shares of the
# card's width and height: left, top, width, height. Measured on
# Scryfall's pictures on 2026-11-01, by finding samples of each kind's
# artwork in their full pictures; every sample of a kind matched.
ART_BOXES = {
    "1993": (0.113, 0.094, 0.781, 0.449),
    "1997": (0.119, 0.100, 0.764, 0.443),
    "2003": (0.088, 0.119, 0.826, 0.435),
    "2015": (0.079, 0.114, 0.840, 0.440),
}
# The modern frame's planeswalkers: four lines of abilities or more
# (name_in_text.has_long_text) leave less room for the art
PLANESWALKER_ART_BOX = (0.072, 0.101, 0.850, 0.451)
PLANESWALKER_LONG_TEXT_ART_BOX = (0.073, 0.101, 0.849, 0.382)
# Sagas have tall art on the right half; classes and cases on the left
SAGA_ART_BOX = (0.502, 0.113, 0.418, 0.724)
CLASS_ART_BOX = (0.076, 0.113, 0.418, 0.724)
# A saga that is a creature too, as Final Fantasy's summons: its
# reminder text runs across the whole card above the chapters and the
# artwork, which starts lower. Measured on 2026-11-15 on Summon: Esper
# Maduin, the back of Esper Origins, the only one on the lists then.
SAGA_CREATURE_ART_BOX = (0.502, 0.208, 0.419, 0.548)
# Layouts whose front has its frame's usual art box
USUAL_ART_LAYOUTS = {"normal", "transform", "modal_dfc", "adventure", "prepare"}


def art_box(card: Card) -> list[float] | None:
    faces = card.gameplay_faces()
    front = faces[0] if faces else None
    type_line = front.type_line if front else card.type_line
    if card.frame == "2015" and card.layout in ("class", "case"):
        box = CLASS_ART_BOX
    elif card.frame == "2015" and "Saga" in type_line:
        box = SAGA_CREATURE_ART_BOX if "Creature" in type_line else SAGA_ART_BOX
    elif card.layout not in USUAL_ART_LAYOUTS:
        return None
    elif "Planeswalker" in type_line:
        if card.frame != "2015":
            return None
        long_text = has_long_text(front.oracle_text if front else "")
        box = PLANESWALKER_LONG_TEXT_ART_BOX if long_text else PLANESWALKER_ART_BOX
    else:
        found = ART_BOXES.get(card.frame or "")
        if found is None:
            return None
        box = found
    return list(box)


# Where the name sits in the title bar of each kind of card front, as
# shares of the card's width and height, measured on Scryfall's pictures
# on 2026-11-12: where the name starts, its top and height, where the
# mana cost ends on the right, and the width of one mana symbol. The top
# and height leave a little of the title bar above and below the
# letters, which the app paints the name over with.
@dataclass(frozen=True)
class NameArea:
    left: float
    top: float
    height: float
    cost_right: float
    symbol: float


NAME_AREAS = {
    "1993": NameArea(0.075, 0.033, 0.058, 0.918, 0.050),
    "1997": NameArea(0.085, 0.048, 0.046, 0.918, 0.046),
    "2003": NameArea(0.080, 0.050, 0.054, 0.918, 0.047),
    "2015": NameArea(0.080, 0.052, 0.051, 0.928, 0.0515),
}
# A planeswalker's title bar has another shape, thinner and higher, with
# its mana cost further in. Measured on 2026-11-15 on the five on the
# lists then, all in the modern frame - the only one art_box knows a
# planeswalker's artwork in.
PLANESWALKER_NAME_AREAS = {
    "2015": NameArea(0.072, 0.042, 0.040, 0.921, 0.0485),
}
# The small title bar of an adventure's or prepare card's spell, by
# layout (see name_in_text.PART_COLUMNS), in the modern frame. Measured
# on 2026-11-16 on the six on the lists then and Jadzi, Steward of Fate:
# the bar is a little taller on an adventure, but the letters sit in
# the same rows on all of them.
SPELL_NAME_AREAS = {
    "adventure": NameArea(0.080, 0.637, 0.032, 0.479, 0.0435),
    "prepare": NameArea(0.514, 0.637, 0.032, 0.931, 0.0445),
}


# Where a half's name sits on a split card printed sideways, on its
# picture as stored: in a title bar running up the card's left side,
# from the bar's lower end up to the mana cost at its top. All as shares
# of the card's width and height, for the second half, whose bar is the
# upper one: the bar's left and width, where its mana cost starts at the
# top and how far down each symbol takes it, and where its name starts
# at the bottom. The first half's bar is the same, `first_lower` lower.
@dataclass(frozen=True)
class SidewaysNameArea:
    left: float
    width: float
    cost_top: float
    symbol: float
    bottom: float
    first_lower: float


# By kind of split card, in the modern frame, measured on 2026-11-16 on
# the only one of each on the lists then, Wear // Tear and Unholy Annex //
# Ritual Chamber: the same frame on a split card without fuse isn't
# known, nor an older frame's.
SIDEWAYS_NAME_AREAS = {
    "fuse": SidewaysNameArea(0.077, 0.052, 0.0529, 0.0366, 0.440, 0.460),
    "room": SidewaysNameArea(0.058, 0.0555, 0.0567, 0.0356, 0.438, 0.457),
}
# Room left between the mana cost and the name's area, as a share of the
# card's height
SIDEWAYS_NAME_GAP = 0.005
# Layouts with one name, in a title bar like a normal card's. A saga,
# class or case has its text beside its artwork, which
# name_in_text.TEXT_COLUMNS knows.
ONE_NAME_LAYOUTS = {"normal", *TEXT_COLUMNS}
# Frame effects with an icon left of the name: where the name starts then
NAME_AFTER_ICON = {"lesson": 0.165, "tombstone": 0.105}
# A transform card's front shows its own name only, after an icon telling
# which side is up: where the name starts then. Measured on Scryfall's
# pictures on 2026-11-14. A modal double-faced card's sides have their
# icon there too, and the same left edge: measured on 2026-11-17 on the
# three on the lists then.
TRANSFORM_NAME_LEFT = 0.16
# Frame effects whose transform back has its icon left of the name too,
# as the front: a sun and moon, Fable of the Mirror-Breaker's fan, and
# the like. Without one, the back's icon (a triangle pointing down) is
# on the right, where a mana cost would be, and the name starts where a
# normal card's does: so on four of the seven backs on the lists on
# 2026-11-15, Delver of Secrets' and Ajani, Nacatl Pariah's among them.
LEFT_ICON_BACKS = {
    "sunmoondfc",
    "compasslanddfc",
    "originpwdfc",
    "mooneldrazidfc",
    "waxingandwaningmoondfc",
    "fandfc",
}
# Where that icon on the right starts. Measured on Scryfall's pictures
# on 2026-11-15, the same on a planeswalker's back.
BACK_ICON_RIGHT_LEFT = 0.85
# Room left between the name's area and the mana cost, or the title
# bar's rounded end on a card without one
NAME_GAP = 0.02

# Words a card's Oracle text uses for the card itself, where older
# printings print its name instead, e.g. "This land enters tapped" on a
# card printed "Volatile Fjord enters the battlefield tapped"
SELF_REFERENCE = re.compile(
    r"\bthis (creature|artifact|enchantment|land|permanent|planeswalker|battle"
    r"|aura|equipment|vehicle|spell|card|saga|class|case|token)\b",
    re.IGNORECASE,
)
# Printings from this date on print "this creature" and the like, as the
# Oracle text does: Foundations was the first set printed that way. Only
# for new sets - a reprint (The List, a Commander deck) can keep the old text.
SELF_REFERENCE_PRINTED_FROM = "2024-11-15"
NEW_CARD_SET_TYPES = {"expansion", "core"}


def without_keyword_reminders(oracle_text: str, keywords: list[str]) -> str:
    """The Oracle text without the reminder text of its keywords, e.g.
    Flashback's "(You may cast this card from your graveyard...)". A
    keyword's reminder text says "this card" or "this creature" on every
    printing, never the name. Other reminder text stays: Dryad Arbor's
    prints its name, where the Oracle text says "this land".
    """
    lines = []
    for line in oracle_text.split("\n"):
        if any(line.lower().startswith(keyword.lower()) for keyword in keywords):
            line = REMINDER.sub("", line)
        lines.append(line)
    return "\n".join(lines)


def printed_as_oracle(card: Card) -> bool:
    """Printed with "this creature" and the like, as the Oracle text"""
    raw = card.raw
    return (raw.get("released_at") or "") >= SELF_REFERENCE_PRINTED_FROM and raw.get(
        "set_type"
    ) in NEW_CARD_SET_TYPES


def may_show_name_in_text(card: Card) -> bool:
    """True when the name may be printed in the text box: the name or a
    legend's short name in its Oracle or flavor text, a word of the name
    in its flavor text, "this creature"
    and the like on an older printing, or a "Summon" type line - or
    below it, in the type line of a saga, class or case. Always on a
    planeswalker: its type line, read with its text, nearly always has
    a word of its name. Which of
    these the printing really shows, only its picture can tell.
    """
    raw = card.raw
    if name_in_low_type_line(card) or is_planeswalker(card):
        return True
    oracle_text = raw.get("oracle_text") or ""
    # In any case: "birds of paradise" in a flavor text - or in the other
    # part's text, on a card with two parts
    texts = [*printed_texts(card), raw.get("flavor_text") or ""]
    text = "\n".join(texts).lower()
    if card.name.lower() in text or short_name(card.name).lower() in text:
        return True
    # A word of the name by itself in the flavor text: "Lórien" in "the
    # Naith of Lórien" on Lórien Revealed. A short one, like "of", is no
    # sign of the name.
    name_words = {normalize(part) for part in card.name.split()}
    flavor_words = {normalize(part) for part in (raw.get("flavor_text") or "").split()}
    if any(
        len(part) >= 4 and (part in flavor_words or part + "s" in flavor_words)
        for part in name_words
    ):
        return True
    rules = without_keyword_reminders(oracle_text, card.keywords)
    if SELF_REFERENCE.search(rules) and not printed_as_oracle(card):
        return True
    return is_summon_printing(card)


def name_boxes(
    card: Card, read_text: ReadText = never_read, side: int = 0
) -> tuple[list[float] | None, list[list[float]]]:
    """Where the name sits on a side's picture, 0 for the front and 1 for
    a transform or modal double-faced card's back, for the question
    "which card is this?"
    asked with the full card: in the title bar, [left, top, width,
    height] up to just before the mana cost, and wherever `read_text`
    finds it in the text box. (None, []) when the name can't be covered
    everywhere it shows: then the question is never asked about this
    side.
    """
    name_left = name_right = None
    if card.layout == "transform":
        effects = set(card.raw.get("frame_effects") or [])
        if side == 0 or effects & LEFT_ICON_BACKS:
            name_left = TRANSFORM_NAME_LEFT
        else:
            name_right = BACK_ICON_RIGHT_LEFT
        card = face_of(card, side)
    elif card.layout == "modal_dfc":
        # Its icon is on the left on both sides
        name_left = TRANSFORM_NAME_LEFT
        card = face_of(card, side)
    elif side:
        # A battle's back isn't measured
        return None, []
    elif card.layout in PART_COLUMNS:
        # The main part alone: its spell is asked about by itself
        card = part_of(card, 0)
    return with_text_boxes(card, title_name_box(card, name_left, name_right), read_text)


def with_text_boxes(
    card: Card, title: list[float] | None, read_text: ReadText
) -> tuple[list[float] | None, list[list[float]]]:
    """The name's box in its title bar, and where `read_text` finds it in
    the text box too, when it may be printed there: (None, []) when it
    can't be covered there"""
    if title is None or not may_show_name_in_text(card):
        return title, []
    in_text = read_text(card)
    if in_text is None:
        return None, []
    return title, in_text


# The card types a question names, first the one taken from a type line
# with more than one: "Artifact Creature" is asked as a creature
MAIN_TYPES = [
    "Creature",
    "Land",
    "Planeswalker",
    "Battle",
    "Artifact",
    "Enchantment",
    "Instant",
    "Sorcery",
]


def main_type(type_line: str) -> str:
    """The one type a question names a card or a part of it by, from its
    type line: "creature", "land", ... in the order of MAIN_TYPES, and
    "Room" for a Room's door, which as an enchantment would sound wrong.
    "card" for a type line without any of these, or none at all."""
    types: set[str] = set()
    subtypes: set[str] = set()
    for part in type_line.split("//"):
        kinds, _, subs = part.partition("—")
        types.update(kinds.split())
        subtypes.update(subs.split())
    if "Room" in subtypes:
        return "Room"
    return next((kind.lower() for kind in MAIN_TYPES if kind in types), "card")


def front_type(card: Card) -> str:
    """The type the question about the front's full picture names (see
    main_type): the first face's on a card with faces, but a split card
    asked about whole names both halves'"""
    faces = card.raw.get("card_faces") or []
    if faces and card.layout != "split":
        return main_type(faces[0].get("type_line") or "")
    return main_type(card.type_line)


def spell_part(card: Card, read_text: ReadText = never_read) -> SpellPart | None:
    """An adventure's or prepare card's spell, for the question about it
    alone (see name_in_text.PART_COLUMNS); None for every other card"""
    if card.layout not in PART_COLUMNS or len(card.raw.get("card_faces") or []) != 2:
        return None
    spell = part_of(card, 1)
    raw = spell.raw
    area = SPELL_NAME_AREAS[card.layout] if card.frame == "2015" else None
    title = None
    if area is not None and raw.get("lang") == "en":
        title = box_before_cost(area, area.left, spell.mana_cost)
    title, in_text = with_text_boxes(spell, title, read_text)
    return {
        "name": shown_name(spell.name),
        "name_box": title,
        "name_text_boxes": in_text,
        "type": main_type(spell.type_line),
    }


def split_halves(card: Card) -> list[SplitHalf] | None:
    """A split card's two halves printed sideways, each asked about by
    itself (see ExportCard's halves), in the modern frame; None for
    every other card"""
    faces = card.raw.get("card_faces") or []
    if not all(horizontal_sides(card)) or len(faces) != 2 or card.frame != "2015":
        return None
    halves: list[SplitHalf] = []
    for index in (0, 1):
        half = part_of(card, index)
        other = faces[1 - index].get("oracle_text") or ""
        in_text = may_show_name_in_text(half) or half.name.lower() in other.lower()
        area = sideways_name_area(card)
        box = None
        if area is not None and card.raw.get("lang") == "en" and not in_text:
            box = sideways_name_box(area, half.mana_cost, index)
        halves.append(
            {
                "name": shown_name(half.name),
                "name_box": box,
                "type": main_type(half.type_line),
            }
        )
    return halves


def sideways_name_area(card: Card) -> SidewaysNameArea | None:
    if "Room" in card.type_line:
        return SIDEWAYS_NAME_AREAS["room"]
    if "Fuse" in card.keywords:
        return SIDEWAYS_NAME_AREAS["fuse"]
    return None


def sideways_name_box(
    area: SidewaysNameArea, mana_cost: str | None, half: int
) -> list[float]:
    """A half's name's box, from just below its mana cost down to its
    bar's lower end, 0 for the first half and 1 for the second"""
    symbols = len(re.findall(r"\{[^}]*\}", mana_cost or ""))
    lower = area.first_lower if half == 0 else 0
    top = area.cost_top + symbols * area.symbol + SIDEWAYS_NAME_GAP + lower
    bottom = area.bottom + lower
    return [round(value, 4) for value in (area.left, top, area.width, bottom - top)]


def face_of(card: Card, side: int) -> Card:
    """One side of a double-faced card as a card by itself, 0 for the
    front and 1 for the back. A transform card's picture shows only that
    side's name, text and type line - a normal card's or, like Fable of
    the Mirror-Breaker's front, a saga's. The other side's name is
    nowhere on it. Nor on a modal double-faced card's: the strip at its
    bottom left shows the other side's type and mana cost or ability,
    never its name."""
    raw = {key: value for key, value in card.raw.items() if key != "card_faces"}
    face = card.raw["card_faces"][side]
    layout = "saga" if "Saga" in face.get("type_line", "") else "normal"
    return Card.from_raw({**raw, **face, "layout": layout})


def title_name_box(
    card: Card, name_left: float | None = None, name_right: float | None = None
) -> list[float] | None:
    """Where the name sits in the title bar, or None for a card whose
    title bar isn't measured, or that prints more than one name.
    `name_left` is where the name starts after an icon not among the
    frame effects, and `name_right` where an icon in the mana cost's
    place starts: a transform card's."""
    raw = card.raw
    # One name on one side: a split card has two. Of an adventure or a
    # prepare card, only its main part's (see part_of), whose title bar
    # is a normal card's: its spell's is spell_part's.
    one_name = card.layout in ONE_NAME_LAYOUTS or part_index(card) == 0
    if not one_name or raw.get("lang") != "en":
        return None
    areas = PLANESWALKER_NAME_AREAS if "Planeswalker" in card.type_line else NAME_AREAS
    area = areas.get(card.frame or "")
    if area is None:
        return None
    left = max(
        [area.left]
        + ([name_left] if name_left is not None else [])
        + [
            NAME_AFTER_ICON[effect]
            for effect in raw.get("frame_effects") or []
            if effect in NAME_AFTER_ICON
        ]
    )
    return box_before_cost(area, left, card.mana_cost, name_right)


def box_before_cost(
    area: NameArea, left: float, mana_cost: str | None, name_right: float | None = None
) -> list[float]:
    """The name's box in a title bar, from `left` up to just before the
    mana cost, or before an icon starting at `name_right`"""
    symbols = len(re.findall(r"\{[^}]*\}", mana_cost or ""))
    cost_left = area.cost_right - symbols * area.symbol
    right = (cost_left if name_right is None else name_right) - NAME_GAP
    return [round(value, 4) for value in (left, area.top, right - left, area.height)]


def horizontal_sides(card: Card) -> list[bool]:
    """Which sides are printed sideways: both halves of a split card
    (Fire // Ice, the Rooms), and a battle's front. An aftermath card is
    split too, but only its second half is turned, the other way - left
    as it is."""
    sides = len(card.image_sides())
    if card.layout == "split" and "Aftermath" not in card.keywords:
        return [True] * sides
    if card.layout == "battle":
        return [side == 0 for side in range(sides)]
    return [False] * sides


# Sides whose artwork from Scryfall catches text around it, cut by the
# app from the side's large picture instead, at the side's art box.
# Found on 2026-11-15 by comparing the shape of every card's artwork from
# Scryfall with its art box: only Summon: Esper Maduin's, whose frame
# has the artwork lower than a saga's (see SAGA_CREATURE_ART_BOX), was
# off - Scryfall cuts it as a saga's, with text above and below.
OWN_CROPS = {"Summon: Esper Maduin"}


def art_from(
    side: ImageSide, face_name: str, box: list[float] | None
) -> ArtFrom | None:
    """Where the app cuts this side's artwork from, for one in OWN_CROPS"""
    picture = side.image_uris.get("large")
    if face_name not in OWN_CROPS or box is None or picture is None:
        return None
    return {"picture": picture, "box": box}


# Names that read oddly on an answer button, shown shorter in the app:
# for each side's name, the name the app gets. Final Fantasy's summons
# print "Summon:" before the name - and only Summon: Esper Maduin was on
# the lists on 2026-11-15, where the word alone told it apart.
SHOWN_NAMES = {"Summon: Esper Maduin": "Esper Maduin"}


def shown_name(name: str) -> str:
    """The card's name for the app: each side's, joined by " // " as
    Scryfall does, with the names in SHOWN_NAMES shortened"""
    return " // ".join(SHOWN_NAMES.get(side, side) for side in name.split(" // "))


# Double-faced layouts whose back has its frame's usual art box, or a
# saga's or a planeswalker's, as art_box knows them. A battle's back
# isn't measured.
BACK_ART_LAYOUTS = {"transform", "modal_dfc"}


def back_side(card: Card, read_text: ReadText = never_read) -> BackSide | None:
    """A double-faced card's back, for questions about its artwork, and
    a transform or modal double-faced card's about its full picture
    too; None for a card with
    one side, or a back without artwork or artist, or whose artwork is
    of another printing."""
    sides = card.image_sides()
    if len(sides) < 2:
        return None
    back = sides[1]
    art = back.image_uris.get("art") or back.image_uris.get("art_crop")
    if not art or not back.artist or card.id not in art:
        return None
    face = face_of(card, 1)
    box = art_box(face) if card.layout in BACK_ART_LAYOUTS else None
    title, in_text = name_boxes(card, read_text, side=1)
    return {
        "art": art,
        "artist": back.artist,
        "art_box": box,
        "art_from": art_from(back, face.name, box),
        "name_box": title,
        "name_text_boxes": in_text,
        "type": main_type(face.type_line),
    }


def build_card(card: Card, read_text: ReadText = never_read) -> ExportCard | None:
    # Without an id the app can't tell cards apart, and without its
    # pictures and artist it can't show or ask about the card - leave
    # such a card out.
    images = image_urls(card)
    sides = card.image_sides()
    if not card.oracle_id or not images or not sides:
        return None
    front = sides[0]
    # "art" is the WebP version of "art_crop"
    art = front.image_uris.get("art") or front.image_uris.get("art_crop")
    if not art or not front.artist:
        return None
    # The full card shown after answering must be the same printing as
    # the artwork asked about. Scryfall's picture links carry the
    # printing's id, so both links must contain this card's id.
    if card.id not in art or not all(card.id in image for image in images):
        return None
    title, in_text = name_boxes(card, read_text)
    front_box = art_box(card)
    faces = card.gameplay_faces()
    front_name = faces[0].name if len(sides) > 1 and faces else card.name
    return {
        "oracle_id": card.oracle_id,
        "name": shown_name(card.name),
        "images": images,
        "large_images": large_image_urls(card),
        "art_box": front_box,
        "name_box": title,
        "name_text_boxes": in_text,
        "art": art,
        "artist": front.artist,
        "art_from": art_from(front, front_name, front_box),
        "horizontal": horizontal_sides(card),
        "back": back_side(card, read_text),
        "spell": spell_part(card, read_text),
        "halves": split_halves(card),
        "type": front_type(card),
    }


def _staleness(card: Card) -> float:
    # A negative age was written by a clock that ran ahead, so nothing
    # says how old the data really is - it counts as the oldest, as the
    # cache in scryfall/service.py treats it as stale
    return math.inf if card.age < 0 else card.age


def build_export(
    format_name: str,
    cards: list[Card],
    list_updated: str,
    read_text: ReadText = never_read,
) -> ExportFile:
    # The app tells cards apart by oracle id, so each may appear only once.
    # Two names on the list can still lead to one card, e.g. an old
    # spelling and the new one after Scryfall renamed it. Usually both
    # copies are already one object here: get_display_printings gives
    # every copy the same chosen printing, so the first copy is kept. Only
    # a card with no choice, saved or new, reaches here as two different
    # copies. Then the one with the newest Scryfall data is kept - it
    # carries the card's current name - whichever name the list put first.
    kept: dict[str, tuple[Card, ExportCard]] = {}
    for card in cards:
        built = build_card(card, read_text)
        if built is None:
            log.warning(
                f"Leaving out '{card.name}' - no oracle id, picture or artist, "
                "or pictures of different printings"
            )
            continue
        oracle_id = built["oracle_id"]
        other = kept.get(oracle_id)
        if other and _staleness(other[0]) <= _staleness(card):
            log.warning(
                f"Leaving out '{card.name}' - the same card as '{other[0].name}'"
            )
            continue
        if other:
            log.warning(
                f"Leaving out '{other[0].name}' - the same card as '{card.name}'"
            )
        kept[oracle_id] = (card, built)

    # Sorted so the file doesn't reshuffle between runs
    exported = sorted((built for _, built in kept.values()), key=lambda c: c["name"])
    return {"format": format_name, "list_updated": list_updated, "cards": exported}


def write_json(path: Path, data: object) -> None:
    """Writes the whole file under a temporary name first, then swaps it
    in for the old one. A run that stops halfway - killed, or the disk
    full - leaves the old file whole, never a cut-off one the app can't
    read. The temporary file is removed below when the write fails; one
    left by a killed run is removed by export_all at the start of the
    next.
    """
    temp = path.with_name(path.name + ".tmp")
    try:
        temp.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temp.replace(path)
    finally:
        # Gone already after the swap; after a failed write, don't leave
        # the half-written file to be published
        temp.unlink(missing_ok=True)


def load_name_in_text(path: Path) -> dict[str, Any]:
    """The pictures read on earlier runs - see name_in_text.py"""
    if not path.exists():
        return {}
    results: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return results


def write_export(data: ExportFile, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{data['format']}.json"
    write_json(path, data)
    return path


def is_basic_land(card: Card) -> bool:
    """Plains, Snow-Covered Island, Wastes and so on: "Basic" is a word of
    their type line before the dash, e.g. "Basic Snow Land — Island".
    Asking which card a basic land's artwork belongs to teaches nothing.
    """
    return "Basic" in card.type_line.split("—")[0].split()


def export_format(
    conn: sqlite3.Connection,
    format_name: str,
    kind: str,
    out_dir: Path,
    read_text: ReadText = never_read,
) -> Path:
    """Exports one list of one format, e.g. "pauper" and "lands", to a
    file named after the list - see list_name in config.py."""
    name = config.list_name(format_name, kind)
    meta = get_meta_cards(conn, format_name, kind)
    list_updated = _check_list_age(conn, name)
    cards = [card for card in fetch_cards(conn, meta) if not is_basic_land(card)]
    # The printing each card is shown with - see scryfall/artwork.py
    cards = get_display_printings(conn, cards)
    data = build_export(name, cards, list_updated, read_text)
    minimum = config.min_cards(kind)
    if len(data["cards"]) < minimum:
        raise RuntimeError(
            f"Only {len(data['cards'])} usable cards for {name}, "
            f"expected at least {minimum} - not writing the file"
        )
    path = write_export(data, out_dir)
    log.info(f"Wrote {path}: {card_count(len(data['cards']))}")
    return path


def _check_list_age(conn: sqlite3.Connection, format_name: str) -> str:
    """When the MTGGoldfish list was last fetched, as UTC text. Fails if
    that is longer ago than EXPORT_STALE_AFTER - see config.py.
    """
    fetched = get_meta_timestamp(conn, format_name)
    if fetched is None:
        raise RuntimeError(f"The {format_name} list was never fetched from MTGGoldfish")
    age = int(time.time()) - fetched
    if age > config.EXPORT_STALE_AFTER:
        raise RuntimeError(
            f"The {format_name} list was last fetched from MTGGoldfish "
            f"{age // config.DAY} days ago - not publishing it. "
            "The warnings above say why fetching failed."
        )
    return datetime.fromtimestamp(fetched, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def export_all(
    conn: sqlite3.Connection,
    formats: list[str],
    kinds: list[str],
    out_dir: Path,
    read_text: ReadText = never_read,
) -> list[str]:
    """Exports each list of each format on its own: one that fails keeps
    the file it had, and the others are still written. Then writes
    formats.json. Returns the lists that failed.
    """
    # A run killed while write_json was writing - out of memory, or over
    # the time limit - leaves its half-written .tmp file, and the daily
    # run publishes this directory as it is. So clear those out first.
    for stray in out_dir.glob("*.tmp"):
        log.warning(f"Removing {stray} left by an interrupted run")
        stray.unlink()

    failed: list[str] = []
    for format_name in formats:
        for kind in kinds:
            name = config.list_name(format_name, kind)
            try:
                export_format(conn, format_name, kind, out_dir, read_text)
            except Exception:
                # With the full error, so the log says why
                log.exception(
                    f"Could not export {name} - keeping its previous file, if any"
                )
                failed.append(name)

    write_formats(out_dir, formats, kinds)
    return failed


def write_formats(out_dir: Path, formats: list[str], kinds: list[str]) -> Path:
    """Lists what has a card file, new or kept from before - a list that
    has never been exported isn't offered, and a format only once its
    "all" list has a file.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    lists = {
        format_name: [
            kind
            for kind in kinds
            if (out_dir / f"{config.list_name(format_name, kind)}.json").exists()
        ]
        for format_name in formats
    }
    available = [name for name in formats if "all" in lists[name]]
    data: FormatsFile = {
        "formats": available,
        "lists": {name: lists[name] for name in available},
    }
    path = out_dir / "formats.json"
    write_json(path, data)
    return path


def report_left_out(summary: list[str]) -> None:
    """Logs the cards whose name in the text box couldn't be covered
    (NameInText.summary), and on GitHub Actions also puts them on the
    run's page, as its job summary"""
    for line in summary:
        log.info(line)
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary and step_summary:
        with open(step_summary, "a", encoding="utf-8") as file:
            file.write("\n".join(["### Cards asked only by their artwork", *summary]))
            file.write("\n")


def main() -> int:
    """Exit code 1 if any format failed. The files that could be written
    are still there, so the daily run can publish them and then report
    the failure.
    """
    # Show this package's progress and warnings, one plain line each
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    read_text = NameInText(
        load_name_in_text(config.NAME_IN_TEXT_PATH), fetch_game_words()
    )
    try:
        with get_connection() as conn:
            init_db(conn)
            failed = export_all(
                conn,
                config.GOLDFISH_FORMATS,
                config.GOLDFISH_LISTS,
                config.EXPORT_DIR,
                read_text,
            )
    finally:
        # Even after a failure: the pictures read so far took their time
        if read_text.changed:
            write_json(
                config.NAME_IN_TEXT_PATH, dict(sorted(read_text.results.items()))
            )
        report_left_out(read_text.summary())

    if failed:
        log.error(f"Failed to export: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
