from __future__ import annotations

import os

from pydantic import BaseModel, Field, model_validator
from langchain_openai import ChatOpenAI

from contract_review_agent.config import (
    DEFAULT_PROVIDER_BASE_URLS,
    DEFAULT_PROVIDER_MODELS,
    ProviderName,
)


class ProviderSettings(BaseModel):
    provider: ProviderName
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    timeout: int = 180
    max_retries: int = 2

    @model_validator(mode="after")
    def fill_defaults(self) -> "ProviderSettings":
        if self.model is None:
            self.model = DEFAULT_PROVIDER_MODELS[self.provider]
        if self.base_url is None:
            self.base_url = DEFAULT_PROVIDER_BASE_URLS[self.provider]
        if self.api_key is None:
            env_name = f"{self.provider.upper()}_API_KEY"
            self.api_key = os.getenv(env_name)
        if not self.api_key:
            raise ValueError(
                f"Missing API key for provider '{self.provider}'. "
                f"Pass --api-key or set {self.provider.upper()}_API_KEY."
            )
        return self


def create_chat_model(settings: ProviderSettings) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.base_url,
        temperature=settings.temperature,
        timeout=settings.timeout,
        max_retries=settings.max_retries,
    )
