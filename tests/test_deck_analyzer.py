from models.card import CardData
from services.deck_analyzer import DeckAnalyzer


def test_calculates_deck_metrics_and_categories():
    cards = [
        CardData(name="Island", quantity=10, type_line="Basic Land — Island", colors=["U"]),
        CardData(
            name="Signet",
            mana_value=2,
            type_line="Artifact",
            oracle_text="{T}: Add {U} or {R}.",
            colors=["U", "R"],
        ),
        CardData(name="Counterspell", mana_value=2, type_line="Instant", oracle_text="Counter target spell."),
        CardData(name="Fact or Fiction", mana_value=4, type_line="Instant", oracle_text="Draw a card."),
    ]

    stats = DeckAnalyzer().analyze(cards)

    assert stats.total_cards == 13
    assert stats.lands == 10
    assert stats.nonlands == 3
    assert stats.average_mana_value == 2.67
    assert stats.mana_curve == {"2": 2, "4": 1}
    assert stats.categories["Counterspell"] == ["Counterspell"]
    assert stats.categories["Mana Rock"] == ["Signet"]
    assert stats.categories["Card Draw"] == ["Fact or Fiction"]