import gzip
import json
import logging
import os
from collections.abc import Iterator
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import pytest
import requests
from pytest import MonkeyPatch

from meta_morphis.scryfall import bulk
from meta_morphis.scryfall.bulk import bulk_file_age, read_cards, update_bulk_file
from meta_morphis.utils.http import RequestUnavailable

# 2026-11-17T22:06:47Z, as Unix time
MADE = 1794953207
INFO = {
    "updated_at": "2026-11-17T22:06:47+00:00",
    "jsonl_download_uri": "https://data.scryfall.io/default-cards/x.jsonl.gz",
}


def _printing(name: str, oracle_id: str, **extra: Any) -> dict[str, Any]:
    printing = f"{oracle_id}-{extra.get('set', 'm10')}"
    return {
        "id": printing,
        "oracle_id": oracle_id,
        "name": name,
        "set": "m10",
        "collector_number": "1",
        "released_at": "2009-07-17",
        "illustration_id": "art-" + oracle_id,
        "games": ["paper"],
        "lang": "en",
        "layout": "normal",
        "image_uris": {"grid": f"grid/{printing}.webp", "art": f"art/{printing}.webp"},
        **extra,
    }


def _faces(*names: str) -> list[dict[str, Any]]:
    return [{"name": name, "type_line": "Instant"} for name in names]


def _bulk_file(path: Path, lines: list[Any]) -> Path:
    with gzip.open(path, "wt", encoding="utf-8") as file:
        for line in lines:
            file.write((line if isinstance(line, str) else json.dumps(line)) + "\n")
    return path


def _read(tmp_path: Path, printings: list[Any], names: list[str]) -> dict[str, str]:
    """The id of the printing each name got"""
    path = _bulk_file(tmp_path / "cards.jsonl.gz", printings)
    return {key: card.id for key, card in read_cards(path, names).items()}


def test_a_name_gets_its_cards_chosen_printing(tmp_path: Path) -> None:
    printings = [
        _printing("Lightning Bolt", "bolt", set="m10", released_at="2009-07-17"),
        _printing("Lightning Bolt", "bolt", set="2xm", released_at="2020-08-07"),
        _printing("Counterspell", "counter"),
    ]
    # Keyed by normalize_name, the way the exporter looks names up
    assert _read(tmp_path, printings, ["Lightning Bolt"]) == {
        "lightning bolt": "bolt-2xm"
    }


def test_names_match_with_accents_and_case_ignored(tmp_path: Path) -> None:
    printings = [_printing("Lórien Revealed", "lorien")]
    assert _read(tmp_path, printings, ["Lorien revealed"]) == {
        "lorien revealed": "lorien-m10"
    }


def test_a_full_name_wins_over_a_face(tmp_path: Path) -> None:
    # "Fire" is a face of both, but only Fire // Ice is called that whole
    printings = [
        _printing("Fire // Ice", "fire-ice", card_faces=_faces("Fire", "Ice")),
        _printing("Start // Fire", "start-fire", card_faces=_faces("Start", "Fire")),
    ]
    found = _read(tmp_path, printings, ["Fire // Ice", "Start // Fire"])
    assert found == {"fire // ice": "fire-ice-m10", "start // fire": "start-fire-m10"}


def test_a_double_faced_card_is_found_by_its_front(tmp_path: Path) -> None:
    printings = [
        _printing(
            "Delver of Secrets // Insectile Aberration",
            "delver",
            card_faces=_faces("Delver of Secrets", "Insectile Aberration"),
        )
    ]
    assert _read(tmp_path, printings, ["Delver of Secrets"]) == {
        "delver of secrets": "delver-m10"
    }


def test_a_front_face_wins_over_another_face(tmp_path: Path) -> None:
    printings = [
        _printing("Stomp // Other", "front", card_faces=_faces("Stomp", "Other")),
        _printing("Giant // Stomp", "back", card_faces=_faces("Giant", "Stomp")),
    ]
    assert _read(tmp_path, printings, ["Stomp"]) == {"stomp": "front-m10"}


def test_an_adventure_is_found_by_its_spell(tmp_path: Path) -> None:
    printings = [
        _printing(
            "Bonecrusher Giant // Stomp",
            "giant",
            card_faces=_faces("Bonecrusher Giant", "Stomp"),
        )
    ]
    assert _read(tmp_path, printings, ["Stomp"]) == {"stomp": "giant-m10"}


def test_a_name_of_two_cards_is_left_out(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    printings = [_printing("Twin", "one"), _printing("Twin", "two")]
    assert _read(tmp_path, printings, ["Twin"]) == {}
    assert "Leaving out 'Twin' - 2 cards have that name" in caplog.text


def test_an_unknown_name_is_left_out(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    assert _read(tmp_path, [_printing("Counterspell", "c")], ["Lightnig Bolt"]) == {}
    assert "Leaving out 'Lightnig Bolt' - no card of that name" in caplog.text


@pytest.mark.parametrize(
    "not_a_card",
    [
        {"layout": "token"},
        {"layout": "art_series"},
        {"layout": "emblem"},
        {"layout": "double_faced_token"},
        # An Alchemy or other Arena-only card
        {"games": ["arena"]},
    ],
)
def test_tokens_art_cards_and_digital_cards_are_not_cards(
    tmp_path: Path, not_a_card: dict[str, Any]
) -> None:
    # A token with a card's name doesn't make the name stand for two cards
    printings = [
        _printing("Goblin", "card"),
        _printing("Goblin", "token", **not_a_card),
    ]
    assert _read(tmp_path, printings, ["Goblin"]) == {"goblin": "card-m10"}


def test_a_card_with_no_regular_printing_is_left_out(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    printings = [_printing("Promo Only", "promo", promo=True)]
    assert _read(tmp_path, printings, ["Promo Only"]) == {}
    assert "Leaving out 'Promo Only' - no regular printing to show" in caplog.text


def test_a_malformed_printing_is_never_chosen(tmp_path: Path) -> None:
    good = _printing("Lightning Bolt", "bolt", set="m10", released_at="2009-07-17")
    # Newer, so it would be chosen, but a Card can't be built from it
    broken = _printing("Lightning Bolt", "bolt", set="2xm", released_at="2020-08-07")
    broken["card_faces"] = None
    assert _read(tmp_path, [good, broken], ["Lightning Bolt"]) == {
        "lightning bolt": "bolt-m10"
    }


def test_unreadable_lines_are_skipped(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    printings = ['{"cut off', "[1, 2]", _printing("Lightning Bolt", "bolt")]
    assert _read(tmp_path, printings, ["Lightning Bolt"]) == {
        "lightning bolt": "bolt-m10"
    }
    assert "Skipped 2 unreadable line(s)" in caplog.text


def test_two_names_of_one_card_share_one_card(tmp_path: Path) -> None:
    path = _bulk_file(
        tmp_path / "cards.jsonl.gz",
        [
            _printing(
                "Delver of Secrets // Insectile Aberration",
                "delver",
                card_faces=_faces("Delver of Secrets", "Insectile Aberration"),
            )
        ],
    )
    cards = read_cards(
        path, ["Delver of Secrets", "Delver of Secrets // Insectile Aberration"]
    )
    assert (
        cards["delver of secrets"] is cards["delver of secrets // insectile aberration"]
    )


class FakeDownload:
    """The response requests.get(stream=True) gives, for `body`"""

    def __init__(self, body: bytes, status: int = 200) -> None:
        self.body = body
        self.status = status

    def raise_for_status(self) -> None:
        if self.status != 200:
            raise requests.HTTPError(f"{self.status} error")

    def iter_content(self, chunk_size: int) -> Iterator[bytes]:
        for start in range(0, len(self.body), chunk_size):
            yield self.body[start : start + chunk_size]


def _gzipped(text: str) -> bytes:
    return gzip.compress(text.encode("utf-8"))


def _serve(
    monkeypatch: MonkeyPatch, body: bytes, size: int | None = None, status: int = 200
) -> list[str]:
    """Scryfall offers `body` as its card data, made at MADE; returns the
    addresses downloaded"""
    info = {**INFO, "compressed_size": len(body) if size is None else size}
    monkeypatch.setattr(bulk, "fetch_bulk_info", lambda: info)
    downloaded: list[str] = []

    def fake_get(url: str, **kwargs: Any) -> nullcontext[FakeDownload]:
        downloaded.append(url)
        # Used in a with block, like a real response
        return nullcontext(FakeDownload(body, status))

    monkeypatch.setattr("meta_morphis.scryfall.bulk.requests.get", fake_get)
    return downloaded


def _old_copy(path: Path) -> Path:
    path.write_bytes(_gzipped("old\n"))
    os.utime(path, (MADE - 86400, MADE - 86400))
    return path


def test_a_newer_file_is_downloaded_and_dated_when_scryfall_made_it(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    # In a folder not made yet, as on the first run
    path = tmp_path / "data" / "cards.jsonl.gz"
    downloaded = _serve(monkeypatch, _gzipped("new\n"))
    monkeypatch.setattr("meta_morphis.scryfall.bulk.time.time", lambda: MADE + 60)

    update_bulk_file(path)

    assert downloaded == [INFO["jsonl_download_uri"]]
    assert gzip.decompress(path.read_bytes()) == b"new\n"
    assert path.stat().st_mtime == MADE
    assert bulk_file_age(path) == 60
    # Nothing left under the temporary name
    assert [f.name for f in path.parent.iterdir()] == ["cards.jsonl.gz"]


def test_an_older_copy_is_replaced(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    path = _old_copy(tmp_path / "cards.jsonl.gz")
    _serve(monkeypatch, _gzipped("new\n"))

    update_bulk_file(path)

    assert gzip.decompress(path.read_bytes()) == b"new\n"


def test_an_up_to_date_copy_is_not_downloaded_again(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    path = tmp_path / "cards.jsonl.gz"
    path.write_bytes(_gzipped("current\n"))
    os.utime(path, (MADE, MADE))
    downloaded = _serve(monkeypatch, _gzipped("new\n"))

    update_bulk_file(path)

    assert downloaded == []
    assert gzip.decompress(path.read_bytes()) == b"current\n"


@pytest.mark.parametrize(
    "body, size, status",
    [
        # Cut short: fewer bytes than Scryfall said
        (_gzipped("new\n" * 1000)[:-10], len(_gzipped("new\n" * 1000)), 200),
        # The right size, but damaged inside
        (b"\x1f\x8b" + b"x" * 30, None, 200),
        # Not there
        (b"", None, 404),
    ],
)
def test_a_failed_download_keeps_the_old_copy(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    body: bytes,
    size: int | None,
    status: int,
) -> None:
    path = _old_copy(tmp_path / "cards.jsonl.gz")
    _serve(monkeypatch, body, size, status)

    update_bulk_file(path)

    assert gzip.decompress(path.read_bytes()) == b"old\n"
    assert path.stat().st_mtime == MADE - 86400
    assert [f.name for f in tmp_path.iterdir()] == ["cards.jsonl.gz"]
    assert "Could not download Scryfall's card data" in caplog.text


@pytest.mark.parametrize(
    "answer, message",
    [
        (RequestUnavailable("timed out"), "Could not ask Scryfall"),
        (None, "Scryfall has no card data file"),
        ({"updated_at": "yesterday"}, "unusable"),
    ],
)
def test_no_usable_answer_keeps_the_old_copy(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    answer: Any,
    message: str,
) -> None:
    path = _old_copy(tmp_path / "cards.jsonl.gz")

    def fake_info() -> Any:
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(bulk, "fetch_bulk_info", fake_info)
    caplog.set_level(logging.WARNING)

    update_bulk_file(path)

    assert gzip.decompress(path.read_bytes()) == b"old\n"
    assert message in caplog.text
