import io
import shutil
from typing import Any

import pytest
from PIL import Image, ImageDraw, ImageFont
from pytest import MonkeyPatch

from meta_morphis import name_in_text
from meta_morphis.models.card import Card
from meta_morphis.name_in_text import (
    READER_VERSION,
    NameInText,
    Word,
    edits,
    fetch_game_words,
    find_name,
    matches,
    normalize,
    parse_tsv,
)


GAME_WORDS = frozenset({"goblin", "frog", "desert", "giant", "phyrexian"})


def _words(*lines: str) -> list[Word]:
    """Words as Tesseract would read them: each line 20 pixels below the
    one before, each word 10 pixels wide per letter, a space between"""
    words = []
    for number, line in enumerate(lines):
        left = 0.0
        for text in line.split():
            width = 10.0 * len(text)
            words.append(Word(text, left, 20.0 * number, left + width, 20.0 * number + 15,
                              ("1", "1", str(number))))
            left += width + 10
    return words


def test_normalize() -> None:
    assert normalize("Lórien's,") == "loriens"
    assert normalize("“Firebending") == "firebending"
    assert normalize("—") == ""


@pytest.mark.parametrize("read, wanted, same", [
    ("masticore", "masticore", True),
    # A possessive
    ("outs", "out", True),
    # One letter wrong, missing or extra, in a word of 4 letters or more
    ("rnasticore", "masticore", False),
    ("mastlcore", "masticore", True),
    ("masticor", "masticore", True),
    ("masticores", "masticore", True),
    # A short word must be read exactly
    ("ont", "out", False),
    ("jackalpup", "jackal", False),
])
def test_matches(read: str, wanted: str, same: bool) -> None:
    assert matches(read, wanted) is same


def test_find_name_on_one_line_and_across_two() -> None:
    words = _words("If Phyrexian Devourer's power is 7",
                   "a counter on Phyrexian",
                   "Devourer, where X is")
    assert find_name(words, "Phyrexian Devourer") == [
        [30.0, 0.0, 230.0, 15.0],
        # One box on each line
        [130.0, 20.0, 220.0, 35.0],
        [0.0, 40.0, 90.0, 55.0],
    ]


def test_find_name_also_finds_a_legends_short_name() -> None:
    words = _words("Discard Otawara, Soaring City: Return",
                   "Otawara is legendary")
    boxes = find_name(words, "Otawara, Soaring City")
    # The full name first, then the short name alone
    assert boxes == [[80.0, 0.0, 300.0, 15.0], [0.0, 20.0, 70.0, 35.0]]


def test_find_name_finds_nothing_when_the_name_is_not_printed() -> None:
    assert find_name(_words("When this creature enters, draw a card."), "Glint Hawk") == []


def test_edits() -> None:
    assert edits("matron", "matron") == 0
    assert edits("mafr0n", "matron") == 2
    assert edits("frog", "from") == 1
    assert edits("", "pup") == 3


@pytest.mark.parametrize("line, name", [
    # A creature type in the rules, or its plural in a flavor text
    ("Search for a Goblin card. Goblin Matron enters", "Goblin Matron"),
    ("Some goblins are expendable", "Squee, Goblin Nabob"),
    # A word a letter off a creature type: "from" for "frog"
    ("Exile three cards from your graveyard", "Psychic Frog"),
    # A name in the plural: Storm Giants, with the Giant type
    ("becomes a 7/7 blue Giant creature", "Hall of Storm Giants"),
])
def test_find_name_leaves_a_game_word_of_the_name_in_sight(line: str, name: str) -> None:
    boxes = find_name(_words(line), name, GAME_WORDS)
    expected = [[260.0, 0.0, 390.0, 15.0]] if name == "Goblin Matron" else []
    assert boxes == expected


def test_find_name_covers_any_other_word_of_the_name_standing_alone() -> None:
    # A place, which gives the answer away
    words = _words("Without Locthwain's persistence")
    assert find_name(words, "Castle Locthwain", GAME_WORDS) == [[80.0, 0.0, 190.0, 15.0]]
    # The name itself is a game word: nothing else to tell it by
    assert find_name(_words("Sacrifice two Deserts"), "Desert", GAME_WORDS) == [
        [140.0, 0.0, 210.0, 15.0],
    ]


@pytest.mark.parametrize("lines, name", [
    # Run together: its box may not cover both words
    (["Whenever Jackal,Pup is dealt damage"], "Jackal Pup"),
    # Broken at a line's end, so "Spider-Man" isn't read as one word
    (["You may have Superior Spider-", "Man enter as a copy"], "Superior Spider-Man"),
    # A piece of the name next to a word of it
    (["Put Chalice.of the Void onto"], "Chalice of the Void"),
    # A game word next to the rest of the name read badly
    (["When Goblin Mafr0n enters"], "Goblin Matron"),
    # ... or past a speck of the border read as a word
    (["a counter on Phyrexian", "a Devourer, where X is"], "Phyrexian Devourer"),
])
def test_find_name_gives_up_when_the_name_may_be_read_badly(lines: list[str], name: str) -> None:
    assert find_name(_words(*lines), name, GAME_WORDS) is None


def test_find_name_gives_up_when_too_many_words_are_like_the_name() -> None:
    words = _words("Goblin Goblin Goblin Goblin and Goblin Matron")
    assert find_name(words, "Goblin Matron") is None


def test_find_name_gives_up_on_a_name_of_short_words_only() -> None:
    assert find_name(_words("Prevent all combat damage."), "Fog") is None


def test_parse_tsv_places_words_back_on_the_whole_picture() -> None:
    tsv = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        "4\t1\t1\t1\t1\t0\t0\t0\t100\t20\t-1\t\n"
        "5\t1\t1\t1\t1\t1\t10\t20\t40\t30\t90\tMasticore\n"
        "5\t1\t1\t1\t1\t2\t60\t20\t40\t30\t70\tdeals\n"
        # Bits of the border, read as punctuation: left out
        "5\t1\t1\t1\t1\t3\t90\t20\t5\t30\t10\t|\n"
    )
    words, confidence = parse_tsv(tsv, left=100, top=600)
    # Enlarged twice, from (100, 600)
    assert words[0] == Word("Masticore", 105.0, 610.0, 125.0, 625.0, ("1", "1", "1"))
    assert [word.text for word in words] == ["Masticore", "deals"]
    assert confidence == 80


def _card(**extra: Any) -> Card:
    return Card.from_raw({
        "id": "printing", "oracle_id": "oid", "name": "Masticore", "lang": "en",
        "type_line": "Artifact Creature — Masticore", "released_at": "2020-01-01",
        "oracle_text": "Masticore deals 1 damage to target creature.",
        "image_uris": {"png": "png/printing.png?1"},
        **extra,
    })


def test_a_printing_is_read_once(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("meta_morphis.name_in_text.shutil.which", lambda name: "/usr/bin/tesseract")
    downloads: list[str] = []

    def download(url: str) -> bytes:
        downloads.append(url)
        return b"png"
    monkeypatch.setattr(name_in_text, "_download", download)
    monkeypatch.setattr(name_in_text, "name_in_text", lambda card, picture, game_words: [[0.1, 0.7, 0.2, 0.03]])

    read = NameInText({}, GAME_WORDS)
    assert read(_card()) == [[0.1, 0.7, 0.2, 0.03]]
    assert read(_card()) == [[0.1, 0.7, 0.2, 0.03]]
    assert downloads == ["png/printing.png?1"]
    assert read.changed
    assert read.results == {"printing": {
        "name": "Masticore", "picture": "png/printing.png?1",
        "reader": READER_VERSION, "boxes": [[0.1, 0.7, 0.2, 0.03]],
    }}


@pytest.mark.parametrize("change", [
    {"picture": "png/printing.png?0"},
    {"name": "Masticore of Old"},
    {"reader": READER_VERSION - 1},
])
def test_a_printing_is_read_again_when_something_changed(
    monkeypatch: MonkeyPatch, change: dict[str, Any]
) -> None:
    monkeypatch.setattr("meta_morphis.name_in_text.shutil.which", lambda name: "/usr/bin/tesseract")
    monkeypatch.setattr(name_in_text, "_download", lambda url: b"png")
    monkeypatch.setattr(name_in_text, "name_in_text", lambda card, picture, game_words: [])
    saved = {"name": "Masticore", "picture": "png/printing.png?1",
             "reader": READER_VERSION, "boxes": None}
    # The saved result as it is
    assert NameInText({"printing": saved}, GAME_WORDS)(_card()) is None
    # Read again
    assert NameInText({"printing": saved | change}, GAME_WORDS)(_card()) == []


def test_nothing_is_saved_when_the_picture_could_not_be_read(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("meta_morphis.name_in_text.shutil.which", lambda name: None)
    read = NameInText({}, GAME_WORDS)
    assert read(_card()) is None
    assert not read.changed
    monkeypatch.setattr("meta_morphis.name_in_text.shutil.which", lambda name: "/usr/bin/tesseract")
    monkeypatch.setattr(name_in_text, "_download", lambda url: None)
    read = NameInText({}, GAME_WORDS)
    assert read(_card()) is None
    assert not read.changed


def test_nothing_is_read_without_the_game_words(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("meta_morphis.name_in_text.shutil.which", lambda name: "/usr/bin/tesseract")
    downloads: list[str] = []
    monkeypatch.setattr(name_in_text, "_download", lambda url: downloads.append(url))
    read = NameInText({}, frozenset())
    assert read(_card()) is None
    assert downloads == []


def test_fetch_game_words(monkeypatch: MonkeyPatch) -> None:
    lists = {"creature-types": ["Goblin", "Frog"], "land-types": ["Urza's", "Desert"]}
    monkeypatch.setattr(name_in_text, "fetch_catalog", lambda name: lists.get(name, ["Aura"]))
    assert fetch_game_words() == {"goblin", "frog", "urzas", "desert", "aura"}
    # One list missing: none at all, so nothing is read without them
    monkeypatch.setattr(name_in_text, "fetch_catalog", lambda name: lists.get(name))
    assert fetch_game_words() == frozenset()


def _picture(*lines: str) -> bytes:
    """A plain card-sized picture with the lines in its text box"""
    image = Image.new("RGB", (745, 1040), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=30)
    for number, line in enumerate(lines):
        draw.text((80, 650 + 40 * number), line, fill="black", font=font)
    png = io.BytesIO()
    image.save(png, format="PNG")
    return png.getvalue()


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract is not installed")
def test_name_in_text_reads_a_picture() -> None:
    picture = _picture("Masticore deals 1 damage to",
                       "target creature. Regenerate",
                       "Masticore.")
    boxes = name_in_text.name_in_text(_card(), picture)
    assert boxes is not None and len(boxes) == 2
    # Shares of the picture, around the first word of the first line
    left, top, width, height = boxes[0]
    assert 0.09 < left < 0.11 and 0.61 < top < 0.64
    assert 0.15 < width < 0.3 and 0.02 < height < 0.05
