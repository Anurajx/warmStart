"""Application configuration.

All settings are overridable through environment variables (prefix ``WARMSTART_``)
or a local ``.env`` file. ``OPENAI_API_KEY`` is honoured as a fallback so the
standard OpenAI SDK convention keeps working unchanged.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

CustomerTier = Literal["Free", "Gold"]


class Settings(BaseSettings):
    """Runtime settings for the Warmstart service."""

    app_name: str = "Warmstart"
    version: str = "1.0.0"

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_index_name: str = "idx:warmstart_vectors"
    redis_key_prefix: str = "warmstart"

    # OpenAI
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    llm_model: str = "gpt-4o-mini"
    judge_model: str = "gpt-4o-mini"
    openai_base_url: str | None = None

    # Cache behaviour
    semantic_similarity_threshold: float = 0.88
    cache_ttl_seconds: int = 86400
    vector_knn_results: int = 3

    # USD pricing per 1M tokens (OpenAI published list pricing).
    input_token_price_per_1m: float = 0.15
    output_token_price_per_1m: float = 0.60
    embedding_token_price_per_1m: float = 0.02

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="WARMSTART_",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="after")
    def _default_openai_key(self) -> "Settings":
        """Fall back to the conventional OPENAI_API_KEY variable."""
        if not self.openai_api_key:
            self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()