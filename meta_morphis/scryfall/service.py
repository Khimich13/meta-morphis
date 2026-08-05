import sqlite3
import time
import config

from typing_extensions import Any

from .repo import (
    get_card_from_cache,
    get_card_age,
    save_cards_to_cache
)
from .client import (
    fetch_single,
    fetch_batch,
    batch
)
from meta_morphis.models.meta import MetaEntry

def fetch_one_by_one(conn: sqlite3.Connection, names: list[str]) -> list[dict[str, Any]]:
    cards = []
    print(f"Failed to find {len(names)} card(s) in Scryfall in batch request")
    print(f"This/these card(s) will be fetched from either Scryfall or cache one by one")
    for name in names:
        cached = get_card_from_cache(conn, name)
        if cached:
            print(f"Card {name} found in cache")
            cards.append(cached)
            continue
        
        time.sleep(0.1)
        fetched = fetch_single(name)
        if fetched:
            print(f"Found card {name} in Scryfall")
            cards.append(fetched)
            continue

        print("Not found:", name)
    return cards

def classify_cards(conn: sqlite3.Connection, meta: list[MetaEntry]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    fresh = []
    outdated = []
    missing = []

    for entry in meta:
        name = entry.name
        cached = get_card_from_cache(conn, name)

        if cached:
            age = get_card_age(conn, name)
            if age and age > config.SCRYFALL_REFRESH_RATE:
                outdated.append(cached)
            else:
                fresh.append(cached)
        else:
            missing.append(name)

    return fresh, outdated, missing

def refresh_outdated(conn: sqlite3.Connection, outdated: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    names = [card["name"] for card in outdated]
    refreshed = []
    for batch_names in batch(names):
        raw = fetch_batch(conn, batch_names)
        if raw:
            cards = process_batch_request(conn, raw)
            refreshed.extend(cards)

    refreshed_names = {card["name"] for card in refreshed}
    not_refreshed = [card for card in outdated if card["name"] not in refreshed_names]
    return refreshed, not_refreshed

def fetch_cards(conn: sqlite3.Connection, meta: list[MetaEntry]) -> list[dict[str, Any]]:
    output = []

    fresh, outdated, missing = classify_cards(conn, meta)
    output.extend(fresh)

    if missing:
        print("Trying to fetch missing names...")
        for batch_names in batch(missing):
            raw = fetch_batch(conn, batch_names)
            if raw:
                cards = process_batch_request(conn, raw)
                save_cards_to_cache(conn, cards)
                output.extend(cards)

    if outdated:
        print("Trying to fetch outdated names...")
        refreshed, not_refreshed = refresh_outdated(conn, outdated)

        print(f"{len(refreshed)} outdated cards were refreshed successfully")
        save_cards_to_cache(conn, refreshed)
        output.extend(refreshed)
        
        if not_refreshed:
            print(f"{len(not_refreshed)} outdated cards were not refreshed")
            output.extend(not_refreshed)

    if not output:
        raise RuntimeError("No cards have been fetched either from Scryfall or from cache")
    return output

def process_batch_request(conn: sqlite3.Connection, raw: dict[str, Any]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = raw.get("data", [])
    if not cards:
        print(f"Scryfall error: no data received")
        return cards

    not_found = raw.get("not_found", [])
    if not_found:
        missing_names = [item["name"] for item in not_found]
        cards.extend(fetch_one_by_one(conn, missing_names))

    return cards