from typing import Callable, TypeVar

from bs4 import BeautifulSoup
from bs4.element import Tag

from meta_morphis import config
from meta_morphis.models.meta import MetaEntry
from meta_morphis.utils.http import RequestUnavailable, request_with_retries

T = TypeVar("T")

# Maps each field we need to the CSS class MTGGoldfish puts on its <th>.
_COLUMN_CLASSES = {
    "rank": "col-rank",
    "name": "col-card",
    "percent": "col-decks",
    "avg_copies": "col-played",
}


def scrape_meta_cards(url: str) -> list[MetaEntry] | None:
    try:
        raw = request_with_retries(
            "GET",
            url=url,
            headers=config.GOLDFISH_HEADERS
        )
    except RequestUnavailable:
        return None
    if not raw:
        return None

    result = _parse_meta_table(raw)
    if result is None:
        return None

    meta, skipped_count = result

    if skipped_count > config.BAD_ROWS_LIMIT:
        return None

    return meta

def _parse_cell(cell: Tag, cast: Callable[[str], T]) -> T | None:
    try:
        return cast(cell.text.strip())
    except Exception:
        return None

def _locate_columns(table: Tag) -> dict[str, int] | None:
    # Map each field name to its column index using <thead>'s <th> classes.
    thead = table.find("thead")
    if thead is None:
        return None

    class_to_index: dict[str, int] = {}
    for i, th in enumerate(thead.find_all("th")):
        for css_class in th.get("class") or []:
            class_to_index[css_class] = i

    columns: dict[str, int] = {}
    for field, css_class in _COLUMN_CLASSES.items():
        if css_class not in class_to_index:
            return None
        columns[field] = class_to_index[css_class]

    return columns

def _parse_meta_table(html: str) -> tuple[list[MetaEntry], int] | None:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.table-staples")

    if not table:
        return None

    columns = _locate_columns(table)
    if columns is None:
        return None

    required_cols = max(columns.values()) + 1

    entries: list[MetaEntry] = []
    skipped_count = 0

    for row in table.select("tr"):
        cols = row.find_all("td")

        if not cols:
            # Not a data row at all
            continue

        if len(cols) < required_cols:
            skipped_count += 1
            continue

        rank = _parse_cell(cols[columns["rank"]], int)

        name_cell = cols[columns["name"]]
        anchor = name_cell.find("a")
        name = _parse_cell(anchor, str) if anchor else _parse_cell(name_cell, str)

        percent = _parse_cell(cols[columns["percent"]], lambda s: float(s.replace("%", "")))
        avg_copies = _parse_cell(cols[columns["avg_copies"]], float)

        if not name or (rank is None and percent is None and avg_copies is None):
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
