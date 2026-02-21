from snrd_kg.normalize import normalize_text


def test_normalize_text_basic():
    assert normalize_text("Árbol   de   la Vida ") == "arbol de la vida"
