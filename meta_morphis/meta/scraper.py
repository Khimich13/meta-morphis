from typing import Callable, TypeVar

from bs4 import BeautifulSoup
from bs4.element import Tag

import config

T = TypeVar("T")

from meta_morphis.models.meta import MetaEntry
from meta_morphis.utils.http import request_with_retries


def scrape_meta_cards(url: str) -> list[MetaEntry] | None:
    raw = request_with_retries(
        "GET",
        url=url,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    if not raw:
        return None
    
    result = parse_meta_table(raw)
    if result is None:
        return None

    meta, skipped_count = result

    if skipped_count > config.BED_ROWS_LIMIT:
        return None
        
    return meta

def _parse_cell(cell: Tag, cast: Callable[[str], T]) -> T | None:
    try:
        return cast(cell.text.strip())
    except Exception:
        return None

def parse_meta_table(html: str) -> tuple[list[MetaEntry], int] | None:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.table-staples")

    if not table:
        return None
    
    entries: list[MetaEntry] = []
    skipped_count = 0

    for row in table.select("tr"):
        cols = row.find_all("td")

        # Row must have at least 5 columns
        if len(cols) < 5:
            skipped_count += 1
            continue
        
        # Column 1 is the rank
        rank = _parse_cell(cols[0], int)
        # Column 2 is the name, which has an anchor tag next to it
        anchor = cols[1].find("a")
        if anchor:
            name = _parse_cell(anchor, str)
        else:
            name = _parse_cell(cols[1], str)
        # Column 3 is mana cost (not used)
        # Column 4 is percent of total decks using the card
        percent = _parse_cell(cols[3], lambda s: float(s.replace("%", "")))
        # Column 5 is average copies of the card in decks using it
        avg_copies = _parse_cell(cols[4], float)

        if name is None:
            skipped_count += 1
            continue

        meta_entry = MetaEntry(
            name = name,
            rank = rank,
            percent = percent,
            avg_copies= avg_copies,
        )
        if "//" in name:
            meta_entry.lookup_name = name.split("//")[0].strip()
        
        entries.append(meta_entry)
        
    return entries, skipped_count