"""Where each set's symbol starts on a card's type line, for the question
about a creature's types: the cover over the type line stops a few
pixels before it, so the symbol stays in sight.

A set's symbol is the same on every card of it, and starts at the same
place on the type line, within a pixel or two from one scan to the next.
So it is measured once per set, on the picture of one of its cards, and
the result kept in SET_SYMBOLS_PATH (see config.py). A long type line
never runs into the symbol: the card squeezes it to fit before it.

Measured on 2026-11-22 on the 169 sets of every creature in the modern
frame then: 165 measured, the other 4 only with long lines to measure on.
Only the modern frame is measured: see CREATURE_TYPE_LINES in export.py.
"""

import io
from collections.abc import Mapping

from PIL import Image

from meta_morphis.models.card import Card

# Where each set's symbol starts on the type line, as a share of the
# card's width, by symbol_set: None for a set that couldn't be measured
SetSymbols = Mapping[str, float | None]

# The type line's rows in the modern frame, as shares of the card's
# height: the symbol is looked for in these
BAND_TOP = 0.569
BAND_HEIGHT = 0.043
# Where the search starts, a little inside the bar's right end: a symbol
# ends at about 0.924 of the card's width
START = 0.925
# A column has ink where at least INK_ROWS of its rows differ in
# brightness by more than INK_STEP from the column to their left: the
# edges of a symbol or a letter, not the bar's grain. One row lets the
# grain in: some sets' symbols then measured up to 29 pixels too wide.
INK_STEP = 40
INK_ROWS = 2
# A gap of this many clean columns ends the symbol; a narrower one is
# inside it: the pieces of some symbols are apart (Eternal Weekend's
# axe, the Marvel "M" plate)
INSIDE_GAP = 12
# On the card measured, at least this many clean columns between the
# symbol and the text before it, so the text isn't taken for part of the
# symbol: a card with a short type line is measured
TEXT_AWAY = 20
# A symbol ends at least this far right, as a share of the card's width
RIGHT_AT_LEAST = 0.89
# And is between this many pixels and this share of the card's width
# wide: M20's plate, the widest, is 62 pixels of the 488
NARROWEST = 8
WIDEST = 0.16


def symbol_set(card: Card) -> str:
    """The set whose symbol the card's picture shows: its own, but for a
    card of The List, the set it was first printed in, as its collector
    number says ("XLN-217")"""
    code = str(card.raw.get("set") or "")
    if code == "plst":
        return str(card.raw.get("collector_number") or "").split("-")[0].lower()
    return code


def symbol_left(picture: bytes) -> float | None:
    """Where the set symbol starts on the type line of a modern-frame
    card's picture, as a share of its width: from START, leftward, to the
    symbol's ink, and on through it until a gap of INSIDE_GAP.
    None when the symbol isn't found clearly: nothing at the bar's right
    end, a symbol too narrow or too wide, or text closer than TEXT_AWAY."""
    image = Image.open(io.BytesIO(picture)).convert("L")
    width, height = image.size
    gray = image.tobytes()
    top, bottom = round(BAND_TOP * height), round((BAND_TOP + BAND_HEIGHT) * height)

    def ink(x: int) -> bool:
        rows = range(top * width + x, bottom * width + x, width)
        steps = sum(1 for at in rows if abs(gray[at] - gray[at - 1]) > INK_STEP)
        return steps >= INK_ROWS

    lowest = round(0.3 * width)
    x = round(START * width)
    while x > lowest and not ink(x):
        x -= 1
    right = x
    if right < RIGHT_AT_LEAST * width:
        return None
    left, gap = x, 0
    while x > lowest:
        if ink(x):
            left, gap = x, 0
        else:
            gap += 1
            if gap >= INSIDE_GAP:
                break
        x -= 1
    # The text before it
    x = left - 1
    while x > lowest and not ink(x):
        x -= 1
    if left - x - 1 < TEXT_AWAY:
        return None
    if not NARROWEST <= right - left + 1 <= WIDEST * width:
        return None
    return round(left / width, 4)
