"""A format's most played cards, counted from the decklists Magic Online
publishes (https://www.mtgo.com/decklists), as fbettega's archive on
GitHub keeps them: one JSON file per event, under
Tournaments/MTGO/<yyyy>/<mm>/<dd>/<format>-....json. The rank, deck %
and copies are this project's own count, not another site's statistics.

Each run lists the last DECKLISTS_DAYS days of the archive, downloads
the files not yet in DECKLISTS_DIR, and deletes the days that have
fallen out of that window. A day's folder fills in during the day, so
past days are listed again on every run. Listing costs a few calls to
GitHub's API, one for each year and one for each month in the window.

MTGO publishes the top finishers of its Challenges and only the
undefeated League decks, so the counts describe winning decks.
"""

import json
import logging
import os
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from meta_morphis import config
from meta_morphis.models.meta import MetaEntry
from meta_morphis.utils.http import RequestUnavailable, request_with_retries
from meta_morphis.utils.text import normalize_name

log = logging.getLogger(__name__)

# One deck: the copies of each card in it, main deck and sideboard
# together, keyed by the card's name as the list spells it
Deck = dict[str, int]


@dataclass
class DeckCount:
    """A format's count of its decks"""

    # Every card played, most played first - see rank_cards
    cards: list[MetaEntry]
    # The day of the newest event counted: the archive is a day or two
    # behind, and stops moving if the archive stops. None with no decks.
    decks_to: date | None


def count_meta_cards(
    format_name: str,
    today: date | None = None,
    folder: Path = config.DECKLISTS_DIR,
) -> DeckCount | None:
    """Every card played in the format's decks of the last DECKLISTS_DAYS
    days. None when the archive can't be listed.
    """
    days = _window(today or datetime.now(timezone.utc).date())
    paths = _list_files(format_name, days)
    if paths is None:
        return None

    _delete_old_days(folder, days[0])
    new = [path for path in paths if not (folder / path).exists()]
    for path in new:
        _download(path, folder)

    decks: list[Deck] = []
    # The day of each event with decks
    event_days: list[date] = []
    for path in paths:
        file = folder / path
        if file.exists():
            event_decks = _read_decks(file)
            decks.extend(event_decks)
            if event_decks:
                event_days.append(_day_of(path))
    newest = max(event_days, default=None)
    log.info(
        f"Counted {len(decks)} {format_name} decks from {len(event_days)} events "
        f"of the last {config.DECKLISTS_DAYS} days, the newest on {newest} "
        f"({len(new)} downloaded now)"
    )
    return DeckCount(rank_cards(decks), newest)


def rank_cards(decks: list[Deck]) -> list[MetaEntry]:
    """The cards of these decks, most played first. `percent` is the
    share of decks with the card in the main deck or the sideboard, and
    `avg_copies` the mean of its copies there, the two added together,
    in the decks that play it. A tie goes to more copies, then by name.

    Names are compared by normalize_name, so "Lórien Revealed" and
    "Lorien Revealed" are one card; the first spelling seen is kept.
    """
    names: dict[str, str] = {}
    playing: dict[str, int] = {}
    copies: dict[str, int] = {}
    for deck in decks:
        # Its copies of each card, however the deck spells its name
        in_deck: dict[str, int] = {}
        for name, count in deck.items():
            key = normalize_name(name)
            names.setdefault(key, name)
            in_deck[key] = in_deck.get(key, 0) + count
        for key, count in in_deck.items():
            playing[key] = playing.get(key, 0) + 1
            copies[key] = copies.get(key, 0) + count

    def avg(key: str) -> float:
        return copies[key] / playing[key]

    order = sorted(playing, key=lambda key: (-playing[key], -avg(key), key))
    return [
        MetaEntry(
            name=names[key],
            rank=rank,
            percent=round(100 * playing[key] / len(decks), 1),
            avg_copies=round(avg(key), 1),
        )
        for rank, key in enumerate(order, start=1)
    ]


def _window(today: date) -> list[date]:
    """The days counted, oldest first, today last"""
    return [
        today - timedelta(days=back) for back in reversed(range(config.DECKLISTS_DAYS))
    ]


def _list_files(format_name: str, days: list[date]) -> list[str] | None:
    """The format's files of these days, as paths under DECKLISTS_FOLDER
    ("2026/10/10/pauper-challenge-32-....json"). None if GitHub can't be
    reached or answers with something other than a folder listing.
    """
    wanted = set(days)
    paths: list[str] = []
    try:
        for year in sorted({day.year for day in days}):
            months = _api(f"contents/{config.DECKLISTS_FOLDER}/{year}")
            # No folder for the year yet, on its first day
            if months is None:
                continue
            month_trees = {
                entry["name"]: entry["sha"]
                for entry in months
                if entry.get("type") == "dir"
            }
            for month in sorted({day.month for day in days if day.year == year}):
                sha = month_trees.get(f"{month:02}")
                if sha is None:
                    continue
                # Every file of the month in one call: about 500 of them
                tree = _api(f"git/trees/{sha}?recursive=1")
                if tree is None:
                    continue
                if tree.get("truncated"):
                    log.warning(
                        f"GitHub cut short the list of {year}-{month:02}'s "
                        "decklists; some events are left out"
                    )
                for entry in tree["tree"]:
                    path = _wanted_path(entry, year, month, format_name, wanted)
                    if path:
                        paths.append(path)
    except RequestUnavailable as e:
        log.warning(f"The decklist archive could not be listed ({e})")
        return None
    except (KeyError, TypeError, AttributeError) as e:
        log.warning(f"The decklist archive's listing was not as expected ({e!r})")
        return None
    return sorted(paths)


def _wanted_path(
    entry: dict[str, Any], year: int, month: int, format_name: str, days: set[date]
) -> str | None:
    """The path of one of the month's files under DECKLISTS_FOLDER, if
    it is an event of the format on one of these days. The format is
    the start of the file's name, so "modern-" is not "premodern-".
    """
    if entry.get("type") != "blob":
        return None
    day, _, name = str(entry.get("path", "")).partition("/")
    if not (day.isdigit() and name.startswith(f"{format_name}-")):
        return None
    if "/" in name or not name.endswith(".json"):
        return None
    try:
        on = date(year, month, int(day))
    except ValueError:
        return None
    return f"{year}/{month:02}/{day}/{name}" if on in days else None


def _day_of(path: str) -> date:
    """The day of an event's file, from its path under DECKLISTS_FOLDER:
    "2026/10/10/pauper-challenge-32-....json" is 2026-10-10"""
    year, month, day = path.split("/")[:3]
    return date(int(year), int(month), int(day))


def _api(path: str) -> Any:
    """One call to GitHub's API about the archive: the parsed answer, or
    None for a folder that doesn't exist"""
    headers = dict(config.DECKLISTS_HEADERS)
    # Set in the daily run on GitHub, for its higher limit
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    raw = request_with_retries(
        "GET", config.DECKLISTS_API_URL + path, headers=headers, timeout=30
    )
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise RequestUnavailable(f"GitHub's answer was not JSON: {e}") from e


def _download(path: str, folder: Path) -> None:
    """Saves one event's file to `folder`/`path`. One that fails is left
    out of this run and tried again on the next."""
    url = f"{config.DECKLISTS_RAW_URL}{config.DECKLISTS_FOLDER}/{path}"
    try:
        raw = request_with_retries(
            "GET",
            url,
            headers={"User-Agent": config.DECKLISTS_HEADERS["User-Agent"]},
            timeout=30,
        )
    except RequestUnavailable as e:
        log.warning(f"Leaving out {path} for now - it could not be downloaded ({e})")
        return
    if raw is None:
        log.warning(f"Leaving out {path} - the archive no longer has it")
        return
    # Checked before saving: a file once saved is never downloaded again
    try:
        json.loads(raw)
    except json.JSONDecodeError:
        log.warning(f"Leaving out {path} for now - it was not JSON")
        return
    file = folder / path
    file.parent.mkdir(parents=True, exist_ok=True)
    temp = file.with_name(file.name + ".part")
    temp.write_text(raw, encoding="utf-8")
    temp.replace(file)


def _delete_old_days(folder: Path, first_day: date) -> None:
    """Deletes the days before `first_day`, of every format, and the
    year and month folders left empty"""
    for day_folder in sorted(folder.glob("*/*/*")):
        try:
            year, month, day = (int(part) for part in day_folder.parts[-3:])
            on = date(year, month, day)
        except ValueError:
            continue
        if on < first_day and day_folder.is_dir():
            shutil.rmtree(day_folder)
    for empty in sorted(folder.glob("*/*"), reverse=True) + sorted(folder.glob("*")):
        if empty.is_dir() and not any(empty.iterdir()):
            empty.rmdir()


def _read_decks(file: Path) -> list[Deck]:
    """The decks of one event's file. A file that can't be read, and a
    deck or card line of the wrong shape, is left out and logged."""
    try:
        event = json.loads(file.read_text(encoding="utf-8"))
        listed = event["Decks"]
        if not isinstance(listed, list):
            raise TypeError("Decks is not a list")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
        log.warning(f"Leaving out {file.name} - it could not be read ({e!r})")
        return []

    decks: list[Deck] = []
    bad = 0
    for listed_deck in listed:
        deck = _deck(listed_deck)
        if deck:
            decks.append(deck)
        else:
            bad += 1
    if bad:
        log.warning(f"Left out {bad} unreadable deck(s) of {file.name}")
    return decks


def _deck(listed: Any) -> Deck | None:
    """One deck's cards, main deck and sideboard added together. None if
    it isn't a deck: not an object, or with no readable card line."""
    if not isinstance(listed, dict):
        return None
    deck: Deck = {}
    for part in ("Mainboard", "Sideboard"):
        lines = listed.get(part)
        for line in lines if isinstance(lines, list) else []:
            card = _card_line(line)
            if card:
                name, count = card
                deck[name] = deck.get(name, 0) + count
    return deck or None


def _card_line(line: Any) -> tuple[str, int] | None:
    if not isinstance(line, dict):
        return None
    name, count = line.get("CardName"), line.get("Count")
    # bool is an int too
    if not isinstance(name, str) or not name.strip():
        return None
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        return None
    return name.strip(), count
