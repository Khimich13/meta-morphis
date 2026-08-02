import sqlite3
import requests
import time
import config
from bs4 import BeautifulSoup

from meta_morphis.db.meta_repo import (
    should_refresh_meta, 
    load_cached_meta, 
    save_meta_to_cache, 
    update_meta_timestamp
)
from meta_morphis.models.meta import MetaEntry

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
    
def scrape_meta_cards(url: str) -> list[MetaEntry] | None:
    for attempt in range(3):
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)

        if r.status_code != 200:
            time.sleep(0.5 * (attempt + 1))
            continue

        meta = parse_meta_table(r.text)
        if meta:
            return meta
        
    # Failed to scrape
    return None

def parse_meta_table(html: str) -> list[MetaEntry] | None:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.table-staples")

    if not table:
        return None
    
    meta: list[MetaEntry] = []
    for row in table.select("tr"):
        cols = row.find_all("td")
        if not cols:
            continue
        name = cols[1].text.strip()
        if "//" in name:
            name = name.split("//")[0].strip()

        meta.append(
            MetaEntry(
                name= name,
                rank= int(cols[0].text.strip()),
                percent= float(cols[3].text.strip().replace("%", "")),
                deck_count= float(cols[4].text.strip())
            )
        )
    return meta