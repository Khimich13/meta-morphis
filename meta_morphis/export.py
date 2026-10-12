"""Writes the card data the web app reads: one <format>.json per format.

Run with: uv run python -m meta_morphis.export
"""
import json
import sqlite3
from pathlib import Path
from typing import TypedDict

from meta_morphis import config
from meta_morphis.db.connection import get_connection
from meta_morphis.db.init_db import init_db
from meta_morphis.meta.service import get_meta_cards
from meta_morphis.models.card import Card
from meta_morphis.scryfall.service import fetch_cards


class ExportCard(TypedDict):
    oracle_id: str
    name: str
    # One picture per physical side: two for a double-faced card
    images: list[str]


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
    # Without an id the app can't tell cards apart, and without a
    # picture it has nothing to show - leave such a card out.
    images = image_urls(card)
    if not card.oracle_id or not images:
        return None
    return {"oracle_id": card.oracle_id, "name": card.name, "images": images}

def build_export(format_name: str, cards: list[Card]) -> ExportFile:
    exported: list[ExportCard] = []
    for card in cards:
        built = build_card(card)
        if built is None:
            print(f"Leaving out '{card.name}' - no oracle id or no picture")
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
    cards = fetch_cards(conn, meta)
    return write_export(build_export(format_name, cards), out_dir)

def main() -> None:
    with get_connection() as conn:
        init_db(conn)
        for format_name in config.EXPORT_FORMATS:
            path = export_format(conn, format_name, config.EXPORT_DIR)
            print(f"Wrote {path}")

if __name__ == "__main__":
    main()
