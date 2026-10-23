import os
from pathlib import Path

_DAY = 24 * 60 * 60

# MTGGoldfish
GOLDFISH_FORMATS = ["pauper", "premodern", "pioneer", "standard", "modern"]
# Each format's most played cards: "all" is creatures and spells
# together (no lands), and the others are each kind on its own
GOLDFISH_LISTS = ["all", "creatures", "spells", "lands"]


def list_name(format_name: str, kind: str) -> str:
    """The name a list is cached and exported under: the format's own
    name for "all", as before the other lists existed, e.g. "pauper",
    and "pauper-creatures" for the others.
    """
    return format_name if kind == "all" else f"{format_name}-{kind}"


GOLDFISH_LIST_URLS = {
    list_name(format_name, kind):
        f"https://www.mtggoldfish.com/format-staples/{format_name}/full/{kind}"
    for format_name in GOLDFISH_FORMATS
    for kind in GOLDFISH_LISTS
}
GOLDFISH_HEADERS = {
    "User-Agent": "meta-morphis (https://github.com/Khimich13/meta-morphis)",
}
# 20 hours rather than a full day: the daily run on GitHub starts a few
# minutes earlier or later each day, and with a 24-hour limit a run that
# started early would find yesterday's list still "fresh" and skip it.
GOLDFISH_REFRESH_RATE = 20 * 60 * 60
GOLDFISH_BAD_ROWS_LIMIT = 10

# Scryfall
SCRYFALL_COLLECTION_URL = "https://api.scryfall.com/cards/collection"
SCRYFALL_NAMED_URL = "https://api.scryfall.com/cards/named"
SCRYFALL_SYMBOLOGY_URL = "https://api.scryfall.com/symbology"
SCRYFALL_SEARCH_URL = "https://api.scryfall.com/cards/search"
# Printings a player could meet at a table, for choosing a card's
# artwork: paper only, and none of the special versions - promos,
# gold-bordered and oversized cards (not tournament-legal), memorabilia,
# and showcase, borderless, extended-art, full-art or "future" frames.
SCRYFALL_REGULAR_PRINTINGS = (
    "game:paper -is:promo -is:digital -border:gold -is:oversized "
    "-st:memorabilia -frame:future -is:showcase -is:extendedart "
    "-is:fullart -is:borderless"
)
# Cards per printing search. Scryfall silently ignores the filters above
# once a query gets too long: tested in October 2026, 15 cards per search
# kept them and 20 did not, with no warning in the response. 10 leaves a
# margin, and scryfall/artwork.py checks every printing again anyway.
SCRYFALL_PRINTINGS_PER_SEARCH = 10
SCRYFALL_HEADERS = {
    "User-Agent": "meta-morphis/0.1.0 (+https://github.com/Khimich13/meta-morphis)",
    "Accept": "application/json",
}
SCRYFALL_REFRESH_RATE = 30 * _DAY
SCRYFALL_BATCH_SIZE_LIMIT = 75
SCRYFALL_BAD_NAMES_LOOKUP_COOLDOWN = 7 * _DAY
# /cards/collection and /cards/named are limited to 2 requests/second,
# and a 429 locks the client out for 30 seconds
# (https://scryfall.com/docs/api/rate-limits)
SCRYFALL_MIN_DELAY = 0.5
SCRYFALL_RATE_LIMIT_COOLDOWN = 30.0

# PWA data export
# An export with fewer usable cards than this fails instead of writing
# the file, so a failed fetch can't publish an empty or half-empty page.
EXPORT_MIN_CARDS = 45
# The same for a lands list, which loses its basic lands: up to 12 of
# them (Plains, Island, Swamp, Mountain, Forest and Wastes, each also
# snow-covered), plus a small margin
EXPORT_MIN_LANDS = 35
# An MTGGoldfish list older than this makes the export fail, so a lasting
# breakage of the scraper fails the daily run and GitHub reports it,
# instead of the old list being published day after day. A short outage
# still publishes the slightly older list. Keep in step with
# LIST_OLD_AFTER_DAYS in web/src/lib/cards.ts, which shows a banner.
EXPORT_STALE_AFTER = 3 * _DAY

# Database
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get("META_MORPHIS_DB") or PROJECT_ROOT / "data" / "cards.db")

# Web app data: one <format>.json per format, read by the app, and
# formats.json listing the formats that have one
EXPORT_DIR = PROJECT_ROOT / "web" / "public" / "data"
