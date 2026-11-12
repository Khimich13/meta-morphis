import logging
import sqlite3
from typing import Any

from meta_morphis import config
from meta_morphis.models.card import Card, oracle_id_of
from meta_morphis.models.meta import MetaEntry
from meta_morphis.utils.http import RequestUnavailable
from meta_morphis.utils.lists import chunked
from meta_morphis.utils.text import normalize_name

from .artwork import choose_printing
from .client import fetch_batch, fetch_by_oracle_ids, fetch_single, search_printings
from .repo import (
    add_alias,
    get_card_from_cache,
    get_chosen_printing,
    record_bad_name_attempt,
    rename_card,
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
            log.warning(f"Could not refresh {len(unrecognized)} outdated card(s) - using the cached copies")
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
                output.extend(_process_batch_request(conn, raw, batch_names))
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
        # to their cards. A printing a Card can't be built from - a field
        # missing, or the wrong shape - is left out here, so it can never
        # be chosen, and the card gets its best good printing instead
        by_card: dict[str, list[dict[str, Any]]] = {}
        for printing in printings:
            if _to_card(printing) is None:
                continue
            by_card.setdefault(oracle_id_of(printing) or "", []).append(printing)

        # One commit for the group's choices. The search is already done,
        # so the transaction never waits on Scryfall
        with conn:
            for oracle_id in group:
                chosen = choose_printing(by_card.get(oracle_id, []))
                if chosen is None:
                    continue
                save_chosen_printing(conn, oracle_id, chosen)
                shown[oracle_id] = Card.from_raw(chosen)

    # The fallbacks, for every card that got no new choice
    return [
        shown.get(card.oracle_id, cached.get(card.oracle_id, card)) if card.oracle_id else card
        for card in cards
    ]

def _classify_cards(conn: sqlite3.Connection, meta: list[MetaEntry]) -> tuple[list[Card], list[Card], list[str]]:
    fresh: list[Card] = []
    outdated: list[Card] = []
    missing: list[str] = []
    # Two names on the list can lead to one cached card, e.g. an old
    # spelling and the new one after Scryfall renamed it. The card is
    # classified once, under whichever name comes first - a second copy
    # would be counted, refreshed and exported twice
    seen: set[str] = set()

    for entry in meta:
        # A split card is looked up by its full name ("Fire // Ice"), never
        # by one face: "Fire" is also a face of Start // Fire. Scryfall's
        # batch lookup doesn't find full split names, so a split card
        # missing from the cache is fetched on its own by fetch_single.
        name = entry.name

        cached = get_card_from_cache(conn, name)

        if cached and cached.name in seen:
            continue
        if cached:
            seen.add(cached.name)
            # Negative age = written by a clock that ran ahead, treat as stale
            if cached.age < 0 or cached.age > config.SCRYFALL_REFRESH_RATE:
                # Checked under the cached card's name, not MTGGoldfish's:
                # a failed refresh is recorded under that name. They
                # differ for a double-faced card, which MTGGoldfish lists
                # by its front face only.
                if should_skip_lookup(conn, cached.name):
                    # A refresh was recently confirmed to fail for this
                    # card - serve the stale copy instead of
                    # hammering Scryfall again every run for the length
                    # of the cooldown.
                    fresh.append(cached)
                elif cached.oracle_id:
                    outdated.append(cached)
                else:
                    # The refresh asks by oracle_id. A card cached
                    # without one is fetched by name, like a new card
                    missing.append(name)
            else:
                fresh.append(cached)
        elif not should_skip_lookup(conn, name):
            missing.append(name)

    return fresh, outdated, missing

def _fetch_updates_for_outdated(conn: sqlite3.Connection, outdated: list[Card]) -> tuple[list[Card], list[Card]]:
    # Asked by oracle_id, a card's permanent identity, not by name: a
    # name can be answered with a different card (Scryfall's fuzzy
    # matching), and no longer finds the card once Scryfall renames it.
    stale = {card.oracle_id: card for card in outdated if card.oracle_id}
    updates: list[Card] = []

    for batch_ids in chunked(list(stale), config.SCRYFALL_BATCH_SIZE_LIMIT):
        try:
            raw = fetch_by_oracle_ids(batch_ids)
        except RequestUnavailable as e:
            log.warning(f"Could not refresh {len(batch_ids)} outdated card(s), Scryfall was unreachable ({e}) - will retry next run")
            continue
        if raw:
            updates.extend(_save_refreshed(conn, raw, stale))
        else:
            log.warning(f"Could not refresh {len(batch_ids)} outdated card(s) - no data received")

    # Whatever got no answer, for any reason, is served from its stale copy
    refreshed = {card.oracle_id for card in updates}
    unrecognized = [card for card in outdated if card.oracle_id not in refreshed]
    return updates, unrecognized

def _save_refreshed(conn: sqlite3.Connection, raw: dict[str, Any], stale: dict[str, Card]) -> list[Card]:
    """Save Scryfall's answer to a refresh and return its cards. `stale`
    is the cached copy of every card that was asked for, by oracle_id.
    """
    cards: list[Card] = []
    # One commit for the batch
    with conn:
        for entry in raw.get("data", []):
            card = _to_card(entry)
            old = stale.get(card.oracle_id or "") if card else None
            if not card or not old:
                continue
            save_cards_to_cache(conn, [card])
            # Same oracle_id under another name: Scryfall renamed the card
            if _answers_another_name(old.name, card):
                rename_card(conn, old.name, card.name)
            cards.append(card)

        # Scryfall no longer has the card. Recorded, so the cooldown
        # stops it from being asked for again every run
        for item in raw.get("not_found", []):
            old = stale.get(item.get("oracle_id") or "")
            if old:
                log.warning(f"Scryfall no longer has '{old.name}' - saved to card_lookup_failures")
                record_bad_name_attempt(conn, old.name)
    return cards

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

def _process_batch_request(conn: sqlite3.Connection, raw: dict[str, Any], asked: list[str]) -> list[Card]:
    """`asked` is the list of names that were sent to Scryfall for `raw`.
    The cards found are saved to the cache before they are returned.
    """
    cards: list[Card] = []
    # (name asked, the card it got) for every name Scryfall answered
    # with a card of a different name. The name is pointed at the card,
    # so it hits cache next run instead of asking Scryfall about it
    # again forever.
    aliases: list[tuple[str, Card]] = []

    data = raw.get("data", [])
    missing_names = [item["name"] for item in raw.get("not_found", [])]

    # Scryfall's /cards/collection docs promise the cards in the order
    # the names were asked for, with the names it didn't find left out
    # and listed in not_found instead - so skipping those pairs each
    # answer with the name it answers. If the counts differ, the pairs
    # can't be trusted: a wrong pair would hand one card's name to
    # another.
    found_names = [name for name in asked if name not in missing_names]
    paired = len(found_names) == len(data)
    if not paired:
        log.warning(
            f"Scryfall sent {len(data)} card(s) for {len(found_names)} name(s) - "
            "not pairing them with the names asked"
        )

    for i, entry in enumerate(data):
        card = _to_card(entry)
        if card:
            cards.append(card)
            if paired and _answers_another_name(found_names[i], card):
                aliases.append((found_names[i], card))

    # Only a confirmed miss is recorded via record_bad_name_attempt; an
    # outage never is
    for name in missing_names:
        try:
            fetched = fetch_single(name)
        except RequestUnavailable as e:
            log.warning(f"Could not verify '{name}', Scryfall was unreachable ({e}) - will retry next run")
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

    if not cards:
        log.warning("Scryfall error: no data received")
        return cards

    # One commit for the batch. Every lookup is done by now, so the
    # transaction never waits on Scryfall. The card rows are saved
    # before the aliases: an alias is a foreign key into them
    with conn:
        save_cards_to_cache(conn, cards)
        for name, card in aliases:
            add_alias(conn, name, card.name)

    return cards
