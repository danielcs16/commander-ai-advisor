import logging
import ssl
from typing import Any, Callable

import httpx
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter

from config.settings import get_settings
from utils.cache import ProviderCache


class _SystemTrustAdapter(HTTPAdapter):
    def init_poolmanager(self, connections: int, maxsize: int, block: bool = False, **pool_kwargs: Any) -> None:
        pool_kwargs["ssl_context"] = ssl.create_default_context()
        super().init_poolmanager(connections, maxsize, block=block, **pool_kwargs)


class EDHRecService:
    def __init__(
        self,
        client: Any | None = None,
        cache: ProviderCache | None = None,
        timeout: float | None = None,
        logger: logging.Logger | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        settings = get_settings()
        self.timeout = timeout or settings.request_timeout_seconds
        self.cache = cache or ProviderCache(settings.cache_ttl_seconds)
        self.logger = logger or logging.getLogger("commander_ai_advisor.edhrec")
        self.client = client or self._make_client()
        self._set_request_timeout()
        headers = {"Accept": "text/html,application/xhtml+xml"}
        session = getattr(self.client, "session", None)
        if session is not None:
            user_agent = session.headers.get("User-Agent")
            if user_agent:
                headers["User-Agent"] = user_agent
        self.http_client = http_client or httpx.Client(
            verify=ssl.create_default_context(),
            timeout=self.timeout,
            follow_redirects=True,
            headers=headers,
        )

    @staticmethod
    def _make_client() -> Any:
        try:
            from pyedhrec import EDHRec
        except ImportError:
            from edhrec import EDHRec
        return EDHRec()

    def _set_request_timeout(self) -> None:
        session = getattr(self.client, "session", None)
        if session is None or not hasattr(session, "request"):
            return
        if hasattr(session, "mount"):
            session.mount("https://", _SystemTrustAdapter())
        original_request = session.request

        def request_with_timeout(*args: Any, **kwargs: Any) -> Any:
            kwargs.setdefault("timeout", self.timeout)
            return original_request(*args, **kwargs)

        session.request = request_with_timeout

    @staticmethod
    def _parse_commander_page(html: str) -> dict[str, Any]:
        soup = BeautifulSoup(html, "html.parser")
        categories: dict[str, list[dict[str, str]]] = {}
        for grid in soup.find_all("ul"):
            classes = grid.get("class") or []
            if not any("grid" in value.casefold() for value in classes):
                continue
            section = grid.parent.parent.parent
            if section is None:
                continue
            direct_divs = section.find_all("div", recursive=False)
            if len(direct_divs) < 2:
                continue
            category = " ".join(direct_divs[0].get_text(" ", strip=True).split())
            if not category or len(category) > 80:
                continue
            cards: list[dict[str, str]] = []
            seen_names: set[str] = set()
            for link in grid.find_all("a", href=True):
                href = link["href"]
                if not href.startswith(("/cards/", "https://edhrec.com/cards/")):
                    continue
                name_node = link.find("span")
                name = " ".join((name_node or link).get_text(" ", strip=True).split())
                key = name.casefold()
                if name and key not in seen_names:
                    cards.append({"name": name, "edhrec_source": category})
                    seen_names.add(key)
            if cards:
                categories[category] = cards
        return {"commander_page_recommendations": categories} if categories else {}

    def _fetch_commander_page(self, commander: str) -> dict[str, Any]:
        formatter: Callable[[str], str] | None = getattr(self.client, "format_card_name", None)
        if not callable(formatter):
            self.logger.warning("EDHREC page fallback unavailable: card slug formatter is missing")
            return {}
        slug = formatter(commander)
        try:
            response = self.http_client.get(f"https://edhrec.com/commanders/{slug}")
            response.raise_for_status()
            data = self._parse_commander_page(response.text)
            if not data:
                self.logger.warning("EDHREC page contained no recommendation lists for %s", commander)
            return data
        except Exception as exc:
            self.logger.warning("EDHREC page fallback failed for %s: %s", commander, exc)
            return {}

    def _cached_page_data(self, commander: str) -> dict[str, Any]:
        cache_key = f"{commander.casefold()}:commander-page"
        cached = self.cache.get("edhrec", cache_key)
        if cached is not None:
            self.logger.info("EDHREC page cache hit for %s", commander)
            return cached
        data = self._fetch_commander_page(commander)
        self.cache.set("edhrec", cache_key, data)
        return data

    def _call(self, commander: str, method_names: tuple[str, ...]) -> Any:
        cache_key = f"{commander.casefold()}:{method_names[0]}"
        cached = self.cache.get("edhrec", cache_key)
        if cached is not None:
            self.logger.info("EDHREC cache hit for %s (%s)", commander, method_names[0])
            return cached
        method: Callable[..., Any] | None = next(
            (getattr(self.client, name, None) for name in method_names if callable(getattr(self.client, name, None))),
            None,
        )
        if method is None:
            self.logger.warning("No supported EDHREC method found for %s", method_names[0])
            return {}
        try:
            self.logger.info("EDHREC request for %s (%s)", commander, method.__name__)
            result = method(commander)
            result = result if result is not None else {}
            self.cache.set("edhrec", cache_key, result)
            return result
        except Exception as exc:
            self.logger.warning("EDHREC request failed for %s: %s", commander, exc)
            return {}

    def get_commander_data(self, commander: str) -> Any:
        return self._call(commander, ("get_commander_data",))

    def get_commander_cards(self, commander: str) -> Any:
        return self._call(commander, ("get_commander_cards",))

    def get_high_synergy_cards(self, commander: str) -> Any:
        return self._call(commander, ("get_high_synergy_cards",))

    def get_top_cards(self, commander: str) -> Any:
        return self._call(commander, ("get_top_cards",))

    def get_commander_combos(self, commander: str) -> Any:
        return self._call(commander, ("get_card_combos", "get_commander_combos"))

    def get_average_deck(self, commander: str) -> Any:
        return self._call(commander, ("get_commanders_average_deck", "get_average_deck"))

    def get_all_commander_data(self, commander: str) -> dict[str, Any]:
        cache_key = f"{commander.casefold()}:all"
        cached = self.cache.get("edhrec", cache_key)
        if cached is not None:
            return cached

        build_id_getter: Callable[..., Any] | None = getattr(self.client, "get_build_id", None)
        if callable(build_id_getter):
            try:
                build_id = getattr(self.client, "current_build_id", None) or build_id_getter()
            except Exception as exc:
                self.logger.warning("Could not detect EDHREC data build for %s: %s", commander, exc)
                build_id = None
            if not build_id:
                data = self._cached_page_data(commander)
                self.cache.set("edhrec", cache_key, data)
                return data

        data = {
            "commander_data": self.get_commander_data(commander),
            "commander_cards": self.get_commander_cards(commander),
            "high_synergy_cards": self.get_high_synergy_cards(commander),
            "top_cards": self.get_top_cards(commander),
            "combos": self.get_commander_combos(commander),
            "average_deck": self.get_average_deck(commander),
        }
        if not any(data.values()):
            data.update(self._cached_page_data(commander))
        self.cache.set("edhrec", cache_key, data)
        return data
