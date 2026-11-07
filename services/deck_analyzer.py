import re

from models.card import CardData
from models.stats import DeckStats


class DeckAnalyzer:
    _category_patterns = {
        "Ramp": re.compile(r"add \{[wubrgc]|search your library for .*land|put .*land .*onto the battlefield", re.I),
        "Card Draw": re.compile(r"draw (?:a|one|two|three|four|five|\d+|cards?)", re.I),
        "Counterspell": re.compile(r"counter target", re.I),
        "Removal": re.compile(r"destroy target|exile target|deals? .* damage to target", re.I),
        "Board Wipe": re.compile(r"destroy all|exile all|each creature gets -|all creatures get -", re.I),
        "Tutor": re.compile(r"search your library for (?:a|any|up to) (?!.*land)", re.I),
        "Protection": re.compile(r"hexproof|indestructible|protection from|phase out|ward \{", re.I),
        "Recursion": re.compile(r"return .* from your graveyard|put .* from your graveyard .* into your hand", re.I),
        "Graveyard Hate": re.compile(r"exile .* from .* graveyard|cards in graveyards? can't", re.I),
        "Artifact/Enchantment Hate": re.compile(r"destroy target artifact|destroy target enchantment|exile target artifact|exile target enchantment", re.I),
        "Win Condition": re.compile(r"you win the game|each opponent loses|target opponent loses", re.I),
    }

    def analyze(self, cards: list[CardData]) -> DeckStats:
        stats = DeckStats(total_cards=sum(card.quantity for card in cards))
        mana_values: list[float] = []
        categories: dict[str, list[str]] = {name: [] for name in self._category_patterns}
        categories["Land"] = []
        categories["Mana Rock"] = []
        curve: dict[str, int] = {}
        colors: dict[str, int] = {}

        for card in cards:
            type_line = (card.type_line or "").casefold()
            text = card.oracle_text or ""
            if "land" in type_line:
                stats.lands += card.quantity
                categories["Land"].append(card.name)
            else:
                stats.nonlands += card.quantity
                if card.mana_value is not None:
                    mana_values.extend([card.mana_value] * card.quantity)
                    bucket = str(min(int(card.mana_value), 7)) if card.mana_value < 7 else "7+"
                    curve[bucket] = curve.get(bucket, 0) + card.quantity
            if "artifact" in type_line and re.search(r"add \{[wubrgc]", text, re.I):
                categories["Mana Rock"].append(card.name)
            for color in card.colors:
                colors[color] = colors.get(color, 0) + card.quantity
            for category, pattern in self._category_patterns.items():
                if pattern.search(text):
                    categories[category].append(card.name)

        stats.average_mana_value = round(sum(mana_values) / len(mana_values), 2) if mana_values else None
        stats.mana_curve = dict(sorted(curve.items(), key=lambda item: (item[0] == "7+", int(item[0].rstrip("+")))))
        stats.color_distribution = colors
        stats.categories = {name: values for name, values in categories.items() if values}
        return stats