import os
from pathlib import Path

_DAY = 24 * 60 * 60

# MTGGoldfish
GOLDFISH_FORMAT_URLS = {
    "pauper": "https://www.mtggoldfish.com/format-staples/pauper/full/all",
    "premodern": "https://www.mtggoldfish.com/format-staples/premodern/full/all",
    "pioneer": "https://www.mtggoldfish.com/format-staples/pioneer/full/all",
    "standard": "https://www.mtggoldfish.com/format-staples/standard/full/all",
    "modern": "https://www.mtggoldfish.com/format-staples/modern/full/all",
}
GOLDFISH_HEADERS = {
    "User-Agent": "meta-morphis (https://github.com/Khimich13/meta-morphis)",
}
GOLDFISH_REFRESH_RATE = _DAY
GOLDFISH_BAD_ROWS_LIMIT = 10

# Scryfall
SCRYFALL_COLLECTION_URL = "https://api.scryfall.com/cards/collection"
SCRYFALL_NAMED_URL = "https://api.scryfall.com/cards/named"
SCRYFALL_SYMBOLOGY_URL = "https://api.scryfall.com/symbology"
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
# A format with fewer cards than this resolved to Scryfall data is not
# published - the previous pack is carried forward instead.
EXPORT_MIN_CARDS = 45
# Meta older than this is flagged stale in the manifest
EXPORT_STALE_AFTER = 2 * _DAY

# Database
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get("META_MORPHIS_DB") or PROJECT_ROOT / "data" / "cards.db")

# Web app data: one <format>.json per format, read by the app
EXPORT_DIR = PROJECT_ROOT / "web" / "public" / "data"
EXPORT_FORMATS = ["pauper"]
