from dataclasses import dataclass, field
from typing import Any

from meta_morphis.models.card_face import CardFace


@dataclass
class ImageSide:
    """One physical side of a card that has its own picture: two for a
    transform or modal double-faced card, one for everything else -
    a split or adventure card is two faces printed on a single side.
    """
    image_uris: dict[str, str]
    artist: str | None


@dataclass
class Card:
    id: str
    name: str
    mana_cost: str | None
    type_line: str
    faces: list[CardFace]
    age: int
    raw: dict[str, Any]
    oracle_id: str | None = None
    layout: str = "normal"
    cmc: float | None = None
    color_identity: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    scryfall_uri: str | None = None
    image_uris: dict[str, str] | None = None
    # The card's own gameplay fields as a face, for a card without
    # `card_faces` - lets gameplay_faces() treat every layout the same.
    single_face: CardFace | None = None

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "Card":
        faces: list[CardFace] = []

        # Build CardFace objects if present
        if "card_faces" in raw:
            for face in raw["card_faces"]:
                faces.append(CardFace.from_raw(face, raw))

        # Determine mana_cost
        if faces:
            mana_cost = faces[0].mana_cost
        else:
            mana_cost = raw.get("mana_cost")

        single_face = None
        if not faces:
            single_face = CardFace.from_raw(
                {**raw, "type_line": raw.get("type_line", "")}, raw
            )

        return cls(
            id=raw["id"],
            name=raw["name"],
            mana_cost=mana_cost,
            type_line=raw.get("type_line", ""),
            faces=faces,
            age=0,
            raw=raw,
            oracle_id=raw.get("oracle_id"),
            layout=raw.get("layout") or "normal",
            cmc=raw.get("cmc"),
            color_identity=raw.get("color_identity") or [],
            keywords=raw.get("keywords") or [],
            scryfall_uri=raw.get("scryfall_uri"),
            image_uris=raw.get("image_uris"),
            single_face=single_face,
        )

    def gameplay_faces(self) -> list[CardFace]:
        """Every face a player can cast or read: the card itself when it
        has a single face, otherwise each of `card_faces` in print order.
        """
        if self.faces:
            return self.faces
        return [self.single_face] if self.single_face else []

    def image_sides(self) -> list[ImageSide]:
        # Transform and modal DFCs carry images per face and none at the
        # top level; split, adventure and flip cards are the reverse.
        sides = [
            ImageSide(face.image_uris, face.artist)
            for face in self.faces
            if face.image_uris
        ]
        if sides:
            return sides
        if self.image_uris:
            # Faces already fall back to the card-level artist
            faces = self.gameplay_faces()
            artist = faces[0].artist if faces else None
            return [ImageSide(self.image_uris, artist)]
        return []

    def __str__(self) -> str:
        output = (
            f"Name: {self.name}\n"
            f"Type Line: {self.type_line}\n"
            f"Mana Cost: {self.mana_cost}\n"
        )
        for face in self.faces:
            output += f"{face}"

        return output
