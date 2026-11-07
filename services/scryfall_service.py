import logging
import ssl
import time
from typing import Any

import httpx

from config.settings import get_settings
from models.card import CardData
from utils.cache import ProviderCache


class ScryfallServiceError(RuntimeError):
    pass


class ScryfallService:
    def __init__(
        self,
        client: httpx.Client | None = None,
        cache: ProviderCache | None = None,
        max_retries: int | None = None,
        timeout: float | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        settings = get_settings()
        self.client = client or httpx.Client(
            base_url=settings.scryfall_base_url,
            timeout=timeout or settings.request_timeout_seconds,
            verify=ssl.create_default_context(),
            headers={"User-Agent": "Commander-AI-Deck-Advisor/1.0", "Accept": "application/json"},
        )
        self.cache = cache or ProviderCache(settings.cache_ttl_seconds)
        self.max_retries = settings.max_retries if max_retries is None else max_retries
        self.logger = logger or logging.getLogger("commander_ai_advisor.scryfall")
        self._last_request_at = 0.0

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        for attempt in range(self.max_retries + 1):
            pause = 0.1 - (time.monotonic() - self._last_request_at)
            if pause > 0:
                time.sleep(pause)
            self._last_request_at = time.monotonic()
            try:
                response = self.client.request(method, url, **kwargs)
            except httpx.TimeoutException as exc:
                if attempt < self.max_retries:
                    time.sleep(0.1 * (2**attempt))
                    continue
                raise ScryfallServiceError("Scryfall request timed out") from exc
            except httpx.HTTPError as exc:
                if attempt < self.max_retries:
                    time.sleep(0.1 * (2**attempt))
                    continue
                raise ScryfallServiceError(f"Scryfall request failed: {exc}") from exc

            if response.status_code == 404:
                return response
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < self.max_retries:
                    retry_after = response.headers.get("Retry-After")
                    delay = min(float(retry_after), 2.0) if retry_after and retry_after.isdigit() else 0.1 * (2**attempt)
                    time.sleep(delay)
                    continue
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise ScryfallServiceError(f"Scryfall returned HTTP {response.status_code}") from exc
            return response
        raise ScryfallServiceError("Scryfall request failed after retries")

    @staticmethod
    def _to_card(data: dict[str, Any], quantity: int = 1) -> CardData:
        faces = data.get("card_faces") or []
        image_uris = data.get("image_uris") or next(
            (face.get("image_uris") for face in faces if face.get("image_uris")), {}
        )
        oracle_text = data.get("oracle_text") or "\n".join(
            face.get("oracle_text", "") for face in faces if face.get("oracle_text")
        ) or None
        type_line = data.get("type_line") or " // ".join(
            face.get("type_line", "") for face in faces if face.get("type_line")
        ) or None
        legalities = data.get("legalities") or {}
        price = data.get("prices", {}).get("usd")
        try:
            price_usd = float(price) if price is not None else None
        except (TypeError, ValueError):
            price_usd = None
        mana_value = data.get("cmc")
        return CardData(
            name=data["name"],
            quantity=quantity,
            oracle_id=data.get("oracle_id"),
            mana_cost=data.get("mana_cost") or next(
                (face.get("mana_cost") for face in faces if face.get("mana_cost")), None
            ),
            mana_value=float(mana_value) if mana_value is not None else None,
            type_line=type_line,
            oracle_text=oracle_text,
            colors=data.get("colors") or [],
            color_identity=data.get("color_identity") or [],
            keywords=data.get("keywords") or [],
            legalities=legalities,
            commander_legal=legalities.get("commander") == "legal" if "commander" in legalities else None,
            price_usd=price_usd,
            scryfall_uri=data.get("scryfall_uri"),
            image_uris=image_uris,
            produced_mana=data.get("produced_mana") or [],
        )

    def get_card_by_name(self, name: str) -> CardData | None:
        key = name.strip().casefold()
        cached = self.cache.get("scryfall", f"card:{key}")
        if cached is not None:
            self.logger.info("Scryfall cache hit for %s", name)
            return cached or None
        self.logger.info("Scryfall lookup for %s", name)
        response = self._request("GET", "/cards/named", params={"exact": name.strip()})
        if response.status_code == 404:
            self.cache.set("scryfall", f"card:{key}", False)
            return None
        card = self._to_card(response.json())
        self.cache.set("scryfall", f"card:{key}", card)
        return card

    def get_cards_by_names(self, names: list[str]) -> dict[str, CardData | None]:
        normalized = list(dict.fromkeys(name.strip() for name in names if name.strip()))
        results: dict[str, CardData | None] = {}
        missing: list[str] = []
        for name in normalized:
            key = name.casefold()
            cached = self.cache.get("scryfall", f"card:{key}")
            if cached is None:
                missing.append(name)
            else:
                self.logger.info("Scryfall cache hit for %s", name)
                results[key] = cached or None

        for start in range(0, len(missing), 75):
            chunk = missing[start : start + 75]
            self.logger.info("Scryfall collection lookup for %d cards", len(chunk))
            response = self._request(
                "POST",
                "/cards/collection",
                json={"identifiers": [{"name": name} for name in chunk]},
            )
            payload = response.json()
            found_by_alias: dict[str, dict[str, dict[str, Any]]] = {}
            for item in payload.get("data", []):
                aliases = {item.get("name", "").casefold()}
                aliases.update(
                    part.strip().casefold()
                    for part in item.get("name", "").split("//")
                    if part.strip()
                )
                aliases.update(
                    face.get("name", "").casefold()
                    for face in item.get("card_faces", [])
                    if face.get("name")
                )
                card_key = item.get("oracle_id") or item.get("name", "").casefold()
                for alias in aliases:
                    found_by_alias.setdefault(alias, {})[card_key] = item

            for name in chunk:
                key = name.casefold()
                matches = found_by_alias.get(key, {})
                if len(matches) == 1:
                    card = self._to_card(next(iter(matches.values())))
                    results[key] = card
                    self.cache.set("scryfall", f"card:{key}", card)
                else:
                    results[key] = self.get_card_by_name(name)
        return results

    def search_cards(self, query: str, page: int = 1) -> list[CardData]:
        response = self._request("GET", "/cards/search", params={"q": query, "page": page})
        payload = response.json()
        return [self._to_card(item) for item in payload.get("data", [])]

    def validate_card(self, name: str) -> bool:
        return self.get_card_by_name(name) is not None

    def get_card_details(self, name: str) -> CardData | None:
        return self.get_card_by_name(name)

    def validate_commander_legality(self, name: str) -> bool | None:
        card = self.get_card_by_name(name)
        return card.commander_legal if card else False

    @staticmethod
    def can_be_commander(card: CardData) -> bool:
        type_line = (card.type_line or "").casefold()
        oracle_text = (card.oracle_text or "").casefold()
        return (
            "legendary creature" in type_line
            or "can be your commander" in oracle_text
            or ("legendary enchantment" in type_line and "background" in type_line)
        )

    @staticmethod
    def validate_commander_pairing(commanders: list[CardData]) -> str | None:
        backgrounds = [
            card
            for card in commanders
            if "background" in (card.type_line or "").casefold()
        ]
        if not backgrounds:
            return None
        if len(commanders) != 2 or len(backgrounds) != 1:
            return "A Background must be paired as the second Commander; select exactly one Background and one compatible Commander."

        lead_commander = next(card for card in commanders if card not in backgrounds)
        has_choose_background = "choose a background" in (lead_commander.oracle_text or "").casefold() or any(
            keyword.casefold() == "choose a background" for keyword in lead_commander.keywords
        )
        if not has_choose_background:
            return f"{backgrounds[0].name} can only be a second Commander with a Commander that has 'Choose a Background'."
        return None

    @staticmethod
    def validate_color_identity(card: CardData, commanders: list[CardData]) -> bool:
        commander_identity = {color for commander in commanders for color in commander.color_identity}
        return set(card.color_identity).issubset(commander_identity)