import requests
from bs4 import BeautifulSoup

from meta_morphis.db.cache import should_refresh_meta, load_cached_meta, save_meta_to_cache, update_meta_timestamp

URL = "https://www.mtggoldfish.com/format-staples/pauper/full/spells"

def get_meta_cards(conn) -> list[dict]:
    if not should_refresh_meta(conn):
        print("Using cached meta data")
        return load_cached_meta(conn)
    
    print("Refreshing meta data from MTGGoldfish...")
    meta_list = scrape_meta_cards()

    save_meta_to_cache(conn, meta_list)

    update_meta_timestamp(conn)
    return meta_list
    

def scrape_meta_cards():
    try:
        html = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=10).text
    except Exception as e:
        raise RuntimeError(f"Failed to fetch Goldfish meta: {e}")

    soup = BeautifulSoup(html, "html.parser")

    table = soup.select_one("table.table-staples")
    if not table:
        raise RuntimeError("Could not find staples table on page.")

    meta_list = []
    for row in table.select("tr"):
        cols = row.find_all("td")
        if not cols:
            continue
        meta_list.append({
            "name": cols[1].text.strip(),
            "rank": int(cols[0].text.strip()),
            "percent": float(cols[3].text.strip().replace("%", "")),
            "deck_count": float(cols[4].text.strip()),
        })

    return meta_list