from models.analysis import CandidateCard, CardChange, DeckAnalysis
from models.card import CardData
from services.recommendation_validator import RecommendationValidator


class FakeScryfall:
    def __init__(self, cards):
        self.cards = cards

    def get_cards_by_names(self, names):
        return {name.casefold(): self.cards.get(name.casefold()) for name in names}


def test_valid_recommendation_is_accepted():
    commander = CardData(name="Commander", color_identity=["G"], commander_legal=True)
    deck = [CardData(name="Slow Card", commander_legal=True), commander]
    cards = {
        "slow card": CardData(name="Slow Card", commander_legal=True),
        "good card": CardData(name="Good Card", color_identity=["G"], commander_legal=True),
    }
    analysis = DeckAnalysis(
        commanders=["Commander"], target_bracket=2, final_summary="summary",
        changes=[CardChange(remove="Slow Card", add="Good Card", reason="Fits plan.", category="Ramp", priority="High", change_type="Upgrade", edhrec_synergy=99.0)],
    )

    candidate = CandidateCard(name="Good Card", card_data={}, edhrec_synergy=0.56)
    result, rejected = RecommendationValidator(FakeScryfall(cards)).validate(analysis, deck, [commander], [candidate])

    assert len(result.changes) == 1
    assert result.changes[0].edhrec_synergy == 0.56
    assert rejected == []


def test_rejects_missing_and_invalid_color_candidate():
    commander = CardData(name="Commander", color_identity=["G"], commander_legal=True)
    deck = [CardData(name="Slow Card"), commander]
    cards = {
        "slow card": CardData(name="Slow Card", commander_legal=True),
        "blue card": CardData(name="Blue Card", color_identity=["U"], commander_legal=True),
        "missing": None,
    }
    changes = [
        CardChange(remove="Slow Card", add="Blue Card", reason="x", category="x", priority="Low", change_type="Upgrade"),
        CardChange(remove="Slow Card", add="Missing", reason="x", category="x", priority="Low", change_type="Upgrade"),
    ]
    analysis = DeckAnalysis(commanders=["Commander"], target_bracket=2, final_summary="summary", changes=changes)

    result, rejected = RecommendationValidator(FakeScryfall(cards)).validate(analysis, deck, [commander], ["Blue Card", "Missing"])

    assert result.changes == []
    assert len(rejected) == 2
    assert any("color identity" in item.reason for item in rejected)
    assert any("could not be found" in item.reason for item in rejected)


def test_rejects_addition_already_in_deck_before_candidate_membership():
    commander = CardData(name="Commander", color_identity=["W"], commander_legal=True)
    deck = [
        CardData(name="Slow Card", commander_legal=True),
        CardData(name="Marionette Master", commander_legal=True),
        commander,
    ]
    cards = {
        "slow card": deck[0],
        "marionette master": deck[1],
    }
    analysis = DeckAnalysis(
        commanders=["Commander"],
        target_bracket=2,
        final_summary="summary",
        changes=[CardChange(
            remove="Slow Card",
            add="Marionette Master",
            reason="Already present.",
            category="Value",
            priority="Low",
            change_type="Optimization",
        )],
    )

    result, rejected = RecommendationValidator(FakeScryfall(cards)).validate(
        analysis, deck, [commander], []
    )

    assert result.changes == []
    assert rejected[0].reason == "The addition is already present in the deck."


def test_rejects_replacing_a_card_with_itself():
    commander = CardData(name="Commander", color_identity=["W"], commander_legal=True)
    wayfarer = CardData(name="Weathered Wayfarer", commander_legal=True)
    deck = [wayfarer, commander]
    analysis = DeckAnalysis(
        commanders=["Commander"],
        target_bracket=2,
        final_summary="summary",
        changes=[CardChange(
            remove="Weathered Wayfarer",
            add="Weathered Wayfarer",
            reason="Same card.",
            category="Value",
            priority="Low",
            change_type="Optimization",
        )],
    )

    result, rejected = RecommendationValidator(
        FakeScryfall({"weathered wayfarer": wayfarer})
    ).validate(analysis, deck, [commander], [])

    assert result.changes == []
    assert rejected[0].reason == "The removal and addition are the same card."


def test_recognizes_double_faced_card_alias_as_already_in_deck():
    commander = CardData(name="Commander", color_identity=["W"], commander_legal=True)
    split_card = CardData(
        name="Dusk // Dawn",
        oracle_id="split-oracle-id",
        commander_legal=True,
    )
    deck = [CardData(name="Slow Card", commander_legal=True), split_card, commander]
    analysis = DeckAnalysis(
        commanders=["Commander"],
        target_bracket=2,
        final_summary="summary",
        changes=[CardChange(
            remove="Slow Card",
            add="Dawn",
            reason="Face alias.",
            category="Removal",
            priority="Low",
            change_type="Optimization",
        )],
    )

    result, rejected = RecommendationValidator(FakeScryfall({
        "slow card": deck[0],
        "dawn": split_card,
    })).validate(analysis, deck, [commander], [])

    assert result.changes == []
    assert rejected[0].reason == "The addition is already present in the deck."