from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel, Field


class Settings(BaseModel):
    default_analyzer_mode: str = Field(default="auto")
    llm_provider: str = Field(default="mock")
    openai_api_key: str | None = Field(default=None)
    max_log_chars: int = Field(default=20_000)
    mongo_uri: str = Field(default="mongodb://localhost:27017")
    mongo_db_name: str = Field(default="log_analysis_mvp")
    polling_enabled: bool = Field(default=True)
    poll_interval_seconds: int = Field(default=10)
    kibana_request_timeout_seconds: float = Field(default=5.0)
    kibana_batch_size: int = Field(default=25)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            default_analyzer_mode=os.getenv("LOG_ANALYZER_MODE", "auto"),
            llm_provider=os.getenv("LOG_ANALYZER_PROVIDER", "mock"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            max_log_chars=int(os.getenv("LOG_ANALYZER_MAX_CHARS", "20000")),
            mongo_uri=os.getenv("MONGO_URI", "mongodb://localhost:27017"),
            mongo_db_name=os.getenv("MONGO_DB_NAME", "log_analysis_mvp"),
            polling_enabled=os.getenv("OBSERVABILITY_POLL_ENABLED", os.getenv("KIBANA_POLL_ENABLED", "true")).lower()
            == "true",
            poll_interval_seconds=int(os.getenv("OBSERVABILITY_POLL_INTERVAL_SECONDS", os.getenv("KIBANA_POLL_INTERVAL_SECONDS", "10"))),
            kibana_request_timeout_seconds=float(os.getenv("KIBANA_REQUEST_TIMEOUT_SECONDS", "5")),
            kibana_batch_size=int(os.getenv("KIBANA_BATCH_SIZE", "25")),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
