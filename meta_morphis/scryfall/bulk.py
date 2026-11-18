"""Scryfall's card data, from its file of every printing: "Default cards"
(https://scryfall.com/docs/api/bulk-data). Scryfall makes a new one each
day; it is downloaded only when Scryfall has made a newer one than the
copy kept from the last run, and read once per run. Scryfall asks for
its bulk files, not its API, when looking up many cards.

The file is gzipped JSON Lines: one printing per line, about 120,000 of
them, 81 MB as downloaded and 657 MB unpacked. It is read a line at a
time, so it is never all in memory at once.
"""

import gzip
import json
import logging
import os
import time
import zlib
from collections.abc import Iterable, Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from meta_morphis import config
from meta_morphis.models.card import Card, oracle_id_of
from meta_morphis.utils.http import RequestUnavailable
from meta_morphis.utils.text import card_count, normalize_name

from .artwork import choose_printing, for_choosing
from .client import fetch_bulk_info

log = logging.getLogger(__name__)

# Things in the file that aren't cards a deck can hold
NOT_CARDS = {"token", "double_faced_token", "art_series", "emblem"}

# The joke sets - Unglued, Unhinged, Unfinity and the like - and playtest
# cards. Their frames break the rules the app covers names by, and no
# deck for a real format holds them.
FUNNY_SET_TYPE = "funny"

# How a name on a list matched a card: its full name ("Fire // Ice"),
# its front face (MTGGoldfish lists a double-faced card by its front),
# or another face (the spell of an adventure card). The first kind that
# matched any card decides.
FULL_NAME, FRONT_FACE, OTHER_FACE = range(3)


def update_bulk_file(path: Path) -> None:
    """Downloads Scryfall's newest card data to `path` if it is newer than
    the copy there. The file's modification time is set to when Scryfall
    made it, which says how old the copy is. When Scryfall can't be
    reached, or the download fails, the copy there is kept.
    """
    try:
        info = fetch_bulk_info()
    except RequestUnavailable as e:
        log.warning(
            f"Could not ask Scryfall for its card data ({e}) - using the last copy"
        )
        return
    if info is None:
        log.warning("Scryfall has no card data file to offer - using the last copy")
        return
    try:
        url = str(info["jsonl_download_uri"])
        size = int(info["compressed_size"])
        made = datetime.fromisoformat(info["updated_at"]).timestamp()
    except (KeyError, TypeError, ValueError) as e:
        log.warning(
            f"Scryfall's answer about its card data was unusable ({e}) - using the last copy"
        )
        return

    if path.exists() and path.stat().st_mtime >= made:
        log.info("Scryfall's card data is up to date")
        return

    log.info(f"Downloading Scryfall's card data ({size / 1e6:.0f} MB)...")
    try:
        _download(url, size, path, made)
    except (requests.RequestException, OSError, EOFError, zlib.error, ValueError) as e:
        log.warning(
            f"Could not download Scryfall's card data ({e}) - using the last copy"
        )
        return
    log.info("Downloaded Scryfall's card data")


def _download(url: str, size: int, path: Path, made: float) -> None:
    """Downloads under a temporary name and checks the whole file unpacks
    before swapping it in, so a download cut short never replaces a good
    copy - the same as write_json in export.py."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    try:
        with requests.get(
            url, headers=config.SCRYFALL_FILE_HEADERS, stream=True, timeout=60
        ) as response:
            response.raise_for_status()
            with temp.open("wb") as file:
                for chunk in response.iter_content(chunk_size=1 << 20):
                    file.write(chunk)
        if temp.stat().st_size != size:
            raise ValueError(f"got {temp.stat().st_size} bytes, Scryfall said {size}")
        # A damaged file fails here, with EOFError or a gzip error
        with gzip.open(temp, "rb") as unpacked:
            while unpacked.read(1 << 24):
                pass
        os.utime(temp, (made, made))
        temp.replace(path)
    finally:
        # Gone already after the swap
        temp.unlink(missing_ok=True)


def bulk_file_age(path: Path) -> float:
    """How long ago Scryfall made the copy at `path`, in seconds"""
    return time.time() - path.stat().st_mtime


def read_cards(path: Path, names: Iterable[str]) -> dict[str, Card]:
    """The card each name stands for, in the printing the app shows - see
    artwork.py - keyed by normalize_name of the name. A name with no card,
    more than one card, or no printing to show is left out and logged.
    """
    wanted = {normalize_name(name): name for name in names}
    # For each name, the cards it matched, by how - see FULL_NAME
    matches: dict[str, list[set[str]]] = {}
    printings: dict[str, list[dict[str, Any]]] = {}
    unreadable = 0

    with gzip.open(path, "rt", encoding="utf-8") as file:
        for line in file:
            printing = _parse(line)
            if printing is None:
                unreadable += 1
                continue
            oracle_id = oracle_id_of(printing)
            if not oracle_id or not _is_game_card(printing):
                continue
            matched = False
            for how, name in _names(printing):
                key = normalize_name(name)
                if key in wanted:
                    matches.setdefault(key, [set(), set(), set()])[how].add(oracle_id)
                    matched = True
            # A printing a Card can't be built from - a field missing, or
            # the wrong shape - is left out here, so it is never chosen
            if matched and _to_card(printing):
                printings.setdefault(oracle_id, []).append(printing)

    if unreadable:
        log.warning(f"Skipped {unreadable} unreadable line(s) of Scryfall's card data")

    cards: dict[str, Card] = {}
    # One Card for each card, however many names lead to it
    shown: dict[str, Card] = {}
    for key, name in wanted.items():
        found = next((ids for ids in matches.get(key, []) if ids), set())
        if not found:
            log.warning(
                f"Leaving out '{name}' - no card of that name in Scryfall's data"
            )
            continue
        if len(found) > 1:
            log.warning(f"Leaving out '{name}' - {len(found)} cards have that name")
            continue
        [oracle_id] = found
        if oracle_id not in shown:
            chosen = choose_printing(printings.get(oracle_id, []))
            if chosen is None:
                log.warning(f"Leaving out '{name}' - no regular printing to show")
                continue
            shown[oracle_id] = Card.from_raw(chosen)
        cards[key] = shown[oracle_id]
    return cards


def read_every_card(path: Path) -> dict[str, Card]:
    """Every card in Scryfall's data, in the printing the app shows - see
    artwork.py - keyed by oracle id. Left out: a card with no printing to
    show, and one printed only in the joke sets (FUNNY_SET_TYPE).

    The file is read twice. Holding all 120,000 printings whole until
    each card's is chosen takes 2.3 GB, so the first reading keeps only
    the fields choose_printing reads, and the second builds a Card from
    each chosen printing alone: 650 MB at most, and 17 s (measured
    2026-11-17).
    """
    printings: dict[str, list[dict[str, Any]]] = {}
    # The cards with a printing outside the joke sets
    serious: set[str] = set()
    unreadable = 0
    with gzip.open(path, "rt", encoding="utf-8") as file:
        for line in file:
            printing = _parse(line)
            if printing is None:
                unreadable += 1
                continue
            oracle_id = oracle_id_of(printing)
            if not oracle_id or not _is_game_card(printing):
                continue
            # As in read_cards, a printing a Card can't be built from is
            # never chosen
            if not _to_card(printing):
                continue
            printings.setdefault(oracle_id, []).append(for_choosing(printing))
            if printing.get("set_type") != FUNNY_SET_TYPE:
                serious.add(oracle_id)

    if unreadable:
        log.warning(f"Skipped {unreadable} unreadable line(s) of Scryfall's card data")

    # The id of each card's chosen printing, and the card it stands for
    chosen: dict[str, str] = {}
    no_printing = 0
    for oracle_id, its_printings in printings.items():
        if oracle_id not in serious:
            continue
        printing = choose_printing(its_printings)
        if printing is None:
            no_printing += 1
            continue
        chosen[printing["id"]] = oracle_id
    jokes = len(printings) - len(serious)
    log.info(
        f"Found {card_count(len(chosen))} in Scryfall's data, leaving out "
        f"{jokes} printed only in joke sets and {no_printing} with no "
        "regular printing to show"
    )
    del printings

    cards: dict[str, Card] = {}
    with gzip.open(path, "rt", encoding="utf-8") as file:
        for line in file:
            printing = _parse(line)
            if printing is None or printing.get("id") not in chosen:
                continue
            card = _to_card(printing)
            if card:
                cards[chosen[printing["id"]]] = card
    return cards


def _parse(line: str) -> dict[str, Any] | None:
    try:
        printing = json.loads(line)
    except json.JSONDecodeError:
        return None
    return printing if isinstance(printing, dict) else None


def _is_game_card(printing: dict[str, Any]) -> bool:
    # Alchemy's rebalanced cards ("A-...") and other Arena-only cards
    # have no paper printing
    games = printing.get("games")
    return (
        printing.get("layout") not in NOT_CARDS
        and isinstance(games, list)
        and "paper" in games
    )


def _names(printing: dict[str, Any]) -> Iterator[tuple[int, str]]:
    """The printing's names a list may use, each with how it matches"""
    name = printing.get("name")
    if isinstance(name, str):
        yield FULL_NAME, name
    faces = printing.get("card_faces")
    if not isinstance(faces, list):
        return
    for index, face in enumerate(faces):
        face_name = face.get("name") if isinstance(face, dict) else None
        if isinstance(face_name, str):
            yield (FRONT_FACE if index == 0 else OTHER_FACE), face_name


def _to_card(raw: dict[str, Any]) -> Card | None:
    # A missing field is a KeyError; a field of the wrong shape - `null`,
    # a list, card_faces: null - is a TypeError or AttributeError
    try:
        return Card.from_raw(raw)
    except (KeyError, TypeError, AttributeError):
        return None
