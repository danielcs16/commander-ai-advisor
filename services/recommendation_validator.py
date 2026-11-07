from models.analysis import CandidateCard, DeckAnalysis, RecommendationRejected
from models.card import CardData
from services.scryfall_service import ScryfallService


class RecommendationValidator:
    def __init__(self, scryfall: ScryfallService) -> None:
        self.scryfall = scryfall

    @staticmethod
    def _aliases(name: str) -> set[str]:
        aliases = {part.strip().casefold() for part in name.split("//") if part.strip()}
        aliases.add(name.strip().casefold())
        return aliases

    def validate(
        self,
        analysis: DeckAnalysis,
        deck_cards: list[CardData],
        commanders: list[CardData],
        candidates: list[str] | list[CandidateCard],
    ) -> tuple[DeckAnalysis, list[RecommendationRejected]]:
        candidate_cards_by_id: dict[str, CandidateCard] = {}
        candidate_cards_by_alias: dict[str, CandidateCard] = {}
        candidate_aliases: set[str] = set()
        for candidate in candidates:
            if isinstance(candidate, CandidateCard):
                aliases = self._aliases(candidate.name)
                candidate_aliases.update(aliases)
                for alias in aliases:
                    candidate_cards_by_alias[alias] = candidate
                canonical_name = candidate.card_data.get("name")
                if isinstance(canonical_name, str):
                    canonical_aliases = self._aliases(canonical_name)
                    candidate_aliases.update(canonical_aliases)
                    for alias in canonical_aliases:
                        candidate_cards_by_alias[alias] = candidate
                oracle_id = candidate.card_data.get("oracle_id")
                if oracle_id:
                    candidate_cards_by_id[oracle_id] = candidate
            else:
                candidate_aliases.update(self._aliases(candidate))

        deck_aliases = {alias for card in deck_cards for alias in self._aliases(card.name)}
        deck_oracle_ids = {card.oracle_id for card in deck_cards if card.oracle_id}
        commander_aliases = {alias for card in commanders for alias in self._aliases(card.name)}
        commander_oracle_ids = {card.oracle_id for card in commanders if card.oracle_id}
        names = list(dict.fromkeys(
            name for change in analysis.changes for name in (change.remove, change.add)
        ))
        resolved = self.scryfall.get_cards_by_names(names)
        accepted = []
        rejected: list[RecommendationRejected] = []
        commander_identity = {color for card in commanders for color in card.color_identity}

        for change in analysis.changes:
            reason = None
            remove_key = change.remove.casefold()
            add_key = change.add.casefold()
            remove_card = resolved.get(remove_key)
            add_card = resolved.get(add_key)
            remove_id = remove_card.oracle_id if remove_card else None
            add_id = add_card.oracle_id if add_card else None
            same_card = (
                bool(remove_id and add_id and remove_id == add_id)
                or bool(self._aliases(change.remove) & self._aliases(change.add))
            )
            remove_is_commander = remove_key in commander_aliases or bool(
                remove_id and remove_id in commander_oracle_ids
            )
            remove_is_in_deck = bool(self._aliases(change.remove) & deck_aliases) or bool(
                remove_id and remove_id in deck_oracle_ids
            )
            add_is_in_deck = bool(self._aliases(change.add) & deck_aliases) or bool(
                add_id and add_id in deck_oracle_ids
            )
            is_candidate = bool(self._aliases(change.add) & candidate_aliases) or bool(
                add_card and self._aliases(add_card.name) & candidate_aliases
            ) or bool(add_id and add_id in candidate_cards_by_id)

            if same_card:
                reason = "The removal and addition are the same card."
            elif remove_is_commander:
                reason = "A Commander cannot be removed by a card-change recommendation."
            elif not remove_is_in_deck:
                reason = "The removal card is not present in the deck."
            elif remove_card is None:
                reason = "The removal card could not be validated by Scryfall."
            elif add_card is None:
                reason = "The addition could not be found on Scryfall."
            elif add_is_in_deck:
                reason = "The addition is already present in the deck."
            elif not is_candidate:
                reason = "The addition is not in the Scryfall-validated EDHREC candidate list."
            elif add_card.commander_legal is not True:
                reason = "The addition is not confirmed legal in Commander."
            elif not set(add_card.color_identity).issubset(commander_identity):
                reason = "The addition is outside the Commander's color identity."

            if reason:
                rejected.append(RecommendationRejected(remove=change.remove, add=change.add, reason=reason))
            else:
                candidate = candidate_cards_by_id.get(add_id) if add_id else None
                if candidate is None:
                    candidate = next(
                        (
                            candidate_cards_by_alias[alias]
                            for alias in self._aliases(change.add)
                            if alias in candidate_cards_by_alias
                        ),
                        None,
                    )
                change.edhrec_synergy = candidate.edhrec_synergy if candidate else None
                accepted.append(change)

        analysis.changes = accepted
        return analysis, rejected