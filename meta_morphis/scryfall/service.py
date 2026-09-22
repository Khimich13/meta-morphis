import sqlite3
from typing import Any

from meta_morphis import config
from meta_morphis.models.card import Card
from meta_morphis.models.meta import MetaEntry
from meta_morphis.utils.http import RequestUnavailable

from .client import batch, fetch_batch, fetch_single
from .repo import (
    get_card_from_cache,
    record_bad_name_attempt,
    save_cards_to_cache,
    should_skip_lookup,
)


def fetch_cards(conn: sqlite3.Connection, meta: list[MetaEntry]) -> list[Card]:
    output: list[Card] = []

    fresh, outdated, missing = _classify_cards(conn, meta)
    output.extend(fresh)

    if outdated:
        print("Trying to fetch outdated names...")
        updates, unrecognized = _fetch_updates_for_outdated(conn, outdated)

        with conn:
            save_cards_to_cache(conn, updates)
        print(f"{len(updates)} outdated cards were refreshed successfully")
        output.extend(updates)
        
        if unrecognized:
            print(f"{len(unrecognized)} outdated cards were not found in Scryfall and was not refreshed")
            output.extend(unrecognized)

    if missing:
        print("Trying to fetch missing names...")
        for batch_names in batch(missing):
            try:
                raw = fetch_batch(batch_names)
            except RequestUnavailable as e:
                print(f"Could not fetch {len(batch_names)} missing card(s), Scryfall was unreachable ({e}) - will retry next run")
                continue
            if raw:
                cards = _process_batch_request(conn, raw)
                with conn:
                    save_cards_to_cache(conn, cards)
                output.extend(cards)
            else:
                print(f"Could not fetch {len(batch_names)} missing card(s) - no data received")

    if not output:
        raise RuntimeError("No cards have been fetched either from Scryfall or from cache")
    return output

def _classify_cards(conn: sqlite3.Connection, meta: list[MetaEntry]) -> tuple[list[Card], list[Card], list[str]]:
    fresh = []
    outdated = []
    missing = []

    for entry in meta:
        name = entry.lookup_name or entry.name
        
        cached = get_card_from_cache(conn, name)

        if cached:
            if cached.age > config.SCRYFALL_REFRESH_RATE:
                outdated.append(cached)
            else:
                fresh.append(cached)
        elif not should_skip_lookup(conn, name):
            missing.append(name)

    return fresh, outdated, missing

def _fetch_updates_for_outdated(conn: sqlite3.Connection, outdated: list[Card]) -> tuple[list[Card], list[Card]]:
    names = [card.name for card in outdated]
    updates: list[Card] = []
    
    for batch_names in batch(names):
        try:
            raw = fetch_batch(batch_names)
        except RequestUnavailable as e:
            print(f"Could not refresh {len(batch_names)} outdated card(s), Scryfall was unreachable ({e}) - will retry next run")
            continue
        if raw:
            cards = _process_batch_request(conn, raw)
            updates.extend(cards)
        else:
            print(f"Could not refresh {len(batch_names)} outdated card(s) - no data received")

    updates_names = {card.name for card in updates}
    unrecognized = [card for card in outdated if card.name not in updates_names]
    return updates, unrecognized

def _to_card(raw: dict[str, Any]) -> Card | None:
    try:
        return Card.from_raw(raw)
    except KeyError as e:
        print(f"Skipping malformed card from Scryfall, missing field {e}")
        return None

def _process_batch_request(conn: sqlite3.Connection, raw: dict[str, Any]) -> list[Card]:
    cards: list[Card] = []

    for entry in raw.get("data", []):
        card = _to_card(entry)
        if card:
            cards.append(card)

    not_found = raw.get("not_found", [])
    if not_found:
        missing_names = [item["name"] for item in not_found]
        for name in missing_names:
            try:
                fetched = fetch_single(name)
            except RequestUnavailable as e:
                print(f"Could not verify '{name}', Scryfall was unreachable ({e}) - will retry next run")
                continue
            card = _to_card(fetched) if fetched else None
            if card:
                cards.append(card)
            else:
                print(f"Bad name - {name} saved to card_lookup_failures")
                with conn:
                    record_bad_name_attempt(conn, name)

    if not cards:
        print("Scryfall error: no data received")

    return cards