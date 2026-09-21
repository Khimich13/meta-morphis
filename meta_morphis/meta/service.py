import sqlite3

from meta_morphis import config
from meta_morphis.models.meta import MetaEntry

from .repo import (
    load_cached_meta,
    save_meta_to_cache,
    should_refresh_meta,
    update_meta_timestamp,
)
from .scraper import scrape_meta_cards


def get_meta_cards(conn: sqlite3.Connection, format_name: str) -> list[MetaEntry]:
    if not should_refresh_meta(conn, format_name):
        print("Using cached meta data\n")
        return load_cached_meta(conn, format_name)

    print("Refreshing meta data from MTGGoldfish...\n")
    
    url = config.FORMATS[format_name]
    meta = scrape_meta_cards(url)

    if not meta:
        print("Failed fetching data from MTGGoldfish...\n")
        cached = load_cached_meta(conn, format_name)
        if cached:
            print("Using cached meta data instead\n")
            return cached
        raise(RuntimeError("Program has failed to find meta info!"))

    with conn:
        save_meta_to_cache(conn, meta, format_name)
        update_meta_timestamp(conn, format_name)
    return meta