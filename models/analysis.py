from typing import Literal

from pydantic import BaseModel, Field


class CardChange(BaseModel):
    remove: str
    add: str
    reason: str
    category: str
    priority: Literal["High", "Medium", "Low"]
    change_type: Literal["Upgrade", "Downgrade", "Optimization", "Bracket Adjustment"]
    edhrec_synergy: float | None = None


class DeckAnalysis(BaseModel):
    commanders: list[str] = Field(default_factory=list)
    detected_strategy: list[str] = Field(default_factory=list)
    current_bracket_estimate: int | None = Field(default=None, ge=1, le=5)
    target_bracket: int = Field(ge=1, le=5)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    changes: list[CardChange] = Field(default_factory=list, max_length=10)
    final_summary: str


class CandidateCard(BaseModel):
    name: str
    card_data: dict
    edhrec_sources: list[str] = Field(default_factory=list)
    edhrec_synergy: float | None = None
    inclusion_rate: float | None = None


class RecommendationRejected(BaseModel):
    remove: str
    add: str
    reason: str