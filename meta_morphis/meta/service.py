import logging
import sqlite3

from meta_morphis import config
from meta_morphis.models.meta import MetaEntry

from .repo import (
    get_meta_from_cache,
    save_meta_to_cache,
    should_refresh_meta,
    update_meta_timestamp,
)
from .scraper import scrape_meta_cards

log = logging.getLogger(__name__)


def get_meta_cards(conn: sqlite3.Connection, format_name: str) -> list[MetaEntry]:
    # Validated before the cache check, so an unknown format always fails
    # the same way - otherwise it depended on the database: a leftover
    # cache row for it was served silently, and no row meant a bare KeyError.
    url = config.GOLDFISH_FORMAT_URLS.get(format_name)
    if url is None:
        known = ", ".join(config.GOLDFISH_FORMAT_URLS)
        raise ValueError(f"Unknown format {format_name!r}, expected one of: {known}")

    if not should_refresh_meta(conn, format_name):
        log.info("Using cached meta data")
        return get_meta_from_cache(conn, format_name)

    log.info("Refreshing meta data from MTGGoldfish...")

    meta = scrape_meta_cards(url)

    if not meta:
        log.warning("Failed fetching data from MTGGoldfish...")
        cached = get_meta_from_cache(conn, format_name)
        if cached:
            log.warning("Using cached meta data instead")
            return cached
        raise RuntimeError("Program has failed to find meta info!")

    with conn:
        save_meta_to_cache(conn, meta, format_name)
        update_meta_timestamp(conn, format_name)
    return meta