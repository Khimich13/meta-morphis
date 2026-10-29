"""Writes the card data the web app reads: one <format>.json per format.

Run with: uv run python -m meta_morphis.export
"""
import json
import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from meta_morphis import config
from meta_morphis.db.connection import get_connection
from meta_morphis.db.init_db import init_db
from meta_morphis.meta.repo import get_meta_timestamp
from meta_morphis.meta.service import get_meta_cards
from meta_morphis.models.card import Card
from meta_morphis.scryfall.service import fetch_cards, get_display_printings

log = logging.getLogger(__name__)


class ExportCard(TypedDict):
    oracle_id: str
    name: str
    # One picture per physical side: two for a double-faced card
    images: list[str]
    # The same pictures larger, which the app loads only when the player
    # zooms into the card; empty when Scryfall lacks one for any side
    large_images: list[str]
    # The front side's artwork alone, and who painted it. Scryfall asks
    # for the artist to be named wherever the artwork is shown by itself.
    art: str
    artist: str


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

def build_card(card: Card) -> ExportCard | None:
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
    return {
        "oracle_id": card.oracle_id,
        "name": card.name,
        "images": images,
        "large_images": large_image_urls(card),
        "art": art,
        "artist": front.artist,
    }

def build_export(format_name: str, cards: list[Card], list_updated: str) -> ExportFile:
    exported: list[ExportCard] = []
    for card in cards:
        built = build_card(card)
        if built is None:
            log.warning(f"Leaving out '{card.name}' - no oracle id, picture or artist, "
                  "or pictures of different printings")
            continue
        exported.append(built)

    # Sorted so the file doesn't reshuffle between runs
    exported.sort(key=lambda c: c["name"])
    return {"format": format_name, "list_updated": list_updated, "cards": exported}

def write_export(data: ExportFile, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{data['format']}.json"
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path

def is_basic_land(card: Card) -> bool:
    """Plains, Snow-Covered Island, Wastes and so on: "Basic" is a word of
    their type line before the dash, e.g. "Basic Snow Land — Island".
    Asking which card a basic land's artwork belongs to teaches nothing.
    """
    return "Basic" in card.type_line.split("—")[0].split()

def export_format(conn: sqlite3.Connection, format_name: str, out_dir: Path) -> Path:
    """Exports one list; format_name is its name, e.g. "pauper-lands" -
    see list_name in config.py."""
    meta = get_meta_cards(conn, format_name)
    list_updated = _check_list_age(conn, format_name)
    cards = [card for card in fetch_cards(conn, meta) if not is_basic_land(card)]
    # The printing each card is shown with - see scryfall/artwork.py
    cards = get_display_printings(conn, cards)
    data = build_export(format_name, cards, list_updated)
    minimum = (
        config.EXPORT_MIN_LANDS if format_name.endswith("-lands") else config.EXPORT_MIN_CARDS
    )
    if len(data["cards"]) < minimum:
        raise RuntimeError(
            f"Only {len(data['cards'])} usable cards for {format_name}, "
            f"expected at least {minimum} - not writing the file"
        )
    path = write_export(data, out_dir)
    count = len(data["cards"])
    log.info(f"Wrote {path}: {count} {'card' if count == 1 else 'cards'}")
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
            f"{age // (24 * 60 * 60)} days ago - not publishing it. "
            "The warnings above say why fetching failed."
        )
    return datetime.fromtimestamp(fetched, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def export_all(
    conn: sqlite3.Connection, formats: list[str], kinds: list[str], out_dir: Path
) -> list[str]:
    """Exports each list of each format on its own: one that fails keeps
    the file it had, and the others are still written. Then writes
    formats.json. Returns the lists that failed.
    """
    failed: list[str] = []
    for format_name in formats:
        for kind in kinds:
            name = config.list_name(format_name, kind)
            try:
                export_format(conn, name, out_dir)
            except Exception:
                # With the full error, so the log says why
                log.exception(f"Could not export {name} - keeping its previous file, if any")
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
            kind for kind in kinds
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
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path

def main() -> int:
    """Exit code 1 if any format failed. The files that could be written
    are still there, so the daily run can publish them and then report
    the failure.
    """
    # Show this package's progress and warnings, one plain line each
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    with get_connection() as conn:
        init_db(conn)
        failed = export_all(
            conn, config.GOLDFISH_FORMATS, config.GOLDFISH_LISTS, config.EXPORT_DIR
        )

    if failed:
        log.error(f"Failed to export: {', '.join(failed)}")
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
