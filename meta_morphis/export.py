"""Writes the card data the web app reads: one <format>.json per format.

Run with: uv run python -m meta_morphis.export
"""
import json
import logging
import sqlite3
from pathlib import Path
from typing import TypedDict

from meta_morphis import config
from meta_morphis.db.connection import get_connection
from meta_morphis.db.init_db import init_db
from meta_morphis.meta.service import get_meta_cards
from meta_morphis.models.card import Card
from meta_morphis.scryfall.service import fetch_cards, get_display_printing

log = logging.getLogger(__name__)


class ExportCard(TypedDict):
    oracle_id: str
    name: str
    # One picture per physical side: two for a double-faced card
    images: list[str]
    # The front side's artwork alone, and who painted it. Scryfall asks
    # for the artist to be named wherever the artwork is shown by itself.
    art: str
    artist: str


class ExportFile(TypedDict):
    format: str
    cards: list[ExportCard]


def image_urls(card: Card) -> list[str]:
    urls: list[str] = []
    for side in card.image_sides():
        # "grid" is the WebP version of "normal" - same picture, smaller file
        url = side.image_uris.get("grid") or side.image_uris.get("normal")
        if url:
            urls.append(url)
    return urls

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
        "art": art,
        "artist": front.artist,
    }

def build_export(format_name: str, cards: list[Card]) -> ExportFile:
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
    return {"format": format_name, "cards": exported}

def write_export(data: ExportFile, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{data['format']}.json"
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path

def export_format(conn: sqlite3.Connection, format_name: str, out_dir: Path) -> Path:
    meta = get_meta_cards(conn, format_name)
    # The printing each card is shown with - see scryfall/artwork.py
    cards = [get_display_printing(conn, card) for card in fetch_cards(conn, meta)]
    data = build_export(format_name, cards)
    if len(data["cards"]) < config.EXPORT_MIN_CARDS:
        raise RuntimeError(
            f"Only {len(data['cards'])} usable cards for {format_name}, "
            f"expected at least {config.EXPORT_MIN_CARDS} - not writing the file"
        )
    path = write_export(data, out_dir)
    count = len(data["cards"])
    log.info(f"Wrote {path}: {count} {'card' if count == 1 else 'cards'}")
    return path

def main() -> None:
    # Show this package's progress and warnings, one plain line each
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    with get_connection() as conn:
        init_db(conn)
        for format_name in config.EXPORT_FORMATS:
            export_format(conn, format_name, config.EXPORT_DIR)

if __name__ == "__main__":
    main()
