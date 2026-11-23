import io
from typing import Any

from PIL import Image, ImageDraw

from meta_morphis.models.card import Card
from meta_morphis.set_symbols import symbol_left, symbol_set


def _card(**raw: Any) -> Card:
    return Card.from_raw({"id": "id", "name": "Card", **raw})


def test_a_card_shows_its_own_sets_symbol() -> None:
    assert symbol_set(_card(set="mh3", collector_number="12")) == "mh3"


def test_a_card_of_the_list_shows_the_set_it_was_first_printed_in() -> None:
    assert symbol_set(_card(set="plst", collector_number="XLN-217")) == "xln"


def _type_line(*strokes: tuple[int, int]) -> bytes:
    """A modern frame's type line, 488 by 680: a light bar with print
    from and to the columns given, drawn as thin upright strokes - print
    is all edges"""
    image = Image.new("L", (488, 680), 200)
    draw = ImageDraw.Draw(image)
    for start, end in strokes:
        for x in range(start, end, 4):
            draw.rectangle([x, 392, x + 1, 410], fill=20)
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def test_the_symbol_starts_where_its_print_does() -> None:
    assert symbol_left(_type_line((40, 200), (420, 450))) == round(420 / 488, 4)


def test_a_gap_inside_a_symbol_is_crossed() -> None:
    # Two pieces 10 columns apart, as Eternal Weekend's axe
    assert symbol_left(_type_line((40, 200), (390, 410), (420, 450))) == round(
        390 / 488, 4
    )


def test_no_symbol_is_found_where_none_is_clearly_apart() -> None:
    # Nothing at the bar's right end
    assert symbol_left(_type_line((40, 200))) is None
    # Text running up to the symbol: either may be taken for the other
    assert symbol_left(_type_line((40, 412), (420, 450))) is None
