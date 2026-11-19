"""Reads the picture of every card that may have its name in its text box,
not only the cards on a format's list, so every card added to a player's
own list can be asked by its full picture with the name covered.

The export reads only the cards on the lists: reading every card takes
an hour or more, too long for the daily run. So this is run by hand, and
name_in_text.json committed afterwards. Run it with:

    uv run python -m meta_morphis.read_every_picture

The sides already read are skipped, and name_in_text.json is saved every
SAVE_EVERY seconds and on Ctrl+C, so it can be stopped and started again
at any time. Tesseract's words are saved in WORDS_DIR as each picture is
read, so even the last minute before a crash is read again quickly.
"""

import argparse
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from meta_morphis import config
from meta_morphis.export import build_card, is_basic_land, load_name_in_text, write_json
from meta_morphis.models.card import Card
from meta_morphis.name_in_text import NameInText, fetch_game_words, saved_key
from meta_morphis.scryfall.bulk import read_every_card
from meta_morphis.utils.text import card_count

log = logging.getLogger(__name__)

# How often name_in_text.json is saved while reading, in seconds
SAVE_EVERY = 60
# How often the progress is logged, in sides read
LOG_EVERY = 100


def sides_to_read(cards: list[Card]) -> dict[str, Card]:
    """Every side the export may read for its name in the text box, as
    the export builds each card, by saved_key: a double-faced card's
    sides and an adventure's spell each count by themselves"""
    sides: dict[str, Card] = {}

    def record(card: Card) -> None:
        sides.setdefault(saved_key(card), card)

    for card in cards:
        if not is_basic_land(card):
            build_card(card, record)
    return sides


def save(read_text: NameInText) -> None:
    # A copy: the reading threads add to the results meanwhile, and a
    # dict's copy is taken in one step
    results = read_text.results.copy()
    write_json(config.NAME_IN_TEXT_PATH, dict(sorted(results.items())))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    # One Tesseract a core: on 12 cores, 12 at a time read every card in
    # about 2 hours, 8 at a time in nearly 3
    workers = os.cpu_count() or 8
    parser.add_argument(
        "--workers",
        type=int,
        default=workers,
        help=f"pictures read at a time ({workers}, the number of cores)",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # Tesseract runs on several threads by itself: with many at a time they
    # crowd each other out, and one ran past its 60 s limit on 2026-11-18
    os.environ["OMP_THREAD_LIMIT"] = "1"

    read_text = NameInText(
        load_name_in_text(config.NAME_IN_TEXT_PATH),
        fetch_game_words(),
        config.WORDS_DIR,
    )
    if read_text.why_not_read:
        log.error(f"Can't read any picture: {read_text.why_not_read}")
        return 1
    log.info(f"Reading Scryfall's card data in {config.BULK_PATH}")
    sides = sides_to_read(list(read_every_card(config.BULK_PATH).values()))
    to_read = [card for _, card in sorted(sides.items()) if not read_text.is_read(card)]
    log.info(
        f"{len(sides)} sides may have their name in the text box, "
        f"{len(to_read)} not read yet: reading them {args.workers} at a time"
    )

    started = saved_at = time.monotonic()
    pool = ThreadPoolExecutor(args.workers)
    try:
        futures = [pool.submit(read_text, card) for card in to_read]
        for done, future in enumerate(as_completed(futures), 1):
            future.result()
            now = time.monotonic()
            if done % LOG_EVERY == 0 or done == len(to_read):
                per_side = (now - started) / done
                left = (len(to_read) - done) * per_side / 60
                log.info(
                    f"{done}/{len(to_read)} read in {(now - started) / 60:.0f} min, "
                    f"about {left:.0f} min left"
                )
            if now - saved_at >= SAVE_EVERY:
                save(read_text)
                saved_at = now
    except KeyboardInterrupt:
        log.info("Stopping: finishing the pictures being read, then saving")
    finally:
        # Leaves out the sides not started: the next run reads them
        pool.shutdown(wait=True, cancel_futures=True)
        save(read_text)
        log.info(f"Saved {config.NAME_IN_TEXT_PATH}")

    log.info(
        f"Left out, asked only by their artwork: {card_count(len(read_text.left_out))}"
    )
    if read_text.not_read:
        log.info(
            f"Not read, tried again on the next run: {card_count(len(read_text.not_read))}"
        )
        for name, why in sorted(read_text.not_read.values()):
            log.info(f"- {name}: {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
