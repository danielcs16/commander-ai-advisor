from pydantic import BaseModel, Field


class DeckStats(BaseModel):
    total_cards: int = 0
    lands: int = 0
    nonlands: int = 0
    average_mana_value: float | None = None
    mana_curve: dict[str, int] = Field(default_factory=dict)
    color_distribution: dict[str, int] = Field(default_factory=dict)
    categories: dict[str, list[str]] = Field(default_factory=dict)


class BracketRule(BaseModel):
    bracket: int
    name: str
    description: str
    expected_speed: str
    optimization: str
    combo_tolerance: str
    tutor_expectation: str
    interaction_expectation: str
    win_condition_expectation: str
    restrictions: list[str] = Field(default_factory=list)
    game_changers: list[str] = Field(default_factory=list)