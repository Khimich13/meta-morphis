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
                cards, _ = _process_batch_request(conn, raw, batch_names)
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

        # One commit for the group's choices. The search is already done,
        # so the transaction never waits on Scryfall
        with conn:
            for oracle_id in group:
                chosen = choose_printing(by_card.get(oracle_id, []))
                if chosen is None:
                    continue
                try:
                    display = Card.from_raw(chosen)
                except KeyError:
                    continue
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
        # A split card is looked up by its full name ("Fire // Ice"), never
        # by one face: "Fire" is also a face of Start // Fire. Scryfall's
        # batch lookup doesn't find full split names, so a split card
        # missing from the cache is fetched on its own by fetch_single.
        name = entry.name

        cached = get_card_from_cache(conn, name)

        if cached:
            # Negative age = written by a clock that ran ahead, treat as stale
            if cached.age < 0 or cached.age > config.SCRYFALL_REFRESH_RATE:
                # Checked under the cached card's name, not MTGGoldfish's:
                # the refresh asks Scryfall for that name and records a
                # failure under it. They differ for a double-faced card,
                # which MTGGoldfish lists by its front face only.
                if should_skip_lookup(conn, cached.name):
                    # A refresh was recently confirmed to fail for this
                    # card - serve the stale copy instead of
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
    # Two list names can lead to one cached card, e.g. an old spelling
    # and the new one after Scryfall renamed it - that card is in
    # `outdated` twice, and is asked about once
    names = list(dict.fromkeys(card.name for card in outdated))
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
            cards, unresolved = _process_batch_request(conn, raw, batch_names)
            updates.extend(cards)
            unresolved_names.update(unresolved)
        else:
            log.warning(f"Could not refresh {len(batch_names)} outdated card(s) - no data received")
            unresolved_names.update(batch_names)

    unrecognized = [card for card in outdated if card.name in unresolved_names]
    return updates, unrecognized

def _to_card(raw: dict[str, Any]) -> Card | None:
    # A missing field is a KeyError. An entry of the wrong shape - `null`,
    # a list, card_faces: null - fails with TypeError or AttributeError
    # instead, and must not take the rest of the batch down with it
    try:
        return Card.from_raw(raw)
    except KeyError as e:
        log.warning(f"Skipping malformed card from Scryfall, missing field {e}")
        return None
    except (TypeError, AttributeError) as e:
        log.warning(f"Skipping malformed card from Scryfall, wrong shape ({e})")
        return None

def _answers_another_name(name: str, card: Card) -> bool:
    """Scryfall answered `name` with a card of a different name - a
    spelling Scryfall corrected, the front face of a double-faced card,
    or the old name of a card Scryfall renamed.
    """
    return normalize_name(card.name) != normalize_name(name)

def _process_batch_request(
    conn: sqlite3.Connection, raw: dict[str, Any], asked: list[str]
) -> tuple[list[Card], list[str]]:
    """`asked` is the list of names that were sent to Scryfall for `raw`.
    The cards found are saved to the cache before they are returned.
    """
    cards: list[Card] = []
    # (name asked, the card it got) for every name Scryfall answered
    # with a card of a different name. The name is pointed at the card,
    # so it hits cache next run instead of asking Scryfall about it
    # again forever. For a renamed card, add_alias moves all of the old
    # row's names to the new card.
    aliases: list[tuple[str, Card]] = []
    # Requested names that did NOT resolve to a card this run, whether
    # Scryfall confirmed the name doesn't exist, sent data we couldn't
    # parse, or we simply couldn't check because of an outage - either
    # way, there's no refreshed card for it right now. Only a confirmed
    # miss is ever recorded via record_bad_name_attempt; an outage never is
    unresolved_names: list[str] = []

    data = raw.get("data", [])
    missing_names = [item["name"] for item in raw.get("not_found", [])]

    # Scryfall's /cards/collection docs promise the cards in the order
    # the names were asked for, with the names it didn't find left out
    # and listed in not_found instead - so skipping those pairs each
    # answer with the name it answers. If the counts differ, the pairs
    # can't be trusted: a wrong pair would hand one card's names to
    # another.
    found_names = [name for name in asked if name not in missing_names]
    paired = len(found_names) == len(data)
    if not paired:
        log.warning(
            f"Scryfall sent {len(data)} card(s) for {len(found_names)} name(s) - "
            "not checking them for renamed cards"
        )

    for i, entry in enumerate(data):
        card = _to_card(entry)
        if card:
            cards.append(card)
            if paired and _answers_another_name(found_names[i], card):
                aliases.append((found_names[i], card))
        elif paired:
            # Reported under the name that was asked, so a refresh serves
            # the stale copy instead of dropping it - the answer's own
            # name can differ when Scryfall renamed the card
            unresolved_names.append(found_names[i])
        elif isinstance(entry, dict) and "name" in entry:
            unresolved_names.append(entry["name"])

    if missing_names:
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
                if _answers_another_name(name, card):
                    aliases.append((name, card))
            else:
                log.warning(f"Bad name - {name} saved to card_lookup_failures")
                with conn:
                    record_bad_name_attempt(conn, name)
                unresolved_names.append(name)

    if not cards:
        log.warning("Scryfall error: no data received")
        return cards, unresolved_names

    # One commit for the batch. Every lookup is done by now, so the
    # transaction never waits on Scryfall. The card rows are saved first:
    # an alias is a foreign key into them.
    # Cards that turned out not to answer the name they were fetched for
    refused: list[Card] = []
    with conn:
        save_cards_to_cache(conn, cards)
        for name, card in aliases:
            if not add_alias(conn, name, card.name):
                # The name is a cached card of its own, and Scryfall's
                # fuzzy matching answered it with a different card. That
                # card is not what the name asked for, so it is left out
                # of this batch's answer and the name is reported
                # unresolved - the stale copy is served in its place.
                # Recorded as a failed lookup, or the same fuzzy match
                # would repeat every run until the cooldown stops it.
                refused.append(card)
                unresolved_names.append(name)
                record_bad_name_attempt(conn, name)
    if refused:
        cards = [c for c in cards if not any(c is r for r in refused)]

    return cards, unresolved_names