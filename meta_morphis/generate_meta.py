import requests
import time
from bs4 import BeautifulSoup

from meta_morphis.db.cache import should_refresh_meta, load_cached_meta, save_meta_to_cache, update_meta_timestamp
from meta_morphis.formats import FORMATS

def get_meta_cards(conn, format) -> list[dict]:
    if not should_refresh_meta(conn, format):
        print("Using cached meta data\n")
        return load_cached_meta(conn, format)

    print("Refreshing meta data from MTGGoldfish...\n")
    
    url = FORMATS[format]
    meta_list = scrape_meta_cards(url)

    if not meta_list:
        print("Failed fetching data from MTGGoldfish...\n")
        print("Using cached meta data instead\n")
        cached_meta = load_cached_meta(conn, format)
        if len(cached_meta) > 0:
            return cached_meta
        print("Error: there was no cached meta data!\n")
        raise(Exception("Program has failed to find meta info!"))

    save_meta_to_cache(conn, meta_list, format)

    update_meta_timestamp(conn, format)
    return meta_list
    

def scrape_meta_cards(url):
    for attempt in range(3):
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)

        if r.status_code != 200:
            # Retry on transient errors
            time.sleep(0.5 * (attempt + 1))
            continue

        soup = BeautifulSoup(r.text, "html.parser")
        table = soup.select_one("table.table-staples")

        if not table:
            time.sleep(0.5 * (attempt + 1))
            continue
        
        meta_list = []
        for row in table.select("tr"):
            cols = row.find_all("td")
            if not cols:
                continue
            name = cols[1].text.strip()
            if "//" in name:
                print(f"{name} - this is a double name that Scryfall doesn't like, so we use just the first part of a double name")
                name = name.split("//")[0].strip()
            meta_list.append({
                "name": name,
                "rank": int(cols[0].text.strip()),
                "percent": float(cols[3].text.strip().replace("%", "")),
                "deck_count": float(cols[4].text.strip()),
            })

        return meta_list 
    # Failed to scrape
    return None