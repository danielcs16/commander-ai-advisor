from pydantic import BaseModel, Field

from models.card import CardData


class Deck(BaseModel):
    commanders: list[str] = Field(default_factory=list)
    cards: list[CardData] = Field(default_factory=list)


class ValidationReport(BaseModel):
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    info: list[str] = Field(default_factory=list)
    deck_size: int = 0