from meta_morphis.utils.text import normalize_name


def test_normalize_removes_accents() -> None:
    assert normalize_name("Bösium Strip") == "bosium strip"
    assert normalize_name("Jötun Grunt") == "jotun grunt"

def test_normalize_expand_ligature() -> None:
    assert normalize_name("Æther Spellbomb") == "aether spellbomb"
    assert normalize_name("Gate to the Æther") == "gate to the aether"

def test_normalize_lowercases() -> None:
    assert normalize_name("Shock") == "shock"
    assert normalize_name("SHOCK") == "shock"

def test_normalize_strips_whitespace() -> None:
    assert normalize_name("  Lightning Bolt ") == "lightning bolt"

def test_normalize_unicode_nfkd() -> None:
    assert normalize_name("ÁÉÍÓÚ") == "aeiou"

def test_normalize_preserves_nonaccent_unicode() -> None:
    assert normalize_name("—") == "—"
    assert normalize_name("_") == "_"

def test_normalize_empty_and_numeric() -> None:
    assert normalize_name("") == ""
    assert normalize_name("   ") == ""
    assert normalize_name("123") == "123"