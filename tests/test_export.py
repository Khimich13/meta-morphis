import errno
import json
import logging
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pytest import MonkeyPatch

from meta_morphis import config
from meta_morphis.export import (
    build_card,
    build_export,
    export_all,
    export_format,
    art_box,
    horizontal_sides,
    is_basic_land,
    write_json,
)
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
            "large": f"large/{printing}.jpg",
            "art": f"art/{printing}.webp",
        },
        "artist": "Some Artist",
        "frame": "2015",
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
        "large_images": ["large/id-Hydroblast.jpg"],
        "art_box": [0.079, 0.114, 0.840, 0.440],
        "art": "art/id-Hydroblast.webp",
        "artist": "Some Artist",
        "horizontal": [False],
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
    # No large picture: the app zooms into the normal one
    assert built["large_images"] == []

def test_build_card_double_faced_has_both_pictures() -> None:
    card = Card.from_raw({
        "id": "24c0d87b",
        "oracle_id": "c0957e5e",
        "name": "Fable of the Mirror-Breaker // Reflection of Kiki-Jiki",
        "artist": "Joseph Meehan",
        "card_faces": [
            {"name": "Fable of the Mirror-Breaker", "type_line": "Enchantment — Saga",
             "image_uris": {"grid": "front/24c0d87b.webp", "large": "large/front/24c0d87b.jpg",
                            "art": "art/front/24c0d87b.webp"}},
            {"name": "Reflection of Kiki-Jiki", "type_line": "Enchantment Creature",
             "image_uris": {"grid": "back/24c0d87b.webp", "large": "large/back/24c0d87b.jpg",
                            "art": "art/back/24c0d87b.webp"}},
        ],
    })
    built = build_card(card)
    assert built is not None
    assert built["images"] == ["front/24c0d87b.webp", "back/24c0d87b.webp"]
    assert built["large_images"] == ["large/front/24c0d87b.jpg", "large/back/24c0d87b.jpg"]
    # The artwork asked about is the front side's
    assert built["art"] == "art/front/24c0d87b.webp"
    assert built["artist"] == "Joseph Meehan"

def test_build_card_large_pictures_all_sides_or_none() -> None:
    # A back side without a large picture: none at all, never mixed sizes
    card = Card.from_raw({
        "id": "x1", "oracle_id": "x", "name": "Front // Back", "artist": "A",
        "card_faces": [
            {"name": "Front", "type_line": "Creature", "image_uris": {"grid": "front/x1.webp", "large": "large/front/x1.jpg",
                                             "art": "art/front/x1.webp"}},
            {"name": "Back", "type_line": "Creature", "image_uris": {"grid": "back/x1.webp"}},
        ],
    })
    built = build_card(card)
    assert built is not None
    assert built["large_images"] == []

@pytest.mark.parametrize("frame, box", [
    ("1993", [0.113, 0.094, 0.781, 0.449]),
    ("1997", [0.119, 0.100, 0.764, 0.443]),
    ("2003", [0.088, 0.119, 0.826, 0.435]),
    ("2015", [0.079, 0.114, 0.840, 0.440]),
])
def test_art_box_follows_the_frame(frame: str, box: list[float]) -> None:
    assert art_box(Card.from_raw(_raw("Card", frame=frame, type_line="Instant"))) == box

def test_art_box_of_sagas_classes_and_planeswalkers() -> None:
    saga = Card.from_raw(_raw("Urza's Saga", layout="saga",
                              type_line="Enchantment Land — Urza's Saga"))
    talent = Card.from_raw(_raw("Stormchaser's Talent", layout="class",
                                type_line="Enchantment — Class"))
    short = Card.from_raw(_raw("Teferi", type_line="Legendary Planeswalker — Teferi",
                               oracle_text="Static.\n+1: One.\n−3: Two."))
    long = Card.from_raw(_raw("Jace", type_line="Legendary Planeswalker — Jace",
                              oracle_text="Static.\n+1: One.\n−1: Two.\n−8: Three."))
    assert art_box(saga) == [0.502, 0.113, 0.418, 0.724]
    assert art_box(talent) == [0.076, 0.113, 0.418, 0.724]
    assert art_box(short) == [0.072, 0.101, 0.850, 0.451]
    assert art_box(long) == [0.073, 0.101, 0.849, 0.382]

def test_art_box_of_a_double_faced_saga_is_its_front_side() -> None:
    fable = Card.from_raw({
        **_raw("Fable of the Mirror-Breaker // Reflection of Kiki-Jiki", layout="transform"),
        "card_faces": [
            {"name": "Fable of the Mirror-Breaker", "type_line": "Enchantment — Saga"},
            {"name": "Reflection of Kiki-Jiki", "type_line": "Enchantment Creature — Goblin"},
        ],
    })
    assert art_box(fable) == [0.502, 0.113, 0.418, 0.724]

def test_no_art_box_without_a_single_measured_one() -> None:
    split = Card.from_raw(_raw("Wear // Tear", layout="split", type_line="Instant // Instant"))
    future = Card.from_raw(_raw("Future Card", frame="future", type_line="Creature"))
    old_walker = Card.from_raw(_raw("Old Walker", frame="1997",
                                    type_line="Planeswalker — Someone"))
    unknown = Card.from_raw(_raw("New Layout", layout="something_new", type_line="Creature"))
    assert art_box(split) is None
    assert art_box(future) is None
    assert art_box(old_walker) is None
    assert art_box(unknown) is None

def test_horizontal_sides() -> None:
    upright = Card.from_raw(_raw("Counterspell"))
    split = Card.from_raw(_raw("Wear // Tear", layout="split", keywords=["Fuse"]))
    aftermath = Card.from_raw(_raw("Commit // Memory", layout="split", keywords=["Aftermath"]))
    battle = Card.from_raw({
        **_raw("Invasion of Gobakhan"),
        "image_uris": None,
        "layout": "battle",
        "card_faces": [
            {"name": "Invasion of Gobakhan", "type_line": "Battle — Siege",
             "image_uris": {"grid": "front.webp", "art": "art/front.webp"}},
            {"name": "Lightshield Array", "type_line": "Artifact",
             "image_uris": {"grid": "back.webp", "art": "art/back.webp"}},
        ],
    })
    assert horizontal_sides(upright) == [False]
    assert horizontal_sides(split) == [True]
    assert horizontal_sides(aftermath) == [False]
    # Only the front of a battle is printed sideways
    assert horizontal_sides(battle) == [True, False]

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

# Two names on the list can lead to one card, e.g. after a rename
def test_build_export_keeps_one_copy_of_each_card(caplog: pytest.LogCaptureFixture) -> None:
    cards = [
        # Unusable, so it doesn't stop the usable copy after it
        Card.from_raw(_raw("Mixed", oracle_id="m", image_uris={
            "grid": "grid/id-Mixed.webp",
            "art": "art/another-printing.webp",
        })),
        Card.from_raw(_raw("New Name", oracle_id="n")),
        Card.from_raw(_raw("Old Name", oracle_id="n")),
        Card.from_raw(_raw("Mixed Fixed", oracle_id="m")),
    ]
    data = build_export("pauper", cards, "2026-10-17T19:18:03Z")
    assert [c["name"] for c in data["cards"]] == ["Mixed Fixed", "New Name"]
    assert "Leaving out 'Old Name' - the same card as 'New Name'" in caplog.text

def test_export_format_writes_the_file(
    conn: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    meta = [MetaEntry(name="Lórien Revealed", rank=1)]
    cards = [Card.from_raw(_raw("Lórien Revealed", oracle_id="l"))]
    monkeypatch.setattr("meta_morphis.export.get_meta_cards", lambda conn, format_name, kind: meta)
    _list_fetched(monkeypatch, FETCHED)
    monkeypatch.setattr("meta_morphis.export.fetch_cards", lambda conn, meta: cards)
    monkeypatch.setattr("meta_morphis.export.get_display_printings", lambda conn, cards: cards)
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
        "cards": [{
            "oracle_id": "l",
            "name": "Lórien Revealed",
            "images": ["grid/id-Lórien Revealed.webp"],
            "large_images": ["large/id-Lórien Revealed.jpg"],
            "art_box": [0.079, 0.114, 0.840, 0.440],
            "art": "art/id-Lórien Revealed.webp",
            "artist": "Some Artist",
            "horizontal": [False],
        }],
    }

# A failed fetch must not replace the file with an empty or half-empty one
def test_export_format_fails_with_too_few_cards(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    cards = [Card.from_raw(_raw("Hydroblast", oracle_id="h"))]
    monkeypatch.setattr("meta_morphis.export.get_meta_cards", lambda conn, format_name, kind: [])
    _list_fetched(monkeypatch, FETCHED)
    monkeypatch.setattr("meta_morphis.export.fetch_cards", lambda conn, meta: cards)
    monkeypatch.setattr("meta_morphis.export.get_display_printings", lambda conn, cards: cards)
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
    chosen = Card.from_raw({**_raw("Lightning Bolt", oracle_id="bolt"),
                            "id": "m10",
                            "artist": "Christopher Moeller",
                            "image_uris": {"grid": "grid/m10.webp", "art": "art/m10.webp"}})
    monkeypatch.setattr("meta_morphis.export.get_meta_cards", lambda conn, format_name, kind: [])
    _list_fetched(monkeypatch, FETCHED)
    monkeypatch.setattr("meta_morphis.export.fetch_cards", lambda conn, meta: [default])
    monkeypatch.setattr("meta_morphis.export.get_display_printings", lambda conn, cards: [chosen])
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
    monkeypatch.setattr("meta_morphis.export.get_meta_cards", lambda conn, format_name, kind: [])
    monkeypatch.setattr("meta_morphis.export.fetch_cards", lambda conn, meta: cards)
    monkeypatch.setattr("meta_morphis.export.get_display_printings", lambda conn, cards: cards)
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
    monkeypatch.setattr("meta_morphis.export.get_meta_cards", lambda conn, format_name, kind: [])
    _list_fetched(monkeypatch, None)

    with pytest.raises(RuntimeError, match="never fetched"):
        export_format(conn, "pauper", "all", tmp_path)

def _fake_export(
    fails: tuple[str, ...] = (),
) -> Callable[[sqlite3.Connection, str, str, Path], Path]:
    """export_format that writes an empty file, or fails for the named lists"""
    def fake_export(
        conn: sqlite3.Connection, format_name: str, kind: str, out_dir: Path
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

    failed = export_all(conn, ["pauper", "modern", "standard"], ["all", "lands"], tmp_path)

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

def test_export_all_reports_no_failures(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr("meta_morphis.export.export_format", _fake_export())

    assert export_all(conn, ["pauper"], ["all", "creatures"], tmp_path) == []
    assert (tmp_path / "pauper-creatures.json").exists()
    formats = json.loads((tmp_path / "formats.json").read_text(encoding="utf-8"))
    assert formats == {"formats": ["pauper"], "lists": {"pauper": ["all", "creatures"]}}

@pytest.mark.parametrize("type_line, basic", [
    ("Basic Land — Mountain", True),
    ("Basic Snow Land — Island", True),
    ("Basic Land", True),  # Wastes
    ("Land", False),
    ("Snow Land", False),
    ("Legendary Land", False),
    ("Artifact Land", False),
])
def test_is_basic_land(type_line: str, basic: bool) -> None:
    assert is_basic_land(Card.from_raw(_raw("Some Land", type_line=type_line))) is basic

def test_export_format_leaves_out_basic_lands_and_needs_fewer_lands(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    cards = [
        Card.from_raw(_raw("Mountain", oracle_id="m", type_line="Basic Land — Mountain")),
        Card.from_raw(_raw("Bojuka Bog", oracle_id="b", type_line="Land")),
    ]
    monkeypatch.setattr("meta_morphis.export.get_meta_cards", lambda conn, format_name, kind: [])
    _list_fetched(monkeypatch, FETCHED)
    monkeypatch.setattr("meta_morphis.export.fetch_cards", lambda conn, meta: cards)
    monkeypatch.setattr("meta_morphis.export.get_display_printings", lambda conn, cards: cards)
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
