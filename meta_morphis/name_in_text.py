"""Finds where a card's name is printed in its text box, by reading the
card's picture with Tesseract (https://github.com/tesseract-ocr/tesseract),
so the app can paint over it there too and ask which card it is.

Scryfall's data says whether the name is printed in the text, but not
where on the picture, and not always rightly for an old printing: its
Oracle text says "this creature" where the printing may say the name, or
something else. So the picture itself is read, once per printing, and
the result is kept in config.NAME_IN_TEXT_PATH for the next runs. A
transform or modal double-faced card's sides are each read as a card
by itself.

A reading leaves the card out when anything like a word of its name is
left uncovered - a word read with a letter wrong, the name split up or
run together - or when the text could not be read well. Leaving a card
out costs one kind of question; showing its name gives the answer away.
"""

import functools
import gzip
import hashlib
import io
import itertools
import json
import logging
import os
import re
import shutil
import statistics
import subprocess
import tempfile
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageFilter, ImageOps

from meta_morphis import config
from meta_morphis.models.card import Card
from meta_morphis.scryfall.client import fetch_catalog
from meta_morphis.utils.http import RequestUnavailable
from meta_morphis.utils.text import card_count

log = logging.getLogger(__name__)

# Where a card's name is printed in its text box, as [left, top, width,
# height] shares of its picture; None when that isn't known for sure
ReadText = Callable[[Card], list[list[float]] | None]

# Raise it when the reading changes, so every printing is read again
READER_VERSION = 12

# Where to read on a card's picture, as shares of its width and height:
# the text box, below the type line and above the artist's credit, the
# same on every frame but those of TEXT_COLUMNS. Measured on Scryfall's pictures on 2026-11-12.
TEXT_LEFT, TEXT_RIGHT = 0.07, 0.93
TEXT_TOP, TEXT_BOTTOM = 0.60, 0.94
# Before Sixth Edition, a creature's type line read "Summon" and its
# creature type, which for some was the name: "Summon Ball Lightning".
# Such a printing has its type line read too.
SUMMON_UNTIL = "1999-04-21"
TYPE_LINE_TOP = 0.55
# That type line by itself, as left, top, right and bottom: see
# summon_type_line. Read a second time a little taller, which reads some
# Tesseract misses in the first: "Summon Bird" on Welkin Hawk. Measured on
# Scryfall's pictures on 2026-11-18.
SUMMON_TYPE_LINES = (
    (0.07, TYPE_LINE_TOP, 0.93, TEXT_TOP),
    (0.07, 0.54, 0.93, 0.605),
)
# Where the type starts on such a type line: "Summon", or "Creature" on
# the printings of the time that print "Artifact Creature" or "Creature —
# Merchant" - is_summon_printing can't tell those apart
TYPE_STARTS = ("summon", "creature")
# The most words read after "Summon" taken for its type: "People of the
# Woods" has four
SUMMON_TYPE_WORDS = 4
# A saga has its text in a column left of its artwork, a class and a case
# right of it: the column's left and right. The type line is below both.
# Measured on Scryfall's pictures on 2026-11-14.
TEXT_COLUMNS = {"saga": (0.07, 0.50), "class": (0.50, 0.93), "case": (0.50, 0.93)}
COLUMN_TOP, COLUMN_BOTTOM = 0.11, 0.84
# Their type line, as left, top, right and bottom
LOW_TYPE_LINE = (0.07, 0.84, 0.93, 0.905)
# Cards with a second, smaller spell printed on their one side, in a box
# of its own in half the text box - its name, mana cost and type line
# above its text: on the left for an adventure (an omen too, which
# Scryfall counts as one), on the right for a prepare card. The other
# half has the main part's text. Each part is asked about by itself
# (see part_of), and the whole text box is read for its name: its own
# half first. The halves' left and right, for the main part and the
# spell. Measured on Scryfall's pictures on 2026-11-16.
PART_COLUMNS = {
    "adventure": ((0.50, 0.93), (0.07, 0.50)),
    "prepare": ((0.07, 0.50), (0.50, 0.93)),
}
# Where the spell's text starts, below its type line
SPELL_TEXT_TOP = 0.72
# A planeswalker's type line sits right below its artwork, higher than
# other cards', and moves up with it when the abilities take this many
# lines or more. Its type there is nearly always a word of its name:
# "Legendary Planeswalker — Teferi". So the type line is read with the
# text, from the artwork's bottom: as in export.PLANESWALKER_ART_BOX
# and PLANESWALKER_LONG_TEXT_ART_BOX.
PLANESWALKER_LONG_TEXT_LINES = 4
PLANESWALKER_TEXT_TOP = 0.552
PLANESWALKER_LONG_TEXT_TOP = 0.483
# A transform card's back prints its type line in white on gold, which
# Tesseract misses when reading it with the darker text below. When the
# type isn't found there, the type line is read again by itself, this
# tall from the same top, enlarged in color: that finds it on Ajani,
# Nacatl Avenger and Tamiyo, Seasoned Scholar, where grayscale doesn't.
# Measured on Scryfall's pictures on 2026-11-17.
PLANESWALKER_TYPE_LINE_HEIGHT = 0.075
# A part of the picture: its left, top, right and bottom
Area = tuple[float, float, float, float]
# Tesseract reads small print better enlarged
SCALE = 2
# Raise it when read_words or parse_tsv prepare a picture or keep its
# words in another way, so the words saved the old way (see Picture) are
# read again. SCALE and SMOOTH_SIZE are checked by themselves.
PREPARED = 1
# The ways a picture is read: enlarged and in color; in grayscale at its
# own size; and in grayscale smoothed. Each reading misses words another
# one sees, even when Tesseract is sure of it - "Lord Windgrace can be
# your commander" read without "Lord" in color, "If Abu Ja'far is put" on
# Abu Ja'far in Chronicles read as "icone" - so a picture is read in all
# the ways of its frame, and the name covered wherever any finds it (see
# name_in_text). Grayscale reads the textured text box of an old frame
# far better: there color sees words in the texture. Smoothing wipes that
# texture away on the old frames gray still can't read - Ball Lightning's
# and Goblin Tinkerer's in Fifth Edition and Anthologies - but blurs a
# newer frame's letters, so only old frames get it.
READINGS = ("color", "gray", "smooth")
NEW_FRAME_READINGS = ("color", "gray")
# The old frames. Found on samples of every card on 2026-11-18: with the
# first reading Tesseract was sure of, 8 of 70 old cards showed their
# name, and 1 of about 460 newer ones (Lord Windgrace). Reading newer
# frames in both their ways left out 1 to 3% more of them; smoothing them
# too, a further 2 to 5%, over misread words.
OLD_FRAMES = ("1993", "1997")
# How many pixels across the smoothing takes the middle value of: enough
# to wipe out the texture's specks and keep the letters. Tried on those
# two cards on 2026-11-17: 3 left specks read as words.
SMOOTH_SIZE = 5
# Room added around each name found, as shares of the card's width and
# height: Tesseract's boxes can end a letter short. Less on the left,
# where a name starting a line is next to the text box's border.
PAD_LEFT, PAD_RIGHT, PAD_Y = 0.002, 0.006, 0.003
# A word of the name standing alone - "Locthwain's persistence" in a
# flavor text - is covered too, up to this many. A card with more is left
# out: so many covers would look odd.
MAX_LIKE_NAME = 3
# Readings Tesseract is less sure of than this, on average over the
# words it read (0 to 100), may have missed the name
MIN_CONFIDENCE = 60
# A reading with fewer words than this share of the Oracle text's words
# may have missed part of the text, and the name with it. Counted without
# reminder text, which not every printing prints.
MIN_WORDS_READ = 0.5
# Boxes overlapping over more than this share of the smaller one, across
# and down, are over the same word (see add_boxes)
SAME_PLACE = 0.5
# How much of a word another reading took for the name read badly must be
# covered across for that doubt to be passed over (see name_in_text)
COVERED = 0.9
# How many letters of a word after the name may be run together with its
# last word and still be taken for the name: "is" in "Lu Buis"
MAX_RUN_ON = 2
# Reminder text, in brackets
REMINDER = re.compile(r"\([^)]*\)")


# A word one reading takes for the name read badly: why, and where, as a
# box in pixels from find_name, in shares of the picture from
# name_in_reading
Doubt = tuple[str, list[float]]


class LeftOut(Exception):
    """The name can't be covered everywhere it shows, so the card is left
    out: asked only by its artwork. Each argument says why, one per
    reading tried (see READINGS)."""


@dataclass(frozen=True)
class Word:
    """A word Tesseract read, and where, in pixels of the picture"""

    text: str
    left: float
    top: float
    right: float
    bottom: float
    # The line it is on: words of one name on another line get their own box
    line: tuple[str, str, str]


def is_summon_printing(card: Card) -> bool:
    """A creature printed with a "Summon" type line"""
    released = card.raw.get("released_at") or ""
    return "Creature" in card.type_line and released < SUMMON_UNTIL


def name_in_low_type_line(card: Card) -> bool:
    """A saga, class or case with a word of its name in its type line:
    Urza's Saga, whose type line ends "Urza's Saga" too"""
    if card.layout not in TEXT_COLUMNS:
        return False
    type_words = {normalize(word) for word in card.type_line.split()}
    return any(
        len(part) >= 4 and part in type_words
        for part in (normalize(word) for word in card.name.split())
    )


def is_planeswalker(card: Card) -> bool:
    return "Planeswalker" in card.type_line


def has_long_text(oracle_text: str) -> bool:
    """A planeswalker's abilities take so many lines that its artwork is
    shorter"""
    return len(oracle_text.splitlines()) >= PLANESWALKER_LONG_TEXT_LINES


def planeswalker_type(card: Card) -> str | None:
    """A planeswalker's type, normalized, when it is a word of its name:
    "teferi" on Teferi, Time Raveler, "nixilis" on Ob Nixilis, the
    Adversary - not "liliana" on Professor Onyx"""
    if not is_planeswalker(card) or "—" not in card.type_line:
        return None
    subtype = normalize(card.type_line.split("—")[-1])
    name_words = {normalize(word) for word in card.name.split()}
    return subtype if subtype in name_words else None


def part_of(card: Card, part: int) -> Card:
    """One part of a card in PART_COLUMNS as a card by itself, 0 for the
    main part and 1 for the spell: its own name, mana cost, type line and
    text, with both parts in its card_faces still, as both are printed."""
    raw = {**card.raw, **card.raw["card_faces"][part]}
    one = Card.from_raw(raw)
    # Card.from_raw takes the first face's mana cost for a card with faces
    one.mana_cost = raw.get("mana_cost") or None
    return one


def part_index(card: Card) -> int | None:
    """Which part of a card in PART_COLUMNS this is (see part_of): 0 for
    the main part, 1 for the spell. None for any other card, and for such
    a card as a whole."""
    if card.layout not in PART_COLUMNS:
        return None
    names = [face.get("name") for face in card.raw.get("card_faces") or []]
    return names.index(card.name) if card.name in names else None


def areas_to_read(card: Card) -> list[Area]:
    """Where the name may be printed outside the title bar: the text
    first, then a type line apart from it - or, for a part of a card
    with two (see part_of), its own half of the text box first, then the
    other part's"""
    part = part_index(card)
    if part is not None:
        tops = (TEXT_TOP, SPELL_TEXT_TOP)
        columns = PART_COLUMNS[card.layout]
        return [
            (columns[i][0], tops[i], columns[i][1], TEXT_BOTTOM)
            for i in (part, 1 - part)
        ]
    if is_planeswalker(card):
        long_text = has_long_text(card.raw.get("oracle_text") or "")
        top = PLANESWALKER_LONG_TEXT_TOP if long_text else PLANESWALKER_TEXT_TOP
        return [(TEXT_LEFT, top, TEXT_RIGHT, TEXT_BOTTOM)]
    column = TEXT_COLUMNS.get(card.layout)
    if column is None:
        top = TYPE_LINE_TOP if is_summon_printing(card) else TEXT_TOP
        return [(TEXT_LEFT, top, TEXT_RIGHT, TEXT_BOTTOM)]
    areas: list[Area] = [(column[0], COLUMN_TOP, column[1], COLUMN_BOTTOM)]
    if name_in_low_type_line(card):
        areas.append(LOW_TYPE_LINE)
    return areas


def short_name(name: str) -> str:
    """The name a legend's text calls it by: "Ragavan" for "Ragavan,
    Nimble Pilferer\""""
    return name.split(",")[0]


def normalize(word: str) -> str:
    """Lower case, letters and digits only, accents taken off: "Lórien's"
    and "lorien's," both become "loriens\""""
    plain = unicodedata.normalize("NFKD", word)
    plain = "".join(char for char in plain if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]", "", plain.lower())


def matches(read: str, wanted: str) -> bool:
    """A word read is the word wanted: the same, with a possessive "s"
    ("Snuff Out's"), or for a word of 4 letters or more, one letter
    read wrong, missing or extra"""
    if read in (wanted, wanted + "s"):
        return True
    if len(wanted) < 4 or abs(len(read) - len(wanted)) > 1:
        return False
    if len(read) == len(wanted):
        return sum(a != b for a, b in zip(read, wanted)) <= 1
    shorter, longer = sorted((read, wanted), key=len)
    return any(longer[:i] + longer[i + 1 :] == shorter for i in range(len(longer)))


def edits(a: str, b: str) -> int:
    """How many letters must change, go or come to make a into b"""
    row = list(range(len(b) + 1))
    for i, letter in enumerate(a, 1):
        before, row[0] = row[0], i
        for j, other in enumerate(b, 1):
            before, row[j] = (
                row[j],
                min(row[j] + 1, row[j - 1] + 1, before + (letter != other)),
            )
    return row[-1]


def printed_texts(card: Card) -> list[str]:
    """The Oracle text printed on the card's picture: its own, and for a
    part of a card with two (see part_of), the other part's too"""
    own = card.raw.get("oracle_text") or ""
    if part_index(card) is None:
        return [own]
    return [face.get("oracle_text") or "" for face in card.raw["card_faces"]]


def words_of_text(card: Card) -> frozenset[str]:
    """The words of the card's Oracle text, normalized: "cant" for "can't\""""
    oracle_text = "\n".join(printed_texts(card))
    words = (normalize(word) for word in re.split(r"[^\w'’]+", oracle_text))
    return frozenset(word for word in words if word)


# A named ability or an ability word at a line's start, before its dash:
# "Wasp's Sting — When this creature enters"
ABILITY_NAME = re.compile(r"^[^\n—]* — ", re.MULTILINE)


def rules_words(card: Card) -> frozenset[str]:
    """Words of the name its own Oracle text uses apart from the name,
    normalized: "graveyard" in "exile a card from a graveyard" on
    Graveyard Trespasser, or in the plural, "cards from graveyards" on
    Graveyard Glutton. Printed there, it is a word of the rules, which
    tells no more of which card it is than a subtype. Not from the name of
    an ability: "Wasp's Sting" gives The Wondrous Wasp away."""
    text = ABILITY_NAME.sub(" ", card.raw.get("oracle_text") or "")
    for one_name in (card.name, short_name(card.name)):
        text = re.sub(re.escape(one_name), " ", text, flags=re.IGNORECASE)
    used = {normalize(word) for word in re.split(r"[^\w'’]+", text)}
    return frozenset(
        part
        for part in (normalize(word) for word in card.name.split())
        if part in used or part + "s" in used
    )


def name_end(
    words: list[Word], read: list[str], start: int, wanted: list[str]
) -> int | None:
    """Where the name, its words normalized as `wanted`, ends when it
    starts at `start` among the words `read`, normalized: the index past
    its last word. None when it doesn't start there.

    Word by word first, as matches() allows. Then letter for letter, for
    a name read in other pieces: broken at a line's end ("Superior
    Spider-" and "Man") or run together ("Chalice.of" before "the Void").
    A piece running two words together has a box of its own that may end
    short of its last letters - "Jackal,Pup" ends inside "Pup" - so it is
    only taken when another piece of the name follows it on its line,
    whose box reaches past it. The last piece may run on into a short
    word after the name (MAX_RUN_ON).
    """
    end = start + len(wanted)
    if end <= len(read) and all(
        matches(read[i], part) for i, part in zip(range(start, end), wanted)
    ):
        return end
    whole = "".join(wanted)
    # Where one word of the name ends and the next starts, in `whole`
    joins = set(itertools.accumulate(len(part) for part in wanted[:-1]))
    so_far = ""
    for i in range(start, len(read)):
        runs_together = any(
            len(so_far) < at < len(so_far) + len(read[i]) for at in joins
        )
        so_far += read[i]
        done = so_far in (whole, whole + "s")
        # The name's last word run together with a short word after it:
        # "Lu Buis" for "Lu Bu is". Its box covers that word too.
        run_on = (
            i > start
            and so_far.startswith(whole)
            and len(so_far) - len(whole) <= MAX_RUN_ON
        )
        if run_on and not runs_together:
            return i + 1
        if runs_together and (
            done or i + 1 == len(read) or words[i + 1].line != words[i].line
        ):
            return None
        if done:
            return i + 1
        if not whole.startswith(so_far):
            return None
    return None


def find_name(
    words: list[Word],
    name: str,
    game_words: frozenset[str] = frozenset(),
    text_words: frozenset[str] = frozenset(),
    doubts: list[Doubt] | None = None,
) -> list[list[float]]:
    """Boxes in pixels, [left, top, right, bottom], around each time the
    name is printed among the words: one box per line it runs over. The
    full name is looked for first, then a legend's short name.

    A word left over that is like one of the name's, or starts like one,
    may be the name read badly. When it has a piece of the name next to
    it, or is a piece of the name itself, it may well be, and the card is
    left out (LeftOut): "Goblin" before "Mafr0n" on Goblin Matron, or
    "Jackal,Pup" run together, whose box may be too short (see name_end).
    Standing alone, it is left as it is when it is a game word - a
    subtype such as "Goblin" in "a Goblin card", or a word of the card's
    own rules (see rules_words), among `game_words`, normalized - which
    says nothing of which card it is. Any other is
    covered: a place or a person, such as "Locthwain's" or "coastline" in
    a flavor text, gives the answer away. So is a card left out with more
    than MAX_LIKE_NAME to cover.

    A word of the card's own Oracle text, among `text_words`, normalized,
    is never the name read badly, unless it is a word or a piece of the
    name: "can't" and "cast" on Orim's Chant, "Flashback" on Flash of
    Insight.
    """
    read = [normalize(word.text) for word in words]
    used: set[int] = set()
    boxes: list[list[float]] = []
    names = [name] if short_name(name) == name else [name, short_name(name)]
    for one_name in names:
        wanted = [normalize(part) for part in one_name.split()]
        wanted = [part for part in wanted if part]
        if not wanted:
            continue
        for start in range(len(words)):
            end = name_end(words, read, start, wanted)
            if end is None:
                continue
            span = range(start, end)
            if used.intersection(span):
                continue
            used.update(span)
            lines: dict[tuple[str, str, str], list[float]] = {}
            for i in span:
                word = words[i]
                box = lines.setdefault(
                    word.line, [word.left, word.top, word.right, word.bottom]
                )
                box[:] = [
                    min(box[0], word.left),
                    min(box[1], word.top),
                    max(box[2], word.right),
                    max(box[3], word.bottom),
                ]
            boxes.extend(lines.values())

    every_name_word = {normalize(part) for part in name.split()}
    name_words = {part for part in every_name_word if len(part) >= 4}
    # A name of short words only, like "Fog", can't be told from other
    # short words read with a letter wrong
    if not name_words:
        raise LeftOut("its words are too short to check")
    # The name in one piece, to find pieces of it: "spider" and "man" in
    # "superiorspiderman"
    whole = "".join(normalize(part) for part in name.split())
    # Game words left in sight, also in the plural ("Storm Giants" has the
    # Giant type): only for a name of more than one word, whose other
    # words tell it from the game word itself
    plain = {
        part
        for part in name_words
        if part in game_words or part.endswith("s") and part[:-1] in game_words
    }
    if len(name.split()) == 1:
        plain = set()

    def of_the_text(text: str) -> bool:
        """A word of the Oracle text that isn't a word or a piece of the
        name, nor a word of it with an "s": "Wasp's Sting" on The
        Wondrous Wasp"""
        if text not in text_words or text in whole:
            return False
        return not (text.endswith("s") and text[:-1] in every_name_word)

    def next_word(i: int, step: int) -> int:
        """The word before or after i (step -1 or 1), passing over up to
        two of 1 or 2 letters: bits of the border or of a symbol, read as
        a word between "Phyrexian" and "Devourer"."""
        i += step
        for _ in range(2):
            if 0 <= i < len(read) and len(read[i]) < 3:
                i += step
        return i

    def near_name(i: int) -> bool:
        """The word at i may be a piece or a word of the name, read badly.
        Not when it is part of the name found: then it was read right, as
        "Fire Magic" after the ability "Fire — 0 —" on Fire Magic."""
        if not 0 <= i < len(read) or i in used:
            return False
        if len(read[i]) < 3 or of_the_text(read[i]):
            return False
        return read[i] in whole or any(
            edits(read[i], part) <= 2 for part in name_words if len(part) >= 5
        )

    # The name's words in order, short ones too
    parts = [part for part in (normalize(part) for part in name.split()) if part]

    def beside_name(i: int, step: int) -> bool:
        """The word beside the word at i, before or after it (step -1 or
        1), may be a piece or a word of the name read badly. Words going
        on with the name from the word at i, read right, are passed over:
        "of the" before "gods" in "an act of the gods" on Anger of the
        Gods. The word past them is checked against the name's word
        expected there too: "act" isn't like "Anger", but "Gocls" after
        "Anger of the" is like "Gods"."""
        places: list[int | None] = [
            at for at, part in enumerate(parts) if matches(read[i], part)
        ]
        for at in places or [None]:
            j, expected = i + step, None
            if at is not None:
                at += step
                while (
                    0 <= at < len(parts)
                    and 0 <= j < len(read)
                    and matches(read[j], parts[at])
                ):
                    j, at = j + step, at + step
                expected = parts[at] if 0 <= at < len(parts) else None
            j = next_word(j - step, step)
            if near_name(j):
                return True
            if (
                expected
                and 0 <= j < len(read)
                and j not in used
                and edits(read[j], expected) <= len(expected) // 2
            ):
                return True
        return False

    like_name: list[Word] = []
    for i, text in enumerate(read):
        if i in used or of_the_text(text):
            continue
        like = [part for part in name_words if matches(text, part)]
        if not like and not any(text.startswith(part) for part in name_words):
            continue
        # Only starts like a word of the name: a piece of the name run
        # together when it is all in the name ("jackalpup"), another word
        # to cover when it isn't ("coastline")
        if (not like and text in whole) or beside_name(i, -1) or beside_name(i, 1):
            reason = (
                f"'{words[i].text}' is left in its text, and may be part of "
                "the name read badly"
            )
            if doubts is None:
                raise LeftOut(reason)
            word = words[i]
            doubts.append((reason, [word.left, word.top, word.right, word.bottom]))
            continue
        if like and all(part in plain for part in like):
            continue
        like_name.append(words[i])
    if len(like_name) > MAX_LIKE_NAME:
        listed = ", ".join(f"'{word.text}'" for word in like_name)
        raise LeftOut(f"too many words like it are left: {listed}")
    return boxes + [
        [word.left, word.top, word.right, word.bottom] for word in like_name
    ]


def parse_tsv(
    tsv: str, left: float, top: float, scale: int = SCALE
) -> tuple[list[Word], float]:
    """The words of Tesseract's TSV output, placed back on the whole
    picture from a part of it at (left, top) enlarged `scale` times, and
    how sure Tesseract was of them on average"""
    rows = tsv.splitlines()
    if not rows:
        return [], 0.0
    header = rows[0].split("\t")
    words: list[Word] = []
    confidences: list[float] = []
    for row in rows[1:]:
        cells = dict(zip(header, row.split("\t")))
        text = cells.get("text", "").strip()
        if cells.get("level") != "5" or not normalize(text):
            continue
        x, y = float(cells["left"]), float(cells["top"])
        width, height = float(cells["width"]), float(cells["height"])
        words.append(
            Word(
                text=text,
                left=left + x / scale,
                top=top + y / scale,
                right=left + (x + width) / scale,
                bottom=top + (y + height) / scale,
                line=(cells["block_num"], cells["par_num"], cells["line_num"]),
            )
        )
        confidences.append(float(cells["conf"]))
    return words, statistics.fmean(confidences) if confidences else 0.0


def read_words(
    picture: bytes, area: Area, reading: str = "color"
) -> tuple[list[Word], float, tuple[int, int]]:
    """Reads an area of a card's picture: the words, how sure Tesseract
    was of them, and the picture's size. Enlarged and in color, or in
    grayscale at its own size, smoothed for "smooth" (see READINGS)."""
    image = Image.open(io.BytesIO(picture)).convert("RGB")
    width, height = image.size
    left, top = round(width * area[0]), round(height * area[1])
    right, bottom = round(width * area[2]), round(height * area[3])
    part = image.crop((left, top, right, bottom))
    if reading != "color":
        # Stretched to run from black to white
        part = ImageOps.autocontrast(part.convert("L"))
        if reading == "smooth":
            part = part.filter(ImageFilter.MedianFilter(SMOOTH_SIZE))
        scale = 1
    else:
        part = part.resize(((right - left) * SCALE, (bottom - top) * SCALE))
        scale = SCALE
    png = io.BytesIO()
    part.save(png, format="PNG")
    # --psm 6: the text is one block of lines
    result = subprocess.run(
        ["tesseract", "stdin", "stdout", "--psm", "6", "tsv"],
        input=png.getvalue(),
        capture_output=True,
        check=True,
        timeout=60,
    )
    words, confidence = parse_tsv(result.stdout.decode("utf-8"), left, top, scale)
    return words, confidence, (width, height)


class NotDownloaded(Exception):
    """A card's picture could not be downloaded"""


@functools.cache
def tesseract_version() -> str:
    """The first line of `tesseract --version`, such as "tesseract 5.3.4" """
    result = subprocess.run(
        ["tesseract", "--version"], capture_output=True, check=True, timeout=60
    )
    return result.stdout.decode("utf-8").splitlines()[0]


class Picture:
    """A card's picture, for reading with Tesseract (read_words). Given
    `saved_in`, each reading's words are saved there, by the picture's
    link: a reading made before is taken from there, and the picture is
    downloaded only when a reading isn't. So a change to the rules that
    run on the words (find_name and the like) is tried on every card in
    a minute, without downloading or reading anything.

    The words are read again, rather than taken from the file, when the
    way a part of the picture is prepared for Tesseract has changed: when
    PREPARED, SCALE, SMOOTH_SIZE or Tesseract's version does. A new area
    or reading is read by itself, the others are kept.
    """

    def __init__(
        self,
        url: str | None = None,
        content: bytes | None = None,
        saved_in: Path | None = None,
    ) -> None:
        self.url = url
        self._content = content
        self._path = None
        if saved_in is not None and url:
            name = hashlib.sha1(url.encode()).hexdigest()
            self._path = saved_in / f"{name}.json.gz"
        self._saved: dict[str, Any] | None = None

    def content(self) -> bytes:
        """The picture's file, downloaded the first time it is needed.
        NotDownloaded when it can't be."""
        if self._content is None:
            if self.url:
                self._content = _download(self.url)
            if self._content is None:
                raise NotDownloaded(self.url)
        return self._content

    def read(
        self, area: Area, reading: str = "color"
    ) -> tuple[list[Word], float, tuple[int, int]]:
        """read_words of this picture: from the saved file when it was
        read in the same way before"""
        if self._path is None:
            return read_words(self.content(), area, reading)
        key = f"{reading} {' '.join(map(str, area))}"
        if self._saved is None:
            self._saved = self._load()
        saved = self._saved.get(key)
        if saved is not None:
            words = [
                Word(text, left, top, right, bottom, (block, paragraph, line))
                for text, left, top, right, bottom, block, paragraph, line in saved[
                    "words"
                ]
            ]
            width, height = saved["size"]
            return words, saved["confidence"], (width, height)
        words, confidence, size = read_words(self.content(), area, reading)
        self._saved[key] = {
            "words": [
                [w.text, w.left, w.top, w.right, w.bottom, *w.line] for w in words
            ],
            "confidence": confidence,
            "size": list(size),
        }
        self._save(key)
        return words, confidence, size

    def _prepared(self) -> dict[str, Any]:
        """What the saved words depend on besides the picture, area and
        reading: when any of it changes, they are read again"""
        return {
            "prepared": PREPARED,
            "scale": SCALE,
            "smooth": SMOOTH_SIZE,
            "tesseract": tesseract_version(),
        }

    def _load(self) -> dict[str, Any]:
        """The readings saved for this picture: none when there is no file,
        it can't be read, or it was made in another way"""
        assert self._path is not None
        try:
            with gzip.open(self._path, "rt", encoding="utf-8") as f:
                file = json.load(f)
        except (OSError, ValueError):
            return {}
        if file.get("prepared") != self._prepared():
            return {}
        readings: dict[str, Any] = file.get("readings") or {}
        return readings

    def _save(self, key: str) -> None:
        """Adds the reading under `key` to the file. Written to a file of
        its own first and then put in place, so a run stopped halfway
        never leaves half a file. Two cards with the same picture read at
        the same time, such as an adventure and its spell, may each save
        without the other's reading: that one is only read again later."""
        assert self._path is not None and self._saved is not None
        readings = self._load() | {key: self._saved[key]}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with (
            tempfile.NamedTemporaryFile(
                dir=self._path.parent, suffix=".tmp", delete=False
            ) as f,
            gzip.open(f, "wt", encoding="utf-8") as zipped,
        ):
            json.dump({"prepared": self._prepared(), "readings": readings}, zipped)
        os.replace(f.name, self._path)


def name_in_text(
    card: Card, picture: "bytes | Picture", game_words: frozenset[str] = frozenset()
) -> list[list[float]]:
    """Where the name is printed on the card outside its title bar, as
    [left, top, width, height] shares of the picture: an empty list when
    it isn't. Every reading of its frame (frame_readings) is tried, even
    one Tesseract is unsure of, and the name covered wherever any of them
    finds it. LeftOut, with the reasons, when a word any reading takes for
    the name read badly - unless it is covered anyway, where another reading
    finds the name - or when every reading is unsure.
    """
    if isinstance(picture, bytes):
        picture = Picture(content=picture)
    found: list[list[float]] = []
    reasons: list[str] = []
    all_doubts: list[tuple[str, Doubt]] = []
    trusted = False
    for reading in frame_readings(card):
        unsure: list[str] = []
        doubts: list[Doubt] = []
        try:
            boxes = name_in_reading(card, picture, game_words, reading, unsure, doubts)
        except LeftOut as e:
            reason = f"{reading}: {e}"
            log.info(f"Not covering the name of '{card.name}' - {reason}")
            raise LeftOut(reason) from None
        add_boxes(found, boxes)
        all_doubts += [(reading, doubt) for doubt in doubts]
        reasons += [f"{reading}: {why}" for why in unsure]
        trusted = trusted or not unsure
    if is_summon_printing(card):
        boxes = summon_type_line(card, picture, game_words)
        add_boxes(found, boxes)
    for reading, (why, box) in all_doubts:
        if not covered(box, found):
            reason = f"{reading}: {why}"
            log.info(f"Not covering the name of '{card.name}' - {reason}")
            raise LeftOut(reason)
    if not trusted:
        log.info(f"Not covering the name of '{card.name}' - {'; '.join(reasons)}")
        raise LeftOut(*reasons)
    return found


def add_boxes(found: list[list[float]], boxes: list[list[float]]) -> None:
    """Adds boxes, as [left, top, width, height], to those `found`: one
    over the same word as another, read in another way and a little
    wider or higher, is merged with it into one box around both"""
    for box in boxes:
        for i, other in enumerate(found):
            if same_place(box, other):
                left, top = min(box[0], other[0]), min(box[1], other[1])
                right = max(box[0] + box[2], other[0] + other[2])
                bottom = max(box[1] + box[3], other[1] + other[3])
                found[i] = [
                    round(value, 4) for value in (left, top, right - left, bottom - top)
                ]
                break
        else:
            found.append(box)


def covered(box: list[float], found: list[list[float]]) -> bool:
    """A box, as [left, top, width, height], is under one of those found:
    nearly all across, most of the way down"""
    return any(
        min(box[0] + box[2], other[0] + other[2]) - max(box[0], other[0])
        >= COVERED * box[2]
        and min(box[1] + box[3], other[1] + other[3]) - max(box[1], other[1])
        > SAME_PLACE * box[3]
        for other in found
    )


def same_place(a: list[float], b: list[float]) -> bool:
    """Two boxes overlap over most of the smaller one: across and down"""
    across = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    down = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return across > SAME_PLACE * min(a[2], b[2]) and down > SAME_PLACE * min(a[3], b[3])


def frame_readings(card: Card) -> tuple[str, ...]:
    """The ways a card's picture is read: all READINGS on an old frame,
    NEW_FRAME_READINGS on any other"""
    return READINGS if card.raw.get("frame") in OLD_FRAMES else NEW_FRAME_READINGS


def summon_type_line(
    card: Card, picture: "Picture", game_words: frozenset[str]
) -> list[list[float]]:
    """Where the name is on a "Summon" type line (is_summon_printing),
    read by itself, in each of SUMMON_TYPE_LINES and READINGS: read with
    the text, it is often missed or run together - "Summon Lurker" on
    Lurker, "SummonWolves" on Timber Wolves. The words after "Summon" are
    checked as find_name checks the text, and covered wherever any reading
    finds the name. LeftOut when no reading finds where the type starts
    (TYPE_STARTS), or a word after it may be the name read badly."""
    plain = game_words | rules_words(card)
    found: list[list[float]] = []
    read = False
    for area in SUMMON_TYPE_LINES:
        for reading in READINGS:
            words, _, (width, height) = picture.read(area, reading)
            after = words_after_type_start(words)
            if after is None:
                continue
            read = True
            try:
                in_line = find_name(after, card.name, plain, words_of_text(card))
            except LeftOut as e:
                raise LeftOut(f"{reading}, type line: {e}") from None
            add_boxes(found, shares(in_line, width, height))
    if not read:
        raise LeftOut('"Summon" was not read on its type line')
    return found


def words_after_type_start(words: list[Word]) -> list[Word] | None:
    """The words after a word like one of TYPE_STARTS on its line - read
    with up to two letters wrong, and the type run together with it split
    off: "Stmmom People of the Woods", "SummonWolves". At most
    SUMMON_TYPE_WORDS of them: the rest is the set symbol or the frame
    read as words. None when no word is like one."""
    for i, word in enumerate(words):
        text = normalize(word.text)
        for start in TYPE_STARTS:
            # How much of the word is the start: the part most like it
            lengths = range(len(start) - 1, len(start) + 3)
            length = min(lengths, key=lambda n: edits(text[:n], start))
            if edits(text[:length], start) > 2:
                continue
            after = [w for w in words[i + 1 :] if w.line == word.line]
            if len(text) > length + 2:
                # Run together: the type's part of the word's box
                rest = word.text[len(word.text) * length // len(text) :]
                left = word.left + (word.right - word.left) * length / len(text)
                after.insert(
                    0, Word(rest, left, word.top, word.right, word.bottom, word.line)
                )
            return after[:SUMMON_TYPE_WORDS]
    return None


def name_in_reading(
    card: Card,
    picture: "Picture",
    game_words: frozenset[str],
    reading: str,
    unsure: list[str] | None = None,
    doubts: list[Doubt] | None = None,
) -> list[list[float]]:
    """One reading of the picture for name_in_text. A reading that may
    have missed the name - read unsure, or too few words - is LeftOut; or,
    given `unsure`, noted there, and its finds still given. So is a word
    it takes for the name read badly, given `doubts` (see find_name)."""

    def doubt(why: str) -> None:
        if unsure is None:
            raise LeftOut(why)
        unsure.append(why)

    boxes: list[list[float]] = []
    for number, area in enumerate(areas_to_read(card)):
        words, confidence, (width, height) = picture.read(area, reading)
        if confidence < MIN_CONFIDENCE:
            doubt(f"its text was read only {confidence:.0f}% sure")
        oracle_text = REMINDER.sub("", card.raw.get("oracle_text") or "")
        oracle_words = len(oracle_text.split())
        # Only for the text itself, the first area
        if number == 0 and len(words) < oracle_words * MIN_WORDS_READ:
            doubt(
                f"only {len(words)} words of its text were read, "
                f"of about {oracle_words}"
            )
        walker_type = planeswalker_type(card)
        # The type in the type line tells which planeswalker it is, even
        # when the card's own text names it apart from its name
        plain = game_words | rules_words(card)
        if walker_type:
            plain -= {walker_type}
        in_pixels: list[Doubt] | None = None if doubts is None else []
        found = find_name(words, card.name, plain, words_of_text(card), in_pixels)
        if doubts is not None and in_pixels:
            doubts += [(why, shares([box], width, height)[0]) for why, box in in_pixels]
        if walker_type and not type_covered(words, found, walker_type):
            line_words, line_confidence, _ = picture.read(planeswalker_type_line(area))
            line_found = (
                find_name(line_words, card.name, plain, words_of_text(card))
                if line_confidence >= MIN_CONFIDENCE
                else []
            )
            if not type_covered(line_words, line_found, walker_type):
                raise LeftOut(
                    "its type line was not read well enough to find its type there"
                )
            found += line_found
        boxes.extend(shares(found, width, height))
    return boxes


def shares(found: list[list[float]], width: int, height: int) -> list[list[float]]:
    """Boxes found in pixels, [left, top, right, bottom], as [left, top,
    width, height] shares of the picture, with room around them"""
    return [
        [
            round(value, 4)
            for value in (
                left / width - PAD_LEFT,
                top / height - PAD_Y,
                (right - left) / width + PAD_LEFT + PAD_RIGHT,
                (bottom - top) / height + 2 * PAD_Y,
            )
        ]
        for left, top, right, bottom in found
    ]


def planeswalker_type_line(text_area: Area) -> Area:
    """A planeswalker's type line by itself, at the top of the area read
    for its text (see areas_to_read)"""
    left, top, right, _ = text_area
    return (left, top, right, top + PLANESWALKER_TYPE_LINE_HEIGHT)


def type_covered(words: list[Word], boxes: list[list[float]], walker_type: str) -> bool:
    """The line read with "Planeswalker" on it - the type line - has the
    planeswalker's type on it too, inside a box found to cover. Short
    types, like "Ral", are too short for find_name to tell when read
    badly, so this is the check that it was read right: when it wasn't,
    the type would show."""
    lines = {word.line for word in words if normalize(word.text) == "planeswalker"}
    on_type_line = [
        word
        for word in words
        if word.line in lines and matches(normalize(word.text), walker_type)
    ]
    return bool(on_type_line) and all(
        any(
            box[0] <= word.left
            and word.right <= box[2]
            and box[1] <= word.top
            and word.bottom <= box[3]
            for box in boxes
        )
        for word in on_type_line
    )


def saved_key(card: Card) -> str:
    """Where a side's reading is kept in the results: under its printing's
    id, and a double-faced card's back under the id and "/back" - both
    sides share the id. Scryfall's link to a back's picture has "/back/"
    in it. A card's spell (see part_of) is kept under the id and
    "/spell": both parts share the picture."""
    picture_url = (card.raw.get("image_uris") or {}).get("png") or ""
    if part_index(card) == 1:
        return f"{card.id}/spell"
    return f"{card.id}/back" if "/back/" in picture_url else card.id


class NameInText:
    """Reads each printing's picture once: the results are kept in
    `results`, under saved_key(), for the next runs. A card left
    out has its boxes None, and why under "left_out". A printing is
    read again when its picture changes (its link carries a version), its
    name changes, or READER_VERSION does. Given `words_dir`, Tesseract's
    words are saved there too, so reading again after READER_VERSION
    changes reads nothing from the pictures that was read before.

    Every card left out in this run is kept in `left_out`, under
    saved_key() too, with its name and why: those saved too, and those that could not
    be read this time, to be tried again on the next run. summary() lists
    them.
    """

    def __init__(
        self,
        results: dict[str, Any],
        game_words: frozenset[str],
        words_dir: Path | None = None,
    ) -> None:
        self.results = results
        # Where each picture's words are saved, if anywhere (see Picture)
        self.words_dir = words_dir
        self.changed = False
        self.game_words = game_words
        self.left_out: dict[str, tuple[str, list[str]]] = {}
        self.not_read: dict[str, tuple[str, str]] = {}
        self._why_not_read = ""
        self._can_read = shutil.which("tesseract") is not None and bool(game_words)
        if shutil.which("tesseract") is None:
            self._why_not_read = "Tesseract is not installed"
            log.warning(
                "Tesseract is not installed: cards with their name in "
                "their text box not read before are asked only by their artwork"
            )
        elif not game_words:
            # Read without them, "a Goblin card" would be covered, and
            # saved that way
            self._why_not_read = "Scryfall's lists of subtypes could not be fetched"
            log.warning(
                "Scryfall's lists of subtypes could not be fetched: cards with "
                "their name in their text box not read before are asked only "
                "by their artwork"
            )

    def __call__(self, card: Card) -> list[list[float]] | None:
        key = saved_key(card)
        # A picture that failed to download in an earlier format may be
        # read now
        self.not_read.pop(key, None)
        boxes = self._read(card, key)
        if boxes is None and key not in self.not_read:
            reasons = self.results[key].get("left_out") or [
                "read before the reasons were saved"
            ]
            self.left_out[key] = (card.name, reasons)
        return boxes

    def _read(self, card: Card, key: str) -> list[list[float]] | None:
        picture_url = (card.raw.get("image_uris") or {}).get("png")
        if not picture_url:
            self.not_read[key] = (card.name, "it has no picture")
            return None
        saved: Any = self.results.get(key)
        if self._is_current(saved, card, picture_url):
            boxes: list[list[float]] | None = saved["boxes"]
            return boxes
        if not self._can_read:
            self.not_read[key] = (card.name, self._why_not_read)
            return None
        picture = Picture(picture_url, saved_in=self.words_dir)
        result: dict[str, Any] = {
            "name": card.name,
            "picture": picture_url,
            "reader": READER_VERSION,
        }
        try:
            boxes = name_in_text(card, picture, self.game_words)
            result["boxes"] = boxes
        except LeftOut as e:
            boxes = None
            result |= {"boxes": None, "left_out": list(e.args)}
        except NotDownloaded:
            self.not_read[key] = (card.name, "its picture could not be downloaded")
            return None
        except (OSError, subprocess.SubprocessError) as e:
            # Not saved: tried again on the next run
            log.warning(f"Could not read the picture of '{card.name}': {e}")
            self.not_read[key] = (card.name, f"its picture could not be read: {e}")
            return None
        self.results[key] = result
        self.changed = True
        return boxes

    def saved(self, card: Card) -> list[list[float]] | None:
        """The boxes an earlier reading of the card's picture found,
        without reading it now: None when it was never read, or read
        before it changed. For the cards on no format's list, read by
        hand with read_every_picture.py (see export_every_card).
        Not counted in summary(): those would be most cards."""
        picture_url = (card.raw.get("image_uris") or {}).get("png")
        saved: Any = self.results.get(saved_key(card))
        if not picture_url or not self._is_current(saved, card, picture_url):
            return None
        boxes: list[list[float]] | None = saved["boxes"]
        return boxes

    @property
    def why_not_read(self) -> str:
        """Why no picture can be read in this run; empty when they can"""
        return self._why_not_read

    def is_read(self, card: Card) -> bool:
        """Whether the card's picture, as it is now, was read by this
        READER_VERSION, its name covered or the card left out"""
        picture_url = (card.raw.get("image_uris") or {}).get("png")
        saved: Any = self.results.get(saved_key(card))
        return bool(picture_url and self._is_current(saved, card, picture_url))

    @staticmethod
    def _is_current(saved: Any, card: Card, picture_url: str) -> bool:
        """Whether a saved reading is of this name and picture, by this
        READER_VERSION"""
        return bool(
            saved
            and saved.get("name") == card.name
            and saved.get("picture") == picture_url
            and saved.get("reader") == READER_VERSION
        )

    def summary(self) -> list[str]:
        """Lines on the cards left out in this run, asked only by their
        artwork, and why: one line per card under a heading, as Markdown.
        Empty when there are none."""
        lines = []
        if self.left_out:
            lines.append(
                f"Name in the text box not covered on {card_count(len(self.left_out))}, "
                "asked only by the artwork:"
            )
            lines.extend(
                f"- {name}: {'; '.join(reasons)}"
                for name, reasons in sorted(self.left_out.values())
            )
        if self.not_read:
            lines.append(
                f"Picture not read on {card_count(len(self.not_read))}, "
                "asked only by the artwork and tried again on the next run:"
            )
            lines.extend(
                f"- {name}: {why}" for name, why in sorted(self.not_read.values())
            )
        return lines


def fetch_game_words() -> frozenset[str]:
    """Every subtype a card's text may use as a game word, normalized:
    "goblin", "urzas". Empty when Scryfall can't be reached."""
    words: set[str] = set()
    for catalog in config.SCRYFALL_SUBTYPE_CATALOGS:
        try:
            found = fetch_catalog(catalog)
        except RequestUnavailable as e:
            log.warning(f"Could not fetch Scryfall's {catalog}: {e}")
            return frozenset()
        if not found:
            log.warning(f"Scryfall has no {catalog} list")
            return frozenset()
        words.update(normalize(word) for word in found)
    return frozenset(words)


def _download(url: str) -> bytes | None:
    # Scryfall's picture server has no rate limit, but a pause keeps a
    # first run over thousands of cards gentle
    time.sleep(0.1)
    try:
        response = requests.get(url, headers=config.SCRYFALL_FILE_HEADERS, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        log.warning(f"Could not download {url}: {e}")
        return None
    return response.content


def never_read(card: Card) -> list[list[float]] | None:
    """For an export without reading pictures: every card with its name
    possibly in its text box is asked only by its artwork"""
    return None
