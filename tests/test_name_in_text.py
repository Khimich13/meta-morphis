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
    LeftOut,
    NameInText,
    Word,
    edits,
    fetch_game_words,
    find_name,
    matches,
    normalize,
    parse_tsv,
    rules_words,
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
            words.append(
                Word(
                    text,
                    left,
                    20.0 * number,
                    left + width,
                    20.0 * number + 15,
                    ("1", "1", str(number)),
                )
            )
            left += width + 10
    return words


def test_normalize() -> None:
    assert normalize("Lórien's,") == "loriens"
    assert normalize("“Firebending") == "firebending"
    assert normalize("—") == ""


@pytest.mark.parametrize(
    "read, wanted, same",
    [
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
    ],
)
def test_matches(read: str, wanted: str, same: bool) -> None:
    assert matches(read, wanted) is same


def test_find_name_on_one_line_and_across_two() -> None:
    words = _words(
        "If Phyrexian Devourer's power is 7",
        "a counter on Phyrexian",
        "Devourer, where X is",
    )
    assert find_name(words, "Phyrexian Devourer") == [
        [30.0, 0.0, 230.0, 15.0],
        # One box on each line
        [130.0, 20.0, 220.0, 35.0],
        [0.0, 40.0, 90.0, 55.0],
    ]


def test_find_name_also_finds_a_legends_short_name() -> None:
    words = _words("Discard Otawara, Soaring City: Return", "Otawara is legendary")
    boxes = find_name(words, "Otawara, Soaring City")
    # The full name first, then the short name alone
    assert boxes == [[80.0, 0.0, 300.0, 15.0], [0.0, 20.0, 70.0, 35.0]]


def test_find_name_finds_nothing_when_the_name_is_not_printed() -> None:
    assert (
        find_name(_words("When this creature enters, draw a card."), "Glint Hawk") == []
    )


def test_edits() -> None:
    assert edits("matron", "matron") == 0
    assert edits("mafr0n", "matron") == 2
    assert edits("frog", "from") == 1
    assert edits("", "pup") == 3


@pytest.mark.parametrize(
    "line, name",
    [
        # A creature type in the rules, or its plural in a flavor text
        ("Search for a Goblin card. Goblin Matron enters", "Goblin Matron"),
        ("Some goblins are expendable", "Squee, Goblin Nabob"),
        # A word a letter off a creature type: "from" for "frog"
        ("Exile three cards from your graveyard", "Psychic Frog"),
        # A name in the plural: Storm Giants, with the Giant type
        ("becomes a 7/7 blue Giant creature", "Hall of Storm Giants"),
    ],
)
def test_find_name_leaves_a_game_word_of_the_name_in_sight(
    line: str, name: str
) -> None:
    boxes = find_name(_words(line), name, GAME_WORDS)
    expected = [[260.0, 0.0, 390.0, 15.0]] if name == "Goblin Matron" else []
    assert boxes == expected


def test_find_name_covers_any_other_word_of_the_name_standing_alone() -> None:
    # A place, which gives the answer away
    words = _words("Without Locthwain's persistence")
    assert find_name(words, "Castle Locthwain", GAME_WORDS) == [
        [80.0, 0.0, 190.0, 15.0]
    ]
    # The name itself is a game word: nothing else to tell it by
    assert find_name(_words("Sacrifice two Deserts"), "Desert", GAME_WORDS) == [
        [140.0, 0.0, 210.0, 15.0],
    ]


@pytest.mark.parametrize(
    "lines, name",
    [
        # Run together at the name's end: its box may not cover both words
        (["Whenever Jackal,Pup is dealt damage"], "Jackal Pup"),
        # ... or at a line's end
        (["Put Chalice.of", "the Void onto"], "Chalice of the Void"),
        # A piece of the name next to a word of it
        (["Put Chalice.of the Vod onto"], "Chalice of the Void"),
        # The rest of the name read badly past words of it read right
        (["an act of the gods. Anger of the Gocls"], "Anger of the Gods"),
        # A game word next to the rest of the name read badly
        (["When Goblin Mafr0n enters"], "Goblin Matron"),
        # ... or past a speck of the border read as a word
        (["a counter on Phyrexian", "a Devourer, where X is"], "Phyrexian Devourer"),
    ],
)
def test_find_name_gives_up_when_the_name_may_be_read_badly(
    lines: list[str], name: str
) -> None:
    with pytest.raises(LeftOut):
        find_name(_words(*lines), name, GAME_WORDS)


def test_find_name_finds_a_name_broken_at_a_lines_end() -> None:
    words = _words("You may have Superior Spider-", "Man enter as a copy")
    assert find_name(words, "Superior Spider-Man") == [
        [130.0, 0.0, 290.0, 15.0],
        [0.0, 20.0, 30.0, 35.0],
    ]


def test_find_name_finds_a_name_run_together_before_more_of_it() -> None:
    # The box of "Void" reaches past "Chalice.of", which may end short
    words = _words("Put Chalice.of the Void onto")
    assert find_name(words, "Chalice of the Void") == [[40.0, 0.0, 230.0, 15.0]]


def test_find_name_trusts_the_name_found_next_to_a_word_of_it() -> None:
    # An ability named after a word of the name, before the name itself
    # As Tesseract gives it: the dashes are no words (see parse_tsv)
    words = _words("Fire 0 Fire Magic deals 1")
    assert find_name(words, "Fire Magic") == [
        [70.0, 0.0, 170.0, 15.0],
        [0.0, 0.0, 40.0, 15.0],
    ]


def test_find_name_passes_over_words_of_the_name_read_right() -> None:
    # "of the" before "gods": the start of the name isn't there
    words = _words("Anger of the Gods deals 3", "already an act of the gods.")
    assert find_name(words, "Anger of the Gods") == [
        [0.0, 0.0, 170.0, 15.0],
        [220.0, 20.0, 270.0, 35.0],
    ]


def test_find_name_covers_a_word_that_starts_like_a_word_of_the_name() -> None:
    # In a flavor text: a hint at the name
    words = _words("storms shape the Nephalia coastline, sculpting cliffs")
    assert find_name(words, "Stormcarved Coast", GAME_WORDS) == [
        [260.0, 0.0, 360.0, 15.0]
    ]
    # The keyword a card is named after, read together with the next word
    words = _words("gains flashback-until end of turn")
    assert find_name(words, "Flashback", GAME_WORDS) == [[60.0, 0.0, 210.0, 15.0]]


def test_find_name_takes_a_word_of_the_oracle_text_for_plain_text() -> None:
    # "can't" is like "Chant" with a letter missing, next to "cast"
    words = _words("Target player can't cast spells this turn.")
    text = frozenset({"target", "player", "cant", "cast", "spells", "this", "turn"})
    with pytest.raises(LeftOut):
        find_name(words, "Orim's Chant", GAME_WORDS)
    assert find_name(words, "Orim's Chant", GAME_WORDS, text) == []
    # A keyword that starts like a word of the name
    words = _words("Flashback—® Remove X cards. You can't remove Flash of Insight")
    text = frozenset({"flashback", "remove", "cards", "you", "cant", "this", "card"})
    assert find_name(words, "Flash of Insight", GAME_WORDS, text) == [
        [450.0, 0.0, 610.0, 15.0]
    ]


def test_find_name_still_covers_a_word_of_the_name_in_the_oracle_text() -> None:
    # The name of an ability, "Wasp's Sting", gives the answer away
    words = _words("Wasp's Sting — When The Wondrous Wasp enters")
    text = frozenset({"wasps", "sting", "when", "the", "wondrous", "wasp", "enters"})
    assert find_name(words, "The Wondrous Wasp", GAME_WORDS, text) == [
        [200.0, 0.0, 370.0, 15.0],
        [0.0, 0.0, 60.0, 15.0],
    ]
    # A piece of the name is no plain text either: "Spider" is in the
    # Oracle text, as a creature type and in the name. Here with the
    # rest of the name read badly, so it isn't found whole.
    words = _words("You may have Superior Spider-", "Mon enter as a copy")
    text = frozenset({"you", "may", "have", "superior", "spider", "man", "enter"})
    with pytest.raises(LeftOut):
        find_name(words, "Superior Spider-Man", GAME_WORDS, text)


def test_rules_words_are_words_of_the_name_its_rules_use_apart_from_it() -> None:
    trespasser = Card.from_raw(
        {
            "id": "id",
            "name": "Graveyard Trespasser",
            "type_line": "Creature — Human Werewolf",
            "oracle_text": "Whenever this creature enters or attacks, exile up to "
            "one target card from a graveyard.",
        }
    )
    assert rules_words(trespasser) == {"graveyard"}
    # Also when the rules use it in the plural: "cards from graveyards"
    # on Graveyard Glutton
    glutton = Card.from_raw(
        {
            "id": "id",
            "name": "Graveyard Glutton",
            "type_line": "Creature — Werewolf",
            "oracle_text": "Whenever this creature enters or attacks, exile up to "
            "two target cards from graveyards.",
        }
    )
    assert rules_words(glutton) == {"graveyard"}
    # The name itself, or a legend's short name, is no rules word
    ajani = Card.from_raw(
        {
            "id": "id",
            "name": "Ajani, Nacatl Pariah",
            "type_line": "Legendary Creature — Cat Warrior",
            "oracle_text": "When Ajani, Nacatl Pariah enters, create a token.\n"
            "You may exile Ajani.",
        }
    )
    assert rules_words(ajani) == frozenset()
    # Nor is a word of the name of an ability
    wasp = Card.from_raw(
        {
            "id": "id",
            "name": "The Wondrous Wasp",
            "type_line": "Legendary Creature — Insect",
            "oracle_text": "Wasp Sting — When this creature enters, tap a creature.",
        }
    )
    assert rules_words(wasp) == frozenset()


def test_find_name_leaves_a_rules_word_of_the_name_in_sight() -> None:
    words = _words("exile up to one target card from a graveyard.")
    name = "Graveyard Trespasser"
    assert find_name(words, name, GAME_WORDS) == [[350.0, 0.0, 450.0, 15.0]]
    assert find_name(words, name, GAME_WORDS | {"graveyard"}) == []


def test_find_name_gives_up_when_too_many_words_are_like_the_name() -> None:
    words = _words("Goblin Goblin Goblin Goblin and Goblin Matron")
    with pytest.raises(LeftOut):
        find_name(words, "Goblin Matron")


def test_find_name_gives_up_on_a_name_of_short_words_only() -> None:
    with pytest.raises(LeftOut):
        find_name(_words("Prevent all combat damage."), "Fog")


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
    # Not enlarged: as it is
    words, _ = parse_tsv(tsv, left=100, top=600, scale=1)
    assert words[0] == Word("Masticore", 110.0, 620.0, 150.0, 650.0, ("1", "1", "1"))


def _card(**extra: Any) -> Card:
    return Card.from_raw(
        {
            "id": "printing",
            "oracle_id": "oid",
            "name": "Masticore",
            "lang": "en",
            "type_line": "Artifact Creature — Masticore",
            "released_at": "2020-01-01",
            "oracle_text": "Masticore deals 1 damage to target creature.",
            "image_uris": {"png": "png/printing.png?1"},
            **extra,
        }
    )


def test_a_printing_is_read_once(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "meta_morphis.name_in_text.shutil.which", lambda name: "/usr/bin/tesseract"
    )
    downloads: list[str] = []

    def download(url: str) -> bytes:
        downloads.append(url)
        return b"png"

    monkeypatch.setattr(name_in_text, "_download", download)
    monkeypatch.setattr(
        name_in_text,
        "name_in_text",
        lambda card, picture, game_words: [[0.1, 0.7, 0.2, 0.03]],
    )

    read = NameInText({}, GAME_WORDS)
    assert read(_card()) == [[0.1, 0.7, 0.2, 0.03]]
    assert read(_card()) == [[0.1, 0.7, 0.2, 0.03]]
    assert downloads == ["png/printing.png?1"]
    assert read.changed
    assert read.results == {
        "printing": {
            "name": "Masticore",
            "picture": "png/printing.png?1",
            "reader": READER_VERSION,
            "boxes": [[0.1, 0.7, 0.2, 0.03]],
        }
    }


def test_a_back_side_is_kept_apart_from_its_front(monkeypatch: MonkeyPatch) -> None:
    # Both sides of a transform card share the printing's id: each kept
    # under its own key, neither is read again on the next run
    monkeypatch.setattr(
        "meta_morphis.name_in_text.shutil.which", lambda name: "/usr/bin/tesseract"
    )
    downloads: list[str] = []

    def download(url: str) -> bytes:
        downloads.append(url)
        return b"png"

    monkeypatch.setattr(name_in_text, "_download", download)
    monkeypatch.setattr(
        name_in_text, "name_in_text", lambda card, picture, game_words: []
    )
    front = _card(image_uris={"png": "png/front/printing.png?1"})
    back = _card(name="Back", image_uris={"png": "png/back/printing.png?1"})

    read = NameInText({}, GAME_WORDS)
    for _ in range(2):
        assert read(front) == []
        assert read(back) == []
    assert downloads == ["png/front/printing.png?1", "png/back/printing.png?1"]
    assert read.results["printing"]["name"] == "Masticore"
    assert read.results["printing/back"]["name"] == "Back"


def test_a_card_left_out_is_saved_with_why(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "meta_morphis.name_in_text.shutil.which", lambda name: "/usr/bin/tesseract"
    )
    monkeypatch.setattr(name_in_text, "_download", lambda url: b"png")

    def give_up(card: Card, picture: bytes, game_words: frozenset[str]) -> Any:
        raise LeftOut("color: unsure", "gray: unsure too")

    monkeypatch.setattr(name_in_text, "name_in_text", give_up)
    read = NameInText({}, GAME_WORDS)
    assert read(_card()) is None
    assert read.results["printing"]["boxes"] is None
    assert read.results["printing"]["left_out"] == ["color: unsure", "gray: unsure too"]


def test_summary_lists_the_cards_left_out_in_this_run(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "meta_morphis.name_in_text.shutil.which", lambda name: "/usr/bin/tesseract"
    )
    monkeypatch.setattr(name_in_text, "_download", lambda url: None)
    saved = {
        "name": "Masticore",
        "picture": "png/printing.png?1",
        "reader": READER_VERSION,
        "boxes": None,
        "left_out": ["color: unsure", "gray: unsure too"],
    }
    read = NameInText({"printing": saved}, GAME_WORDS)
    assert read.summary() == []
    # Read on an earlier run, and asked about in two formats: listed once
    read(_card())
    read(_card())
    # Not read: its picture could not be downloaded
    read(_card(id="other", name="Ball Lightning"))
    assert read.summary() == [
        "Name in the text box not covered on 1 card, asked only by the artwork:",
        "- Masticore: color: unsure; gray: unsure too",
        (
            "Picture not read on 1 card, asked only by the artwork and tried "
            "again on the next run:"
        ),
        "- Ball Lightning: its picture could not be downloaded",
    ]


def test_summary_leaves_out_a_picture_read_after_failing_once(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "meta_morphis.name_in_text.shutil.which", lambda name: "/usr/bin/tesseract"
    )
    pictures: list[bytes | None] = [None, b"png"]
    monkeypatch.setattr(name_in_text, "_download", lambda url: pictures.pop(0))
    monkeypatch.setattr(
        name_in_text, "name_in_text", lambda card, picture, game_words: []
    )
    read = NameInText({}, GAME_WORDS)
    assert read(_card()) is None
    assert read(_card()) == []
    assert read.summary() == []


@pytest.mark.parametrize(
    "change",
    [
        {"picture": "png/printing.png?0"},
        {"name": "Masticore of Old"},
        {"reader": READER_VERSION - 1},
    ],
)
def test_a_printing_is_read_again_when_something_changed(
    monkeypatch: MonkeyPatch, change: dict[str, Any]
) -> None:
    monkeypatch.setattr(
        "meta_morphis.name_in_text.shutil.which", lambda name: "/usr/bin/tesseract"
    )
    monkeypatch.setattr(name_in_text, "_download", lambda url: b"png")
    monkeypatch.setattr(
        name_in_text, "name_in_text", lambda card, picture, game_words: []
    )
    saved = {
        "name": "Masticore",
        "picture": "png/printing.png?1",
        "reader": READER_VERSION,
        "boxes": None,
    }
    # The saved result as it is
    assert NameInText({"printing": saved}, GAME_WORDS)(_card()) is None
    # Read again
    assert NameInText({"printing": saved | change}, GAME_WORDS)(_card()) == []


def test_nothing_is_saved_when_the_picture_could_not_be_read(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("meta_morphis.name_in_text.shutil.which", lambda name: None)
    read = NameInText({}, GAME_WORDS)
    assert read(_card()) is None
    assert not read.changed
    monkeypatch.setattr(
        "meta_morphis.name_in_text.shutil.which", lambda name: "/usr/bin/tesseract"
    )
    monkeypatch.setattr(name_in_text, "_download", lambda url: None)
    read = NameInText({}, GAME_WORDS)
    assert read(_card()) is None
    assert not read.changed


def test_nothing_is_read_without_the_game_words(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "meta_morphis.name_in_text.shutil.which", lambda name: "/usr/bin/tesseract"
    )
    downloads: list[str] = []
    monkeypatch.setattr(name_in_text, "_download", lambda url: downloads.append(url))
    read = NameInText({}, frozenset())
    assert read(_card()) is None
    assert downloads == []


def test_fetch_game_words(monkeypatch: MonkeyPatch) -> None:
    lists = {"creature-types": ["Goblin", "Frog"], "land-types": ["Urza's", "Desert"]}
    monkeypatch.setattr(
        name_in_text, "fetch_catalog", lambda name: lists.get(name, ["Aura"])
    )
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


@pytest.mark.skipif(
    shutil.which("tesseract") is None, reason="Tesseract is not installed"
)
def test_name_in_text_reads_a_picture() -> None:
    picture = _picture(
        "Masticore deals 1 damage to", "target creature. Regenerate", "Masticore."
    )
    boxes = name_in_text.name_in_text(_card(), picture)
    assert boxes is not None and len(boxes) == 2
    # Shares of the picture, around the first word of the first line
    left, top, width, height = boxes[0]
    assert 0.09 < left < 0.11 and 0.61 < top < 0.64
    assert 0.15 < width < 0.3 and 0.02 < height < 0.05


def _reading(*texts: str, confidence: float = 90) -> Any:
    """What read_words gives for a text box with these words in a line"""
    words = [
        Word(text, 100.0 * i, 700.0, 100.0 * i + 90, 730.0, ("1", "1", "1"))
        for i, text in enumerate(texts)
    ]
    return words, confidence, (745, 1040)


def test_a_picture_is_read_again_in_gray_when_the_first_reading_gives_up(
    monkeypatch: MonkeyPatch,
) -> None:
    asked: list[str] = []

    def read_words(picture: bytes, area: Any, reading: str = "color") -> Any:
        asked.append(reading)
        # In color, words seen in the box's texture leave it unsure
        sure = 90 if reading == "gray" else 40
        return _reading("Masticore", "deals", confidence=sure)

    monkeypatch.setattr(name_in_text, "read_words", read_words)
    boxes = name_in_text.name_in_text(_card(oracle_text="Masticore deals"), b"png")
    assert asked == ["color", "gray"]
    assert boxes is not None and len(boxes) == 1


def test_a_picture_is_read_smoothed_when_gray_gives_up_too(
    monkeypatch: MonkeyPatch,
) -> None:
    asked: list[str] = []

    def read_words(picture: bytes, area: Any, reading: str = "color") -> Any:
        asked.append(reading)
        # An old frame's texture, read as words in gray too
        sure = 90 if reading == "smooth" else 50
        return _reading("Masticore", "deals", confidence=sure)

    monkeypatch.setattr(name_in_text, "read_words", read_words)
    boxes = name_in_text.name_in_text(_card(oracle_text="Masticore deals"), b"png")
    assert asked == ["color", "gray", "smooth"]
    assert boxes is not None and len(boxes) == 1


def test_a_picture_is_read_once_when_the_first_reading_is_trusted(
    monkeypatch: MonkeyPatch,
) -> None:
    asked: list[str] = []

    def read_words(picture: bytes, area: Any, reading: str = "color") -> Any:
        asked.append(reading)
        return _reading("Masticore", "deals")

    monkeypatch.setattr(name_in_text, "read_words", read_words)
    boxes = name_in_text.name_in_text(_card(oracle_text="Masticore deals"), b"png")
    assert asked == ["color"]
    assert boxes is not None and len(boxes) == 1


def test_a_card_is_left_out_when_every_reading_gives_up(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        name_in_text,
        "read_words",
        lambda picture, area, reading="color": _reading("Masticore", confidence=40),
    )
    with pytest.raises(LeftOut) as left_out:
        name_in_text.name_in_text(_card(oracle_text="Masticore"), b"png")
    # Why, for each reading
    assert left_out.value.args == (
        "color: its text was read only 40% sure",
        "gray: its text was read only 40% sure",
        "smooth: its text was read only 40% sure",
    )


@pytest.mark.skipif(
    shutil.which("tesseract") is None, reason="Tesseract is not installed"
)
@pytest.mark.parametrize("reading", ["gray", "smooth"])
def test_read_words_in_gray_places_words_as_the_first_reading_does(
    reading: str,
) -> None:
    picture = _picture("Masticore deals 1 damage to", "target creature.")
    area = name_in_text.areas_to_read(_card())[0]
    color, _, size = name_in_text.read_words(picture, area)
    other, _, other_size = name_in_text.read_words(picture, area, reading)
    assert size == other_size == (745, 1040)
    assert color[0].text == other[0].text == "Masticore"
    for side in ("left", "top", "right", "bottom"):
        assert abs(getattr(color[0], side) - getattr(other[0], side)) < 4


def test_reminder_text_is_not_counted_among_the_words_to_read(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        name_in_text,
        "read_words",
        lambda picture, area, reading="color": _reading("Masticore", "deals"),
    )
    # A printing without the reminder text has far fewer words
    reminder = "(If you discard this card, discard it into exile and so on.)"
    card = _card(oracle_text=f"Masticore deals. Madness {reminder}")
    assert name_in_text.name_in_text(card, b"png") is not None
    # As many words outside the brackets: too few were read
    card = _card(oracle_text=f"Masticore deals. Madness {reminder[1:-1]}")
    with pytest.raises(LeftOut):
        name_in_text.name_in_text(card, b"png")


def test_areas_to_read_follow_the_layout() -> None:
    assert name_in_text.areas_to_read(_card()) == [(0.07, 0.60, 0.93, 0.94)]
    # A "Summon" type line is read with the text
    old = _card(type_line="Creature — Masticore", released_at="1998-01-01")
    assert name_in_text.areas_to_read(old) == [(0.07, 0.55, 0.93, 0.94)]
    # Text left of the artwork, or right of it
    saga = _card(
        name="The Misty Mountains Cold", layout="saga", type_line="Enchantment — Saga"
    )
    talent = _card(
        name="Stormchaser's Talent", layout="class", type_line="Enchantment — Class"
    )
    assert name_in_text.areas_to_read(saga) == [(0.07, 0.11, 0.50, 0.84)]
    assert name_in_text.areas_to_read(talent) == [(0.50, 0.11, 0.93, 0.84)]
    # The type line too, when it has a word of the name
    urzas = _card(
        name="Urza's Saga", layout="saga", type_line="Enchantment Land — Urza's Saga"
    )
    assert name_in_text.areas_to_read(urzas) == [
        (0.07, 0.11, 0.50, 0.84),
        (0.07, 0.84, 0.93, 0.905),
    ]


def test_every_area_is_read_and_must_be_trusted(monkeypatch: MonkeyPatch) -> None:
    urzas = _card(
        name="Urza's Saga",
        layout="saga",
        type_line="Enchantment Land — Urza's Saga",
        oracle_text="Urza's Saga gains",
    )
    sure = {"text": 90.0, "type line": 90.0}

    def read_words(picture: bytes, area: Any, reading: str = "color") -> Any:
        if area == name_in_text.LOW_TYPE_LINE:
            return _reading("Land", "Urza's", "Saga", confidence=sure["type line"])
        return _reading("Urza's", "Saga", "gains", confidence=sure["text"])

    monkeypatch.setattr(name_in_text, "read_words", read_words)
    boxes = name_in_text.name_in_text(urzas, b"png", GAME_WORDS)
    # One in the text, one in the type line
    assert boxes is not None and len(boxes) == 2
    # The type line read poorly, in color and in gray: left out
    sure["type line"] = 40.0
    with pytest.raises(LeftOut):
        name_in_text.name_in_text(urzas, b"png", GAME_WORDS)


def _walker(**extra: Any) -> Card:
    return _card(
        **{
            "name": "Ral, Crackling Wit",
            "type_line": "Legendary Planeswalker — Ral",
            "oracle_text": "Put a counter on Ral.",
            **extra,
        }
    )


def test_a_planeswalkers_type_line_is_read_with_its_text() -> None:
    # Right below the artwork, which is shorter with four lines or more
    assert name_in_text.areas_to_read(_walker()) == [(0.07, 0.552, 0.93, 0.94)]
    long_text = _walker(oracle_text="+1: One.\n−1: Two.\n−3: Three.\n−8: Four.")
    assert name_in_text.areas_to_read(long_text) == [(0.07, 0.483, 0.93, 0.94)]


def test_planeswalker_type_is_its_type_when_a_word_of_its_name() -> None:
    assert name_in_text.planeswalker_type(_walker()) == "ral"
    nixilis = _walker(
        name="Ob Nixilis, the Adversary", type_line="Legendary Planeswalker — Nixilis"
    )
    assert name_in_text.planeswalker_type(nixilis) == "nixilis"
    onyx = _walker(name="Professor Onyx", type_line="Legendary Planeswalker — Liliana")
    assert name_in_text.planeswalker_type(onyx) is None
    assert name_in_text.planeswalker_type(_card()) is None


def _two_lines(type_line: list[str], text: list[str]) -> Any:
    """What read_words gives for a planeswalker: its type line, then its
    text. The dash isn't a word: parse_tsv leaves it out."""
    words = [
        Word(
            word,
            100.0 * i,
            100.0 * row,
            100.0 * i + 90,
            100.0 * row + 30,
            ("1", "1", str(row)),
        )
        for row, line in enumerate((type_line, text))
        for i, word in enumerate(line)
    ]
    return words, 90.0, (745, 1040)


def test_a_planeswalkers_type_must_be_read_and_covered(
    monkeypatch: MonkeyPatch,
) -> None:
    shown = {"type": "Ral", "text": "Ral."}

    def read_words(picture: bytes, area: Any, reading: str = "color") -> Any:
        return _two_lines(
            ["Legendary", "Planeswalker", shown["type"]],
            ["Put", "a", "counter", "on", shown["text"]],
        )

    monkeypatch.setattr(name_in_text, "read_words", read_words)
    boxes = name_in_text.name_in_text(_walker(), b"png", GAME_WORDS)
    # In the type line and in the text
    assert boxes is not None and len(boxes) == 2
    # Too short for find_name to know "RaI" for the name read badly:
    # left out, even with the name read right in the text
    shown["type"] = "RaI"
    with pytest.raises(LeftOut):
        name_in_text.name_in_text(_walker(), b"png", GAME_WORDS)


def test_a_planeswalkers_type_line_is_read_alone_when_missed(
    monkeypatch: MonkeyPatch,
) -> None:
    # A transform back's white type line, missed when read with the text
    type_line = ["Legendary", "Planeswalker", "Ral"]
    areas: list[Any] = []

    def read_words(picture: bytes, area: Any, reading: str = "color") -> Any:
        areas.append(area)
        if area == (0.07, 0.552, 0.93, 0.627):
            return _two_lines(type_line, [])
        return _two_lines(["on", "ES"], ["Put", "a", "counter", "on", "Ral."])

    monkeypatch.setattr(name_in_text, "read_words", read_words)
    boxes = name_in_text.name_in_text(_walker(), b"png", GAME_WORDS)
    # In the text, then in the type line read alone
    assert boxes is not None and len(boxes) == 2
    assert areas[-1] == (0.07, 0.552, 0.93, 0.627)
    # Missed there too: left out
    type_line[2] = "RaI"
    with pytest.raises(LeftOut):
        name_in_text.name_in_text(_walker(), b"png", GAME_WORDS)


def test_a_planeswalkers_type_is_covered_when_its_text_uses_it_too(
    monkeypatch: MonkeyPatch,
) -> None:
    # "Jace" in its text apart from its name is a rules word, which would
    # be left in sight - but in the type line it tells which card it is
    jace = _walker(
        name="The Theorist, Jace Beleren",
        type_line="Legendary Planeswalker — Jace",
        oracle_text="Then Jace draws",
    )
    assert "jace" in rules_words(jace)
    monkeypatch.setattr(
        name_in_text,
        "read_words",
        lambda picture, area, reading="color": _two_lines(
            ["Legendary", "Planeswalker", "Jace"], ["Then", "Jace", "draws"]
        ),
    )
    boxes = name_in_text.name_in_text(jace, b"png", GAME_WORDS)
    assert boxes is not None and len(boxes) == 2


def _with_spell(layout: str) -> Card:
    """An adventure or prepare card as a whole, as Scryfall gives it"""
    return _card(
        name="Jadzi, Steward of Fate // Oracle's Gift",
        layout=layout,
        oracle_text=None,
        card_faces=[
            {
                "name": "Jadzi, Steward of Fate",
                "mana_cost": "{2}{U}",
                "type_line": "Legendary Creature — Human Wizard",
                "oracle_text": "Jadzi enters prepared.",
            },
            {
                "name": "Oracle's Gift",
                "mana_cost": "{X}{X}{U}",
                "type_line": "Sorcery",
                "oracle_text": "Create X 0/0 Fractal creature tokens.",
            },
        ],
    )


def test_each_part_of_a_card_with_a_spell_is_a_card_by_itself() -> None:
    whole = _with_spell("prepare")
    main, spell = name_in_text.part_of(whole, 0), name_in_text.part_of(whole, 1)
    assert (main.name, main.mana_cost) == ("Jadzi, Steward of Fate", "{2}{U}")
    assert (spell.name, spell.mana_cost) == ("Oracle's Gift", "{X}{X}{U}")
    assert spell.raw["oracle_text"] == "Create X 0/0 Fractal creature tokens."
    assert [name_in_text.part_index(card) for card in (main, spell)] == [0, 1]
    # Not a part: the card as a whole, or any other card
    assert name_in_text.part_index(whole) is None
    assert name_in_text.part_index(_card()) is None
    # Both share the picture: the spell is kept apart
    assert name_in_text.saved_key(main) == "printing"
    assert name_in_text.saved_key(spell) == "printing/spell"


def test_a_part_is_read_in_its_own_half_of_the_text_box_first() -> None:
    prepare = _with_spell("prepare")
    assert name_in_text.areas_to_read(name_in_text.part_of(prepare, 0)) == [
        (0.07, 0.60, 0.50, 0.94),
        (0.50, 0.72, 0.93, 0.94),
    ]
    assert name_in_text.areas_to_read(name_in_text.part_of(prepare, 1)) == [
        (0.50, 0.72, 0.93, 0.94),
        (0.07, 0.60, 0.50, 0.94),
    ]
    # An adventure's spell is on the left
    adventure = name_in_text.part_of(_with_spell("adventure"), 1)
    assert name_in_text.areas_to_read(adventure)[0] == (0.07, 0.72, 0.50, 0.94)


def test_both_parts_text_is_printed_text() -> None:
    spell = name_in_text.part_of(_with_spell("prepare"), 1)
    # The other part's words are printed too: never the name read badly
    assert {"create", "fractal", "enters", "prepared"} <= name_in_text.words_of_text(
        spell
    )
