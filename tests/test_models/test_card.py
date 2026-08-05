from meta_morphis.models.card import Card
from meta_morphis.models.card_face import CardFace

def test_card_creation():
    face = CardFace("Test", None, "Creature")
    card = Card("123", "Test Card", 0, "Creature", [face])
    assert card.id == "123"
    assert card.faces[0].name == "Test"
