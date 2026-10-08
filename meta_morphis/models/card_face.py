from dataclasses import dataclass, field
from typing import Any


@dataclass
class CardFace:
    name: str
    mana_cost: str | None
    type_line: str
    oracle_text: str = ""
    colors: list[str] = field(default_factory=list)
    power: str | None = None
    toughness: str | None = None
    loyalty: str | None = None
    defense: str | None = None
    artist: str | None = None
    image_uris: dict[str, str] | None = None

    @classmethod
    def from_raw(cls, face: dict[str, Any], card: dict[str, Any]) -> "CardFace":
        """Build a face from a Scryfall face object (or, for a single-faced
        card, the card object itself). `card` is the whole card object:
        some fields - artist, colors - may only be set at card level, and
        a face falls back to them when it doesn't carry its own.
        Raises KeyError if `name` or `type_line` is missing.
        """
        return cls(
            name=face["name"],
            mana_cost=face.get("mana_cost") or None,
            type_line=face["type_line"],
            oracle_text=face.get("oracle_text") or "",
            colors=face["colors"] if "colors" in face else card.get("colors") or [],
            power=face.get("power"),
            toughness=face.get("toughness"),
            loyalty=face.get("loyalty"),
            defense=face.get("defense"),
            artist=face.get("artist") or card.get("artist"),
            image_uris=face.get("image_uris"),
        )

    def __str__(self) -> str:
        return (
            f"Face Name: {self.name}\n"
            f"Type Line: {self.type_line}\n"
            f"Mana Cost: {self.mana_cost}\n"
        )
