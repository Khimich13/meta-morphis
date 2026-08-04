import sqlite3
import config

from meta_morphis.models.meta import MetaEntry
from .repo import (
    should_refresh_meta, 
    load_cached_meta, 
    save_meta_to_cache, 
    update_meta_timestamp
)
from .scraper import scrape_meta_cards

def get_meta_cards(conn: sqlite3.Connection, format: str) -> list[MetaEntry]:
    if not should_refresh_meta(conn, format):
        print("Using cached meta data\n")
        return load_cached_meta(conn, format)

    print("Refreshing meta data from MTGGoldfish...\n")
    
    url = config.FORMATS[format]
    meta = scrape_meta_cards(url)

    if meta is None:
        print("Failed fetching data from MTGGoldfish...\n")
        cached = load_cached_meta(conn, format)
        if cached:
            print("Using cached meta data instead\n")
            return cached
        raise(RuntimeError("Program has failed to find meta info!"))

    save_meta_to_cache(conn, meta, format)
    update_meta_timestamp(conn, format)
    return meta