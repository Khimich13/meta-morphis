"""Chooses which printing of a card the app shows: the newest printing of
the artwork that appears on the most printings - the art a player has
most likely seen.
"""
from typing import Any


def choose_printing(printings: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Group the printings by artwork, take the artwork printed most often -
    the older one when two are printed equally often, since it has been in
    players' hands longer - and return the newest printing of it, which is
    usually the best scan, passing over one whose artwork is cut wrong
    while the artwork has another. None if no printing has the pictures
    to show.
    """
    by_artwork: dict[str, list[dict[str, Any]]] = {}
    for printing in printings:
        if not is_regular_printing(printing):
            continue
        artwork = _illustration_id(printing)
        if artwork is None or not _has_pictures(printing):
            continue
        by_artwork.setdefault(artwork, []).append(printing)

    if not by_artwork:
        return None

    most_printed = min(
        by_artwork.values(),
        key=lambda group: (-len(group), min(_released(p) for p in group)),
    )
    well_cut = [p for p in most_printed if not _art_cut_for_modern_frame(p)]
    return max(well_cut or most_printed, key=_released)

def is_regular_printing(printing: dict[str, Any]) -> bool:
    """The same rules as SCRYFALL_REGULAR_PRINTINGS in config.py, checked
    on the printing's own data. Scryfall can silently drop filters from a
    long query, so the search results are not trusted to follow them.
    """
    effects = printing.get("frame_effects") or []
    return (
        "paper" in (printing.get("games") or [])
        and printing.get("lang") == "en"
        and not printing.get("promo")
        and not printing.get("digital")
        and printing.get("border_color") not in ("gold", "borderless")
        and not printing.get("oversized")
        and printing.get("set_type") != "memorabilia"
        and printing.get("frame") != "future"
        and "showcase" not in effects
        and "extendedart" not in effects
        and not printing.get("full_art")
    )

# The timeshifted sets, which reprint in the old frame artwork first
# printed in a modern frame. Scryfall cut the artwork of most of these
# printings with the modern frame's rectangle: the cut has strips of the
# frame at the sides, leaves off the art's top, and doesn't match the
# app's art box for the old frame. Measured on 2026-11-12 by the shape of
# every one of them: 94 of 122 in tsr, 25 of 40 in h1r, 1 of 16 in h2r.
# No field tells which, so all of them give way to another printing of
# the artwork, which players have also seen in its own frame.
ART_CUT_FOR_MODERN_FRAME_SETS = {"tsr", "h1r", "h2r"}

def _art_cut_for_modern_frame(printing: dict[str, Any]) -> bool:
    return (
        printing.get("frame") == "1997"
        and printing.get("set") in ART_CUT_FOR_MODERN_FRAME_SETS
    )

def _illustration_id(printing: dict[str, Any]) -> str | None:
    # A double-faced card has an artwork per face; the front's is the
    # one the quiz shows
    if "illustration_id" in printing:
        value: str = printing["illustration_id"]
        return value
    faces = printing.get("card_faces") or []
    if faces and "illustration_id" in faces[0]:
        front: str = faces[0]["illustration_id"]
        return front
    return None

def _has_pictures(printing: dict[str, Any]) -> bool:
    if "image_uris" in printing:
        return True
    faces = printing.get("card_faces") or []
    return bool(faces) and all("image_uris" in face for face in faces)

def _released(printing: dict[str, Any]) -> str:
    # YYYY-MM-DD, so comparing the text compares the dates
    value: str = printing.get("released_at", "")
    return value
