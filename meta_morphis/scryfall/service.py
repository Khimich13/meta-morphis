import sqlite3
import time
from typing import Any

import config
from meta_morphis.models.meta import MetaEntry

from .client import batch, fetch_batch, fetch_single
from .repo import get_card_from_cache, save_cards_to_cache


def classify_cards(conn: sqlite3.Connection, meta: list[MetaEntry]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    fresh = []
    outdated = []
    missing = []

    for entry in meta:
        name = entry.lookup_name or entry.name
        
        cached = get_card_from_cache(conn, name)

        if cached:
            if cached.age > config.SCRYFALL_REFRESH_RATE:
                outdated.append(cached.to_raw())
            else:
                fresh.append(cached.to_raw())
        else:
            missing.append(name)

    return fresh, outdated, missing

def refresh_outdated(conn: sqlite3.Connection, outdated: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    names = [card["name"] for card in outdated]
    refreshed = []
    
    for batch_names in batch(names):
        raw = fetch_batch(batch_names)
        if raw:
            cards = process_batch_request(raw)
            refreshed.extend(cards)

    refreshed_names = {card["name"] for card in refreshed}
    not_refreshed = [card for card in outdated if card["name"] not in refreshed_names]
    return refreshed, not_refreshed

def fetch_cards(conn: sqlite3.Connection, meta: list[MetaEntry]) -> list[dict[str, Any]]:
    output = []

    fresh, outdated, missing = classify_cards(conn, meta)
    output.extend(fresh)

    if outdated:
        print("Trying to fetch outdated names...")
        refreshed, not_refreshed = refresh_outdated(conn, outdated)

        print(f"{len(refreshed)} outdated cards were refreshed successfully")
        save_cards_to_cache(conn, refreshed)
        output.extend(refreshed)
        
        if not_refreshed:
            print(f"{len(not_refreshed)} outdated cards were not refreshed")
            output.extend(not_refreshed)

    if missing:
        print("Trying to fetch missing names...")
        for batch_names in batch(missing):
            raw = fetch_batch(batch_names)
            if raw:
                cards = process_batch_request(raw)
                save_cards_to_cache(conn, cards)
                output.extend(cards)

    if not output:
        raise RuntimeError("No cards have been fetched either from Scryfall or from cache")
    return output

def process_batch_request(raw: dict[str, Any]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = raw.get("data", [])

    not_found = raw.get("not_found", [])
    if not_found:
        missing_names = [item["name"] for item in not_found]
        for name in missing_names:
            fetched = fetch_single(name)
            if fetched:
                cards.append(fetched)

    if not cards:
        print(f"Scryfall error: no data received")

    return cards