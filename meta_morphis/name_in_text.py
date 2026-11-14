"""Finds where a card's name is printed in its text box, by reading the
card's picture with Tesseract (https://github.com/tesseract-ocr/tesseract),
so the app can paint over it there too and ask which card it is.

Scryfall's data says whether the name is printed in the text, but not
where on the picture, and not always rightly for an old printing: its
Oracle text says "this creature" where the printing may say the name, or
something else. So the picture itself is read, once per printing, and
the result is kept in config.NAME_IN_TEXT_PATH for the next runs.

A reading leaves the card out when anything like a word of its name is
left uncovered - a word read with a letter wrong, the name split up or
run together - or when the text could not be read well. Leaving a card
out costs one kind of question; showing its name gives the answer away.
"""

import io
import logging
import re
import shutil
import statistics
import subprocess
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import requests
from PIL import Image

from meta_morphis import config
from meta_morphis.models.card import Card
from meta_morphis.scryfall.client import fetch_catalog
from meta_morphis.utils.http import RequestUnavailable

log = logging.getLogger(__name__)

# Where a card's name is printed in its text box, as [left, top, width,
# height] shares of its picture; None when that isn't known for sure
ReadText = Callable[[Card], list[list[float]] | None]

# Raise it when the reading changes, so every printing is read again
READER_VERSION = 5

# Where to read on a card's picture, as shares of its width and height:
# the text box, below the type line and above the artist's credit, the
# same on every frame. Measured on Scryfall's pictures on 2026-11-12.
TEXT_LEFT, TEXT_RIGHT = 0.07, 0.93
TEXT_TOP, TEXT_BOTTOM = 0.60, 0.94
# Before Sixth Edition, a creature's type line read "Summon" and its
# creature type, which for some was the name: "Summon Ball Lightning".
# Such a printing has its type line read too.
SUMMON_UNTIL = "1999-04-21"
TYPE_LINE_TOP = 0.55
# Tesseract reads small print better enlarged
SCALE = 2
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
# may have missed part of the text, and the name with it
MIN_WORDS_READ = 0.5


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


def find_name(
    words: list[Word], name: str, game_words: frozenset[str] = frozenset()
) -> list[list[float]] | None:
    """Boxes in pixels, [left, top, right, bottom], around each time the
    name is printed among the words: one box per line it runs over. The
    full name is looked for first, then a legend's short name.

    A word left over that is like one of the name's may be the name read
    badly. When it has a piece of the name next to it, or only starts like
    a word of the name, it may well be, and the card is left out (None):
    "Superior" before "Spider-" and "Man", a name broken at a line's end,
    or "Jackal,Pup" run together, whose box may be too short. Standing
    alone, it is left as it is when it is a game word - a subtype such as
    "Goblin" in "a Goblin card", among `game_words`, normalized - which
    says nothing of which card it is. Any other is covered: a place or a
    person, such as "Locthwain's" in a flavor text, gives the answer away.
    So is a card left out with more than MAX_LIKE_NAME to cover.
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
        for start in range(len(words) - len(wanted) + 1):
            span = range(start, start + len(wanted))
            if used.intersection(span):
                continue
            if not all(matches(read[i], part) for i, part in zip(span, wanted)):
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

    name_words = {normalize(part) for part in name.split()}
    name_words = {part for part in name_words if len(part) >= 4}
    # A name of short words only, like "Fog", can't be told from other
    # short words read with a letter wrong
    if not name_words:
        log.info(f"Not covering the name of '{name}': its words are too short to check")
        return None
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
        """The word at i may be a piece or a word of the name, read badly"""
        if not 0 <= i < len(read) or len(read[i]) < 3:
            return False
        return read[i] in whole or any(
            edits(read[i], part) <= 2 for part in name_words if len(part) >= 5
        )

    like_name: list[Word] = []
    for i, text in enumerate(read):
        if i in used:
            continue
        like = [part for part in name_words if matches(text, part)]
        if not like and not any(text.startswith(part) for part in name_words):
            continue
        if not like or near_name(next_word(i, -1)) or near_name(next_word(i, 1)):
            log.info(
                f"Not covering the name of '{name}': '{words[i].text}' is left in "
                "its text, and may be part of the name read badly"
            )
            return None
        if all(part in plain for part in like):
            continue
        like_name.append(words[i])
    if len(like_name) > MAX_LIKE_NAME:
        listed = ", ".join(f"'{word.text}'" for word in like_name)
        log.info(
            f"Not covering the name of '{name}': too many words like it are left: {listed}"
        )
        return None
    return boxes + [
        [word.left, word.top, word.right, word.bottom] for word in like_name
    ]


def parse_tsv(tsv: str, left: float, top: float) -> tuple[list[Word], float]:
    """The words of Tesseract's TSV output, placed back on the whole
    picture from a part of it at (left, top) enlarged SCALE times, and
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
                left=left + x / SCALE,
                top=top + y / SCALE,
                right=left + (x + width) / SCALE,
                bottom=top + (y + height) / SCALE,
                line=(cells["block_num"], cells["par_num"], cells["line_num"]),
            )
        )
        confidences.append(float(cells["conf"]))
    return words, statistics.fmean(confidences) if confidences else 0.0


def read_words(
    picture: bytes, from_top: float
) -> tuple[list[Word], float, tuple[int, int]]:
    """Reads the text box of a card's picture: the words, how sure
    Tesseract was of them, and the picture's size"""
    image = Image.open(io.BytesIO(picture)).convert("RGB")
    width, height = image.size
    left, top = round(width * TEXT_LEFT), round(height * from_top)
    right, bottom = round(width * TEXT_RIGHT), round(height * TEXT_BOTTOM)
    part = image.crop((left, top, right, bottom))
    part = part.resize(((right - left) * SCALE, (bottom - top) * SCALE))
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
    words, confidence = parse_tsv(result.stdout.decode("utf-8"), left, top)
    return words, confidence, (width, height)


def name_in_text(
    card: Card, picture: bytes, game_words: frozenset[str] = frozenset()
) -> list[list[float]] | None:
    """Where the name is printed on the card outside its title bar, as
    [left, top, width, height] shares of the picture: an empty list when
    it isn't. None when the reading can't be trusted to have found every
    place it is.
    """
    from_top = TYPE_LINE_TOP if is_summon_printing(card) else TEXT_TOP
    words, confidence, (width, height) = read_words(picture, from_top)
    if confidence < MIN_CONFIDENCE:
        log.info(
            f"Not covering the name of '{card.name}': its text was read "
            f"only {confidence:.0f}% sure"
        )
        return None
    oracle_words = len((card.raw.get("oracle_text") or "").split())
    if len(words) < oracle_words * MIN_WORDS_READ:
        log.info(
            f"Not covering the name of '{card.name}': only {len(words)} words "
            f"of its text were read, of about {oracle_words}"
        )
        return None
    found = find_name(words, card.name, game_words)
    if found is None:
        return None
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


class NameInText:
    """Reads each printing's picture once: the results are kept in
    `results`, under the printing's id, for the next runs. A printing is
    read again when its picture changes (its link carries a version), its
    name changes, or READER_VERSION does.
    """

    def __init__(self, results: dict[str, Any], game_words: frozenset[str]) -> None:
        self.results = results
        self.changed = False
        self.game_words = game_words
        self._can_read = shutil.which("tesseract") is not None and bool(game_words)
        if shutil.which("tesseract") is None:
            log.warning(
                "Tesseract is not installed: cards with their name in "
                "their text box not read before are asked only by their artwork"
            )
        elif not game_words:
            # Read without them, "a Goblin card" would be covered, and
            # saved that way
            log.warning(
                "Scryfall's lists of subtypes could not be fetched: cards with "
                "their name in their text box not read before are asked only "
                "by their artwork"
            )

    def __call__(self, card: Card) -> list[list[float]] | None:
        picture_url = (card.raw.get("image_uris") or {}).get("png")
        if not picture_url:
            return None
        saved = self.results.get(card.id)
        if (
            saved
            and saved.get("name") == card.name
            and saved.get("picture") == picture_url
            and saved.get("reader") == READER_VERSION
        ):
            boxes: list[list[float]] | None = saved["boxes"]
            return boxes
        if not self._can_read:
            return None
        picture = _download(picture_url)
        if picture is None:
            return None
        try:
            boxes = name_in_text(card, picture, self.game_words)
        except (OSError, subprocess.SubprocessError) as e:
            # Not saved: tried again on the next run
            log.warning(f"Could not read the picture of '{card.name}': {e}")
            return None
        self.results[card.id] = {
            "name": card.name,
            "picture": picture_url,
            "reader": READER_VERSION,
            "boxes": boxes,
        }
        self.changed = True
        return boxes


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
        response = requests.get(url, headers=config.SCRYFALL_IMAGE_HEADERS, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        log.warning(f"Could not download {url}: {e}")
        return None
    return response.content


def never_read(card: Card) -> list[list[float]] | None:
    """For an export without reading pictures: every card with its name
    possibly in its text box is asked only by its artwork"""
    return None
