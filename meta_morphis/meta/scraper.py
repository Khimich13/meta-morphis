from bs4 import BeautifulSoup

from meta_morphis.models.meta import MetaEntry
from meta_morphis.utils.http import request_with_retries


def scrape_meta_cards(url: str) -> list[MetaEntry] | None:
    raw = request_with_retries(
        "GET",
        url=url,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    if raw:
        return parse_meta_table(raw)
    
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

        meta_entry = MetaEntry(
            name= name,
            rank= int(cols[0].text.strip()),
            percent= float(cols[3].text.strip().replace("%", "")),
            avg_copies= float(cols[4].text.strip()),
        )
        if "//" in name:
            meta_entry.lookup_name = name.split("//")[0].strip()
        
        meta.append(meta_entry)
        
    return meta