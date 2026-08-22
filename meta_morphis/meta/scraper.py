import requests
import time
from bs4 import BeautifulSoup

from meta_morphis.models.meta import MetaEntry

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
        anchor = cols[1].find("a")
        if anchor:
            name = anchor.text.strip()
        else:
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