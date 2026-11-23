import logging
import sqlite3
from pathlib import Path

from meta_morphis import config
from meta_morphis.models.meta import MetaEntry
from meta_morphis.scryfall.bulk import read_edhrec_ranks

from .decklists import DeckCount, count_meta_cards
from .repo import (
    get_meta_from_cache,
    save_meta_to_cache,
    should_refresh_meta,
    update_meta_timestamp,
)

log = logging.getLogger(__name__)


def get_meta_cards(
    conn: sqlite3.Connection, format_name: str, bulk_path: Path = config.BULK_PATH
) -> list[MetaEntry]:
    """Every card played in the format's decks, most played first - see
    count_meta_cards - or for EDHREC_FORMATS the cards EDHREC ranks
    highest, from Scryfall's card data at `bulk_path` - see
    read_edhrec_ranks. It is saved in the database under the format's
    name, with the day of its newest decks, and counted again after
    META_REFRESH_RATE; a run that can't count the decks uses the last
    count instead.
    """
    # Validated before the cache check, so an unknown format always fails
    # the same way - otherwise a leftover cache row for it would be served
    # silently, and no row would mean an empty count
    if format_name not in config.FORMATS:
        known = ", ".join(config.FORMATS)
        raise ValueError(f"Unknown format {format_name!r}, expected one of: {known}")

    if not should_refresh_meta(conn, format_name):
        log.info(f"Using the {format_name} decks counted earlier")
        return get_meta_from_cache(conn, format_name)

    if format_name in config.EDHREC_FORMATS:
        # With no day of its newest decks: Scryfall doesn't say how
        # recent EDHREC's rank is
        ranked = read_edhrec_ranks(bulk_path, format_name, config.EDHREC_RANKED_CARDS)
        count: DeckCount | None = DeckCount(ranked, None)
    else:
        count = count_meta_cards(format_name)
    if count is None or not count.cards:
        # Why was logged by count_meta_cards or read_edhrec_ranks
        log.warning(f"Could not count the {format_name} decks")
        cached = get_meta_from_cache(conn, format_name)
        if cached:
            log.warning("Using the last count instead")
            return cached
        raise RuntimeError(f"The {format_name} decks were never counted")

    with conn:
        save_meta_to_cache(conn, count.cards, format_name)
        update_meta_timestamp(conn, format_name, count.decks_to)
    return count.cards
