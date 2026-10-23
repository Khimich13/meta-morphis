import logging
import sqlite3
from typing import Any

from meta_morphis import config
from meta_morphis.models.card import Card
from meta_morphis.models.meta import MetaEntry
from meta_morphis.utils.http import RequestUnavailable
from meta_morphis.utils.lists import chunked
from meta_morphis.utils.text import normalize_name

from .artwork import choose_printing
from .client import fetch_batch, fetch_single, search_printings
from .repo import (
    add_alias,
    get_card_from_cache,
    get_chosen_printing,
    record_bad_name_attempt,
    save_cards_to_cache,
    save_chosen_printing,
    should_skip_lookup,
)

log = logging.getLogger(__name__)


def fetch_cards(conn: sqlite3.Connection, meta: list[MetaEntry]) -> list[Card]:
    output: list[Card] = []

    fresh, outdated, missing = _classify_cards(conn, meta)
    output.extend(fresh)

    if outdated:
        log.info("Trying to fetch outdated names...")
        updates, unrecognized = _fetch_updates_for_outdated(conn, outdated)

        with conn:
            save_cards_to_cache(conn, updates)
        log.info(f"{len(updates)} outdated cards were refreshed successfully")
        output.extend(updates)

        if unrecognized:
            log.warning(f"{len(unrecognized)} outdated cards were not found in Scryfall and were not refreshed")
            output.extend(unrecognized)

    if missing:
        log.info("Trying to fetch missing names...")
        for batch_names in chunked(missing, config.SCRYFALL_BATCH_SIZE_LIMIT):
            try:
                raw = fetch_batch(batch_names)
            except RequestUnavailable as e:
                log.warning(f"Could not fetch {len(batch_names)} missing card(s), Scryfall was unreachable ({e}) - will retry next run")
                continue
            if raw:
                cards, _ = _process_batch_request(conn, raw)
                with conn:
                    save_cards_to_cache(conn, cards)
                output.extend(cards)
            else:
                log.warning(f"Could not fetch {len(batch_names)} missing card(s) - no data received")

    if not output:
        raise RuntimeError("No cards have been fetched either from Scryfall or from cache")
    return output

def get_display_printings(conn: sqlite3.Connection, cards: list[Card]) -> list[Card]:
    """The printing of each card the app should show, in the same order -
    see scryfall/artwork.py. A fresh saved choice is reused; the others
    are chosen from printings fetched SCRYFALL_PRINTINGS_PER_SEARCH cards
    at a time. Falls back to the last choice, or to the card itself, when
    Scryfall can't help, so a card is never left out for lack of a choice.
    """
    shown: dict[str, Card] = {}
    cached: dict[str, Card] = {}
    to_choose: list[str] = []
    for card in cards:
        oracle_id = card.oracle_id
        if not oracle_id or oracle_id in shown or oracle_id in to_choose:
            continue
        saved = get_chosen_printing(conn, oracle_id)
        # A choice "from the future" was saved by a clock that ran ahead -
        # treat it as old rather than trusting it indefinitely
        if saved and 0 <= saved.age <= config.SCRYFALL_REFRESH_RATE:
            shown[oracle_id] = saved
        else:
            if saved:
                cached[oracle_id] = saved
            to_choose.append(oracle_id)

    for group in chunked(to_choose, config.SCRYFALL_PRINTINGS_PER_SEARCH):
        try:
            printings = search_printings(group)
        except RequestUnavailable as e:
            log.warning(
                f"Could not choose printings for {len(group)} card(s), "
                f"Scryfall was unreachable ({e})"
            )
            continue

        # One search answers for the whole group: sort the printings back
        # to their cards
        by_card: dict[str, list[dict[str, Any]]] = {}
        for printing in printings:
            by_card.setdefault(printing.get("oracle_id", ""), []).append(printing)

        for oracle_id in group:
            chosen = choose_printing(by_card.get(oracle_id, []))
            if chosen is None:
                continue
            try:
                display = Card.from_raw(chosen)
            except KeyError:
                continue
            with conn:
                save_chosen_printing(conn, oracle_id, chosen)
            shown[oracle_id] = display

    # The fallbacks, for every card that got no new choice
    return [
        shown.get(card.oracle_id, cached.get(card.oracle_id, card)) if card.oracle_id else card
        for card in cards
    ]

def _classify_cards(conn: sqlite3.Connection, meta: list[MetaEntry]) -> tuple[list[Card], list[Card], list[str]]:
    fresh: list[Card] = []
    outdated: list[Card] = []
    missing: list[str] = []

    for entry in meta:
        name = entry.lookup_name or entry.name

        cached = get_card_from_cache(conn, name)

        if cached:
            # Negative age = written by a clock that ran ahead, treat as stale
            if cached.age < 0 or cached.age > config.SCRYFALL_REFRESH_RATE:
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

    for batch_names in chunked(names, config.SCRYFALL_BATCH_SIZE_LIMIT):
        try:
            raw = fetch_batch(batch_names)
        except RequestUnavailable as e:
            log.warning(f"Could not refresh {len(batch_names)} outdated card(s), Scryfall was unreachable ({e}) - will retry next run")
            unresolved_names.update(batch_names)
            continue
        if raw:
            cards, unresolved = _process_batch_request(conn, raw)
            updates.extend(cards)
            unresolved_names.update(unresolved)
        else:
            log.warning(f"Could not refresh {len(batch_names)} outdated card(s) - no data received")
            unresolved_names.update(batch_names)

    unrecognized = [card for card in outdated if card.name in unresolved_names]
    return updates, unrecognized

def _to_card(raw: dict[str, Any]) -> Card | None:
    try:
        return Card.from_raw(raw)
    except KeyError as e:
        log.warning(f"Skipping malformed card from Scryfall, missing field {e}")
        return None

def _process_batch_request(conn: sqlite3.Connection, raw: dict[str, Any]) -> tuple[list[Card], list[str]]:
    cards: list[Card] = []
    # Requested names that did NOT resolve to a card this run, whether
    # Scryfall confirmed the name doesn't exist, sent data we couldn't
    # parse, or we simply couldn't check because of an outage - either
    # way, there's no refreshed card for it right now. Only a confirmed
    # miss is ever recorded via record_bad_name_attempt; an outage never is
    unresolved_names: list[str] = []

    for entry in raw.get("data", []):
        card = _to_card(entry)
        if card:
            cards.append(card)
        elif "name" in entry:
            # Reported, so a refresh serves the stale copy instead of dropping it
            unresolved_names.append(entry["name"])

    not_found = raw.get("not_found", [])
    if not_found:
        missing_names = [item["name"] for item in not_found]
        for name in missing_names:
            try:
                fetched = fetch_single(name)
            except RequestUnavailable as e:
                log.warning(f"Could not verify '{name}', Scryfall was unreachable ({e}) - will retry next run")
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
                log.warning(f"Bad name - {name} saved to card_lookup_failures")
                with conn:
                    record_bad_name_attempt(conn, name)
                unresolved_names.append(name)

    if not cards:
        log.warning("Scryfall error: no data received")

    return cards, unresolved_names