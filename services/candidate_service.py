from collections import defaultdict
from collections.abc import Iterator
from typing import Any

from models.analysis import CandidateCard
from models.card import CardData
from services.edhrec_service import EDHRecService
from services.scryfall_service import ScryfallService


class CandidateService:
    def __init__(self, edhrec: EDHRecService, scryfall: ScryfallService, limit: int = 100) -> None:
        self.edhrec = edhrec
        self.scryfall = scryfall
        self.limit = limit

    @staticmethod
    def _records(value: Any) -> Iterator[dict[str, Any]]:
        if isinstance(value, dict):
            if isinstance(value.get("name"), str):
                yield value
            else:
                for child in value.values():
                    yield from CandidateService._records(child)
        elif isinstance(value, list):
            for child in value:
                yield from CandidateService._records(child)

    @staticmethod
    def _number(record: dict[str, Any], key: str) -> float | None:
        value = record.get(key)
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _aliases(name: str) -> set[str]:
        aliases = {part.strip().casefold() for part in name.split("//") if part.strip()}
        aliases.add(name.strip().casefold())
        return aliases

    def generate(
        self,
        commander: str,
        commanders: list[CardData],
        current_cards: list[CardData],
    ) -> list[CandidateCard]:
        source_data = self.edhrec.get_all_commander_data(commander)
        collected: dict[str, dict[str, Any]] = {}
        for source, payload in source_data.items():
            for record in self._records(payload):
                name = record["name"].strip()
                key = name.casefold()
                candidate = collected.setdefault(
                    key,
                    {"name": name, "sources": set(), "synergy": None, "inclusion": None},
                )
                candidate["sources"].add(record.get("edhrec_source", source))
                synergy = self._number(record, "synergy")
                inclusion = self._number(record, "inclusion")
                if synergy is not None:
                    candidate["synergy"] = synergy
                if inclusion is not None:
                    candidate["inclusion"] = inclusion

        excluded = {alias for card in current_cards for alias in self._aliases(card.name)}
        excluded.update(alias for card in commanders for alias in self._aliases(card.name))
        current_oracle_ids = {card.oracle_id for card in current_cards if card.oracle_id}
        names = [entry["name"] for key, entry in collected.items() if key not in excluded][: self.limit]
        if not names:
            return []

        resolved = self.scryfall.get_cards_by_names(names)
        commander_identity = {color for card in commanders for color in card.color_identity}
        output: list[CandidateCard] = []
        seen_oracle_ids = set(current_oracle_ids)
        for key, entry in collected.items():
            if key in excluded or len(output) >= self.limit:
                continue
            card = resolved.get(key)
            if card is None or card.commander_legal is not True:
                continue
            if self._aliases(card.name) & excluded or (card.oracle_id and card.oracle_id in seen_oracle_ids):
                continue
            if not set(card.color_identity).issubset(commander_identity):
                continue
            if card.oracle_id:
                seen_oracle_ids.add(card.oracle_id)
            output.append(
                CandidateCard(
                    name=card.name,
                    card_data=card.model_dump(exclude={"quantity"}),
                    edhrec_sources=sorted(entry["sources"]),
                    edhrec_synergy=entry["synergy"],
                    inclusion_rate=entry["inclusion"],
                )
            )
        return output