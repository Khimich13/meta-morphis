from dataclasses import dataclass


@dataclass
class CardFace:
    name: str
    mana_cost: str | None
    type_line: str

    def __str__(self) -> str:
        return (
            f"Face Name: {self.name}\n"
            f"Type Line: {self.type_line}\n"
            f"Mana Cost: {self.mana_cost}\n"
        )