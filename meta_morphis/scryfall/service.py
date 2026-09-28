import sqlite3
from typing import Any

from meta_morphis import config
from meta_morphis.models.card import Card
from meta_morphis.models.meta import MetaEntry
from meta_morphis.utils.http import RequestUnavailable
from meta_morphis.utils.text import normalize_name

from .client import batch, fetch_batch, fetch_single
from .repo import (
    add_alias,
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
                cards, _ = _process_batch_request(conn, raw)
                with conn:
                    save_cards_to_cache(conn, cards)
                output.extend(cards)
            else:
                print(f"Could not fetch {len(batch_names)} missing card(s) - no data received")

    if not output:
        raise RuntimeError("No cards have been fetched either from Scryfall or from cache")
    return output

def _classify_cards(conn: sqlite3.Connection, meta: list[MetaEntry]) -> tuple[list[Card], list[Card], list[str]]:
    fresh: list[Card] = []
    outdated: list[Card] = []
    missing: list[str] = []

    for entry in meta:
        name = entry.lookup_name or entry.name

        cached = get_card_from_cache(conn, name)

        if cached:
            if cached.age > config.SCRYFALL_REFRESH_RATE:
                if should_skip_lookup(conn, name):
                    # A refresh was recently confirmed to fail for this
                    # name - serve the stale copy instead of
                    # hammering Scryfall again every run for the length
                    # of the cooldown.
                    fresh.append(cached)
                else:
                    outdated.append(cached)
            else:
                fresh.append(cached)
        elif not should_skip_lookup(conn, name):
            missing.append(name)

    return fresh, outdated, missing

def _fetch_updates_for_outdated(conn: sqlite3.Connection, outdated: list[Card]) -> tuple[list[Card], list[Card]]:
    # Correlated by the OLD (requested) name, not the refreshed card's new
    # name - Scryfall errata renames (or a fuzzy-resolved correction) can
    # legitimately give a card a different name than it was cached under,
    # and comparing old-name-in-new-names used to put the same physical
    # card in both `updates` and `unrecognized`.
    names = [card.name for card in outdated]
    updates: list[Card] = []
    unresolved_names: set[str] = set()

    for batch_names in batch(names):
        try:
            raw = fetch_batch(batch_names)
        except RequestUnavailable as e:
            print(f"Could not refresh {len(batch_names)} outdated card(s), Scryfall was unreachable ({e}) - will retry next run")
            unresolved_names.update(batch_names)
            continue
        if raw:
            cards, unresolved = _process_batch_request(conn, raw)
            updates.extend(cards)
            unresolved_names.update(unresolved)
        else:
            print(f"Could not refresh {len(batch_names)} outdated card(s) - no data received")
            unresolved_names.update(batch_names)

    unrecognized = [card for card in outdated if card.name in unresolved_names]
    return updates, unrecognized

def _to_card(raw: dict[str, Any]) -> Card | None:
    try:
        return Card.from_raw(raw)
    except KeyError as e:
        print(f"Skipping malformed card from Scryfall, missing field {e}")
        return None

def _process_batch_request(conn: sqlite3.Connection, raw: dict[str, Any]) -> tuple[list[Card], list[str]]:
    cards: list[Card] = []
    # Requested names that did NOT resolve to a card this run, whether
    # Scryfall confirmed the name doesn't exist or we simply couldn't
    # check because of an outage - either way, there's no refreshed card
    # for it right now. Only a confirmed miss is ever recorded via
    # record_bad_name_attempt; an outage never is
    unresolved_names: list[str] = []

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
                unresolved_names.append(name)
                continue
            card = _to_card(fetched) if fetched else None
            if card:
                cards.append(card)
                if normalize_name(card.name) != normalize_name(name):
                    # Scryfall's own matching (fuzzy, or a lenient exact
                    # match) resolved this to a different canonical name
                    # than normalize_name would derive from what was
                    # searched - register the searched spelling as an
                    # alias too, so it hits cache next run instead of
                    # asking Scryfall about it again forever. The card
                    # row must exist first for the alias's foreign key.
                    with conn:
                        save_cards_to_cache(conn, [card])
                        add_alias(conn, name, card.name)
            else:
                print(f"Bad name - {name} saved to card_lookup_failures")
                with conn:
                    record_bad_name_attempt(conn, name)
                unresolved_names.append(name)

    if not cards:
        print("Scryfall error: no data received")

    return cards, unresolved_names