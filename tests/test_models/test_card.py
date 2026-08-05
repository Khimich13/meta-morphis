from meta_morphis.models.card import Card

def test_single_face_card():
    raw = {
        "id": "123",
        "name": "Test Card",
        "mana_cost": "{1}{G}",
        "type_line": "Creature",
    }
    card = Card.from_raw(raw)
    assert card.mana_cost == "{1}{G}"
    assert card.faces == []

def test_dual_face_card():
    raw = {
        "id": "123",
        "name": "Split Card",
        "card_faces": [
            {"name": "Face A", "mana_cost": "{R}", "type_line": "Instant"},
            {"name": "Face B", "mana_cost": "{G}", "type_line": "Sorcery"},
        ]
    }
    card = Card.from_raw(raw)
    assert len(card.faces) == 2
    assert card.mana_cost == raw["card_faces"][0]["mana_cost"]

def test_missing_mana_cost():
    raw = {
        "id": "123",
        "name": "Test",
        "type_line": "Creature",
    }
    card = Card.from_raw(raw)
    assert card.mana_cost is None
