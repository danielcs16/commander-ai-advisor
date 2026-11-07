from collections import Counter

from models.card import CardData
from models.deck import ValidationReport


class DeckValidator:
    def validate(self, cards: list[CardData], commanders: list[CardData]) -> ValidationReport:
        report = ValidationReport()
        report.deck_size = sum(card.quantity for card in cards)
        commander_names = {commander.name.casefold() for commander in commanders}

        if not commanders:
            report.errors.append("A Commander must be specified and validated.")
        for commander in commanders:
            if commander.commander_legal is False:
                report.errors.append(f"{commander.name} is not legal in Commander.")

        identity = {color for commander in commanders for color in commander.color_identity}
        report.info.append(
            "Color identity detected: " + (" / ".join(sorted(identity)) if identity else "Colorless") + "."
        )

        copies: Counter[str] = Counter()
        card_by_name = {card.name.casefold(): card for card in cards}
        for card in cards:
            if card.commander_legal is False:
                report.errors.append(f"{card.name} is not legal in Commander.")
            elif card.commander_legal is None:
                report.warnings.append(f"Commander legality is unavailable for {card.name}.")
            outside_identity = set(card.color_identity) - identity
            if outside_identity:
                report.errors.append(
                    f"{card.name} is outside the Commander color identity ({', '.join(sorted(outside_identity))})."
                )
            copies[card.name.casefold()] += card.quantity

        for name, quantity in copies.items():
            card = card_by_name[name]
            basic_land = "basic" in (card.type_line or "").casefold() and "land" in (card.type_line or "").casefold()
            unlimited = "any number of cards named" in (card.oracle_text or "").casefold()
            if quantity > 1 and not basic_land and not unlimited:
                report.errors.append(f"Duplicate copies of {card.name} are not allowed in Commander.")

        for commander in commanders:
            if commander.name.casefold() not in card_by_name:
                report.warnings.append(f"Commander {commander.name} is not included in the pasted decklist.")

        if report.deck_size != 100:
            report.warnings.append(f"Deck currently contains {report.deck_size} cards; Commander decks normally contain 100.")
        return report