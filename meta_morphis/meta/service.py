import logging
import sqlite3

from meta_morphis import config
from meta_morphis.models.meta import MetaEntry
from meta_morphis.utils.text import card_count, normalize_name

from .repo import (
    get_meta_from_cache,
    save_meta_to_cache,
    should_refresh_meta,
    update_meta_timestamp,
)
from .scraper import scrape_meta_cards

log = logging.getLogger(__name__)


def get_meta_cards(
    conn: sqlite3.Connection, format_name: str, kind: str
) -> list[MetaEntry]:
    """One list of one format, e.g. "pauper" and "lands" - see
    GOLDFISH_LISTS in config.py. It is cached under its list name."""
    name = config.list_name(format_name, kind)
    # Validated before the cache check, so an unknown list always fails
    # the same way - otherwise it depended on the database: a leftover
    # cache row for it was served silently, and no row meant a bare KeyError.
    url = config.GOLDFISH_LIST_URLS.get(name)
    if url is None:
        known = ", ".join(config.GOLDFISH_LIST_URLS)
        raise ValueError(f"Unknown list {name!r}, expected one of: {known}")

    if not should_refresh_meta(conn, name):
        log.info("Using cached meta data")
        return get_meta_from_cache(conn, name)

    log.info("Refreshing meta data from MTGGoldfish...")

    meta = scrape_meta_cards(url)

    # A list too short to export counts as a failed fetch. Saving it would
    # replace the cached list, and its new timestamp would stop the next
    # runs from trying again until GOLDFISH_REFRESH_RATE has passed.
    minimum = config.min_cards(kind)
    if meta is not None and len(meta) < minimum:
        log.warning(
            f"MTGGoldfish's {name} list has only {card_count(len(meta))}, "
            f"expected at least {minimum} - its page may have been cut short"
        )
        meta = None

    if not meta:
        log.warning("Failed fetching data from MTGGoldfish...")
        cached = get_meta_from_cache(conn, name)
        if cached:
            log.warning("Using cached meta data instead")
            return cached
        raise RuntimeError("Program has failed to find meta info!")

    # Read before saving, which replaces it
    previous = get_meta_from_cache(conn, name)

    with conn:
        save_meta_to_cache(conn, meta, name)
        update_meta_timestamp(conn, name)

    if previous:
        _log_list_changes(name, previous, meta)
    return meta

def list_changes(
    before: list[MetaEntry], after: list[MetaEntry]
) -> tuple[list[str], list[str]]:
    """The card names that entered and that left the list, each in list
    order. Names are compared by normalize_name, so a change of spelling
    or accents alone isn't counted as a different card.
    """
    before_keys = {normalize_name(entry.name) for entry in before}
    after_keys = {normalize_name(entry.name) for entry in after}
    entered = [e.name for e in after if normalize_name(e.name) not in before_keys]
    left = [e.name for e in before if normalize_name(e.name) not in after_keys]
    return entered, left

def _log_list_changes(
    format_name: str, before: list[MetaEntry], after: list[MetaEntry]
) -> None:
    entered, left = list_changes(before, after)
    if not entered and not left:
        log.info(f"The {format_name} list did not change")
        return
    if entered:
        log.info(f"{card_count(len(entered))} entered the {format_name} list: {', '.join(entered)}")
    if left:
        log.info(f"{card_count(len(left))} left the {format_name} list: {', '.join(left)}")
