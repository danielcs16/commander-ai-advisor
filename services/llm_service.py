import logging
import ssl
from typing import Any

import httpx
from openai import OpenAI

from config.settings import get_settings
from models.analysis import DeckAnalysis
from prompts.deck_analysis import SYSTEM_PROMPT, build_user_prompt


class LLMServiceError(RuntimeError):
    pass


class LLMService:
    def __init__(self, client: Any | None = None, model: str | None = None) -> None:
        settings = get_settings()
        if client is None and not settings.openai_api_key:
            raise LLMServiceError("OPENAI_API_KEY is not configured.")
        self.client = client or OpenAI(
            api_key=settings.openai_api_key,
            http_client=httpx.Client(
                verify=ssl.create_default_context(),
                timeout=settings.request_timeout_seconds,
            ),
        )
        self.model = model or settings.openai_model
        self.logger = logging.getLogger("commander_ai_advisor.llm")

    def close(self) -> None:
        close = getattr(self.client, "close", None)
        if callable(close):
            close()

    def analyze(self, payload: dict[str, Any]) -> DeckAnalysis:
        self.logger.info("Calling OpenAI structured deck analysis")
        try:
            response = self.client.chat.completions.parse(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(payload)},
                ],
                response_format=DeckAnalysis,
                temperature=0.2,
            )
            parsed = response.choices[0].message.parsed
            if parsed is None:
                raise LLMServiceError("The model returned no structured analysis.")
            return parsed
        except LLMServiceError:
            raise
        except Exception as exc:
            raise LLMServiceError(f"OpenAI analysis failed: {exc}") from exc