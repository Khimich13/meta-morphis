import os
from pathlib import Path

DAY = 24 * 60 * 60

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
    list_name(
        format_name, kind
    ): f"https://www.mtggoldfish.com/format-staples/{format_name}/full/{kind}"
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

# Magic Online's decklists, from fbettega's archive on GitHub - see
# meta/decklists.py. Its files are listed through GitHub's API, which
# allows 60 calls an hour without a login and 1,000 with the workflow's
# GITHUB_TOKEN, and downloaded from raw.githubusercontent.com, which
# doesn't count against that limit.
DECKLISTS_API_URL = "https://api.github.com/repos/fbettega/MTG_decklistcache/"
DECKLISTS_RAW_URL = "https://raw.githubusercontent.com/fbettega/MTG_decklistcache/main/"
# The archive's folder of MTGO events: <yyyy>/<mm>/<dd>/<format>-....json
DECKLISTS_FOLDER = "Tournaments/MTGO"
# How many days of events are counted, today included
DECKLISTS_DAYS = 30
DECKLISTS_HEADERS = {
    "User-Agent": "meta-morphis (https://github.com/Khimich13/meta-morphis)",
    "Accept": "application/vnd.github+json",
}

# Scryfall
# Scryfall's file of every printing, one card per line - see
# scryfall/bulk.py. This address says where today's file is; the file
# itself comes from data.scryfall.io, which has no rate limit.
SCRYFALL_BULK_DATA_URL = "https://api.scryfall.com/bulk-data/default-cards"
SCRYFALL_SYMBOLOGY_URL = "https://api.scryfall.com/symbology"
SCRYFALL_CATALOG_URL = "https://api.scryfall.com/catalog/"
# The subtypes printed on type lines, which a card's text uses as plain
# game words: "a Goblin card". Planeswalker types are left out: they are
# people's names, like "Jace".
SCRYFALL_SUBTYPE_CATALOGS = [
    "creature-types",
    "land-types",
    "artifact-types",
    "enchantment-types",
    "spell-types",
    "battle-types",
]
SCRYFALL_HEADERS = {
    "User-Agent": "meta-morphis/0.1.0 (+https://github.com/Khimich13/meta-morphis)",
    "Accept": "application/json",
}
# For downloading files that are not JSON: card pictures and the card data
SCRYFALL_FILE_HEADERS = {"User-Agent": SCRYFALL_HEADERS["User-Agent"]}
# Scryfall's API allows 2 requests a second, and a 429 locks the client
# out for 30 seconds (https://scryfall.com/docs/api/rate-limits)
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

# The same for the files of every card (see export_every_card): today's
# Scryfall data gives 32,441 cards less basic lands, so fewer than this
# means its data or the export broke
EXPORT_MIN_EVERY_CARD = 30_000


def min_cards(kind: str) -> int:
    """The fewest cards a list of this kind needs to be exported. A list
    scraped with fewer isn't saved either, so it can't replace a good
    one - see meta/service.py.
    """
    return EXPORT_MIN_LANDS if kind == "lands" else EXPORT_MIN_CARDS


# An MTGGoldfish list older than this makes the export fail, so a lasting
# breakage of the scraper fails the daily run and GitHub reports it,
# instead of the old list being published day after day. A short outage
# still publishes the slightly older list. Keep in step with
# LIST_OLD_AFTER_DAYS in web/src/lib/cards.ts, which shows a banner.
EXPORT_STALE_AFTER = 3 * DAY

# Scryfall's card data older than this makes the run fail after the
# export, so GitHub reports a download that has failed for a week. The
# export still uses the old file: cards change little in a week.
SCRYFALL_STALE_AFTER = 7 * DAY

# Database
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get("META_MORPHIS_DB") or PROJECT_ROOT / "data" / "cards.db")

# The last downloaded copy of Scryfall's card data, next to the database,
# so the daily run keeps it between runs too
BULK_PATH = PROJECT_ROOT / "data" / "default-cards.jsonl.gz"

# The downloaded decklists of the last DECKLISTS_DAYS days, in the
# archive's <yyyy>/<mm>/<dd> folders, kept between runs like the above
DECKLISTS_DIR = PROJECT_ROOT / "data" / "decklists"

# Where each printing's name was found in its text box, read from its
# picture - see name_in_text.py. Kept in git, unlike the database: the
# first reading of every card takes hours, and the daily run reads only
# printings missing from it.
NAME_IN_TEXT_PATH = PROJECT_ROOT / "meta_morphis" / "name_in_text.json"

# How long the export reads the pictures of cards on no list that
# read_every_picture.py hasn't read, a new set's mostly, in seconds: a
# set's few hundred take minutes, and thousands, after READER_VERSION
# was raised without reading every card again, can't hold up the run
NEW_PICTURES_TIME_LIMIT = 15 * 60

# Tesseract's words on each picture read for its name, one file per
# picture - see name_in_text.Picture. Not in git: about 4.4 KB a picture,
# some 90 MB for every card, and rebuilt by reading the pictures again.
WORDS_DIR = PROJECT_ROOT / "data" / "words"

# Web app data: one <format>.json per format, read by the app, and
# formats.json listing the formats that have one
EXPORT_DIR = PROJECT_ROOT / "web" / "public" / "data"
# Every card, in EXPORT_DIR: index.json and one file per first two
# characters of the oracle id - see export_every_card
EVERY_CARD_DIR = "cards"
