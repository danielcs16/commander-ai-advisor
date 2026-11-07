from models.bracket import Bracket
from models.stats import BracketRule, DeckStats


class BracketService:
    """Central source for bracket guidance; rule data can be replaced at construction."""

    def __init__(self, rules: dict[Bracket, BracketRule] | None = None) -> None:
        self.rules = rules or {
            Bracket.EXHIBITION: BracketRule(
                bracket=1,
                name="Exhibition",
                description="A casual, expressive deck focused on memorable games over efficiency.",
                expected_speed="Slow and varied",
                optimization="Low; thematic choices are welcome",
                combo_tolerance="Avoid compact, deterministic wins",
                tutor_expectation="Few or no tutors",
                interaction_expectation="Light, social interaction",
                win_condition_expectation="Visible, battle-focused finishers",
            ),
            Bracket.CORE: BracketRule(
                bracket=2,
                name="Core",
                description="A focused casual deck with a clear plan and room for varied play.",
                expected_speed="Moderate",
                optimization="Focused but not maximized",
                combo_tolerance="Low; avoid repeatable early combo wins",
                tutor_expectation="Limited, usually thematic tutors",
                interaction_expectation="A modest package",
                win_condition_expectation="Clear, fair paths to close a game",
            ),
            Bracket.UPGRADED: BracketRule(
                bracket=3,
                name="Upgraded",
                description="A synergistic, efficient deck with stronger interaction and coherent finishes.",
                expected_speed="Moderate to fast",
                optimization="High synergy and consistency",
                combo_tolerance="Combos may support the main plan",
                tutor_expectation="Some tutors aligned with the strategy",
                interaction_expectation="Consistent interaction",
                win_condition_expectation="Efficient, well-supported finishers",
            ),
            Bracket.OPTIMIZED: BracketRule(
                bracket=4,
                name="Optimized",
                description="A highly tuned deck built for efficient, powerful multiplayer play.",
                expected_speed="Fast",
                optimization="Very high; consistency is a priority",
                combo_tolerance="Efficient combos are expected",
                tutor_expectation="Frequent, efficient tutoring may fit",
                interaction_expectation="Dense and efficient",
                win_condition_expectation="Multiple compact or resilient lines",
            ),
            Bracket.CEDH: BracketRule(
                bracket=5,
                name="cEDH",
                description="A competitive deck optimized to win against the strongest available opposition.",
                expected_speed="Very fast",
                optimization="Maximum practical efficiency",
                combo_tolerance="Compact, deterministic win lines are central",
                tutor_expectation="High; tutors maximize consistency",
                interaction_expectation="High-impact, low-cost interaction",
                win_condition_expectation="Fast, compact, protected wins",
            ),
        }

    def get_rules(self, bracket: Bracket | int) -> BracketRule:
        return self.rules[Bracket(bracket)]

    def all_rules(self) -> list[BracketRule]:
        return [self.rules[bracket] for bracket in Bracket]

    def estimate(self, stats: DeckStats) -> int:
        categories = stats.categories
        tutors = len(categories.get("Tutor", []))
        interaction = len(categories.get("Removal", [])) + len(categories.get("Counterspell", []))
        score = 1
        if stats.average_mana_value is not None and stats.average_mana_value <= 2.7:
            score += 1
        if tutors >= 3:
            score += 1
        if tutors >= 7:
            score += 1
        if interaction >= 12 and len(categories.get("Ramp", [])) >= 8:
            score += 1
        return min(score, 5)