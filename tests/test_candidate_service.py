from models.card import CardData
from services.candidate_service import CandidateService


class FakeEDHRec:
    def get_all_commander_data(self, commander):
        return {
            "high_synergy_cards": {"Synergy": [{"name": "Good Card", "synergy": 0.0}, {"name": "Out of Color"}]},
            "top_cards": [{"name": "Already In Deck"}, {"name": "Missing Card"}, {"name": "Illegal"}],
        }


class FakeScryfall:
    def get_cards_by_names(self, names):
        cards = {
            "good card": CardData(name="Good Card", color_identity=["G"], commander_legal=True),
            "out of color": CardData(name="Out of Color", color_identity=["U"], commander_legal=True),
            "illegal": CardData(name="Illegal", color_identity=["G"], commander_legal=False),
        }
        return {name.casefold(): cards.get(name.casefold()) for name in names}


def test_candidates_are_validated_and_filtered():
    commander = CardData(name="Commander", color_identity=["G"], commander_legal=True)
    current = [CardData(name="Already In Deck", commander_legal=True)]

    candidates = CandidateService(FakeEDHRec(), FakeScryfall()).generate("Commander", [commander], current)

    assert [candidate.name for candidate in candidates] == ["Good Card"]
    assert candidates[0].edhrec_synergy == 0.0


def test_does_not_offer_double_faced_card_already_in_deck_by_face_name():
    class DoubleFacedEDHRec:
        def get_all_commander_data(self, commander):
            return {"top_cards": [{"name": "Treasure Map"}]}

    class DoubleFacedScryfall:
        def get_cards_by_names(self, names):
            return {
                "treasure map": CardData(
                    name="Treasure Map // Treasure Cove",
                    oracle_id="treasure-map-oracle-id",
                    color_identity=["W"],
                    commander_legal=True,
                )
            }

    commander = CardData(name="Commander", color_identity=["W"], commander_legal=True)
    current = [CardData(
        name="Treasure Map // Treasure Cove",
        oracle_id="treasure-map-oracle-id",
        commander_legal=True,
    )]

    candidates = CandidateService(DoubleFacedEDHRec(), DoubleFacedScryfall()).generate(
        "Commander", [commander], current
    )

    assert candidates == []