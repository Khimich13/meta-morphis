from typing import Any

from meta_morphis.scryfall.artwork import choose_printing, is_regular_printing


def _printing(set_code: str, released: str, artwork: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": f"id-{set_code}",
        "set": set_code,
        "released_at": released,
        "illustration_id": artwork,
        "games": ["paper"],
        "image_uris": {"grid": f"{set_code}.webp", "art": f"{set_code}-art.webp"},
        **extra,
    }

def _chosen_set(printings: list[dict[str, Any]]) -> str | None:
    chosen = choose_printing(printings)
    return None if chosen is None else chosen["set"]

def test_picks_the_artwork_on_the_most_printings() -> None:
    printings = [
        _printing("lea", "1993-08-05", "rush"),
        _printing("m10", "2009-07-17", "moeller"),
        _printing("m11", "2010-07-16", "moeller"),
        _printing("2xm", "2020-08-07", "moeller"),
    ]
    # Moeller's art is on three printings; the newest of them is shown
    assert _chosen_set(printings) == "2xm"

def test_a_tie_goes_to_the_older_artwork() -> None:
    printings = [
        _printing("zen", "2009-10-30", "argyle"),
        _printing("gvl", "2014-12-05", "argyle"),
        _printing("who", "2023-10-13", "fedyczak"),
        _printing("who2", "2023-10-14", "fedyczak"),
    ]
    assert _chosen_set(printings) == "gvl"

def test_order_of_the_input_does_not_matter() -> None:
    printings = [
        _printing("2xm", "2020-08-07", "moeller"),
        _printing("lea", "1993-08-05", "rush"),
        _printing("m10", "2009-07-17", "moeller"),
    ]
    assert _chosen_set(printings) == "2xm"
    assert _chosen_set(list(reversed(printings))) == "2xm"

def test_printings_without_pictures_are_ignored() -> None:
    no_pictures = _printing("new", "2026-01-01", "moeller")
    del no_pictures["image_uris"]
    printings = [
        _printing("m10", "2009-07-17", "moeller"),
        no_pictures,
        _printing("lea", "1993-08-05", "rush"),
    ]
    # Moeller now has one printing with pictures, tied with Rush, and
    # Rush's art is older
    assert _chosen_set(printings) == "lea"

def test_double_faced_cards_are_grouped_by_the_front_artwork() -> None:
    def double_faced(set_code: str, released: str, front: str) -> dict[str, Any]:
        return {
            "id": f"id-{set_code}",
            "set": set_code,
            "released_at": released,
            "games": ["paper"],
            "card_faces": [
                {"illustration_id": front, "image_uris": {"grid": "front.webp"}},
                {"illustration_id": "back", "image_uris": {"grid": "back.webp"}},
            ],
        }

    printings = [
        double_faced("neo", "2022-02-18", "meehan"),
        double_faced("2x2", "2022-07-08", "meehan"),
        double_faced("sld", "2023-01-01", "other"),
    ]
    assert _chosen_set(printings) == "2x2"

def test_nothing_to_choose_from() -> None:
    assert choose_printing([]) is None
    no_artwork = _printing("x", "2020-01-01", "a")
    del no_artwork["illustration_id"]
    assert choose_printing([no_artwork]) is None

def test_regular_printing_rules() -> None:
    regular = _printing("m10", "2009-07-17", "moeller")
    assert is_regular_printing(regular)
    specials: list[dict[str, Any]] = [
        {"games": ["mtgo"]},
        {"promo": True},
        {"digital": True},
        {"border_color": "gold"},
        {"border_color": "borderless"},
        {"oversized": True},
        {"set_type": "memorabilia"},
        {"frame": "future"},
        {"frame_effects": ["showcase"]},
        {"frame_effects": ["legendary", "extendedart"]},
        {"full_art": True},
    ]
    for special in specials:
        assert not is_regular_printing({**regular, **special}), special

# Scryfall can silently drop filters from a long query, so special
# printings may come back: they must not decide the artwork
def test_special_printings_that_slip_through_are_ignored() -> None:
    printings = [
        _printing("m10", "2009-07-17", "moeller"),
        _printing("olep", "1998-10-23", "foglio", oversized=True),
        _printing("olep2", "1998-10-23", "foglio", oversized=True),
        _printing("mb2", "2024-08-02", "meehan", frame="future"),
    ]
    assert _chosen_set(printings) == "m10"
