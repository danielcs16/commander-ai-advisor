from pydantic import BaseModel, ConfigDict, Field


class CardData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    quantity: int = 1
    oracle_id: str | None = None
    mana_cost: str | None = None
    mana_value: float | None = None
    type_line: str | None = None
    oracle_text: str | None = None
    colors: list[str] = Field(default_factory=list)
    color_identity: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    legalities: dict[str, str] = Field(default_factory=dict)
    commander_legal: bool | None = None
    price_usd: float | None = None
    scryfall_uri: str | None = None
    image_uris: dict[str, str] = Field(default_factory=dict)
    produced_mana: list[str] = Field(default_factory=list)


class DeckEntry(BaseModel):
    quantity: int = Field(ge=1)
    name: str = Field(min_length=1)