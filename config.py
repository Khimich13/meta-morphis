#MTGGoldfish configs
META_REFRESH_RATE = 24 * 60 * 60 # 24 hours
FORMATS = {
    "pauper": "https://www.mtggoldfish.com/format-staples/pauper/full/spells",
    "premodern": "https://www.mtggoldfish.com/format-staples/premodern/full/all",
    "pioneer": "https://www.mtggoldfish.com/format-staples/pioneer/full/all",
    "standard": "https://www.mtggoldfish.com/format-staples/standard/full/all",
    "modern": "https://www.mtggoldfish.com/format-staples/modern/full/all"
}
#ScryFall API configs
URL_COLLECTION = "https://api.scryfall.com/cards/collection"
URL_NAMED = "https://api.scryfall.com/cards/named"
SCRYFALL_REFRESH_RATE = 24 * 60 * 60 * 30 # 30 days
SCRYFALL_BATCH_SIZE_LIMIT = 75
HEADERS = {
        "User-Agent": "meta-morphis",
        "Accept": "application/json"
    }
#DB
DB_PATH = "data/cards.db"