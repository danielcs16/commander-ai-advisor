from models.card import CardData
from services.deck_validator import DeckValidator


def card(name, identity=(), legal=True, quantity=1, type_line="Instant", text=None):
    return CardData(
        name=name,
        quantity=quantity,
        color_identity=list(identity),
        commander_legal=legal,
        type_line=type_line,
        oracle_text=text,
    )


def test_reports_color_identity_and_illegal_card():
    commander = card("Commander", ("G",), type_line="Legendary Creature")
    report = DeckValidator().validate(
        [commander, card("Off-color", ("U",)), card("Banned", legal=False)], [commander]
    )

    assert any("outside the Commander color identity" in error for error in report.errors)
    assert any("Banned is not legal" in error for error in report.errors)


def test_reports_size_and_duplicates():
    commander = card("Commander", type_line="Legendary Creature")
    report = DeckValidator().validate(
        [commander, card("Sol Ring", quantity=2, type_line="Artifact")], [commander]
    )

    assert report.deck_size == 3
    assert any("100" in warning for warning in report.warnings)
    assert any("Duplicate copies" in error for error in report.errors)


def test_basic_lands_may_be_repeated():
    report = DeckValidator().validate(
        [card("Island", quantity=30, type_line="Basic Land — Island")],
        [card("Commander", type_line="Legendary Creature")],
    )

    assert not any("Duplicate copies" in error for error in report.errors)