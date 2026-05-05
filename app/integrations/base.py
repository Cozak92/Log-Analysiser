from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.schemas.admin import ProjectIntegration


@dataclass(slots=True)
class FetchedLog:
    raw_log: str
    external_id: str | None = None


@dataclass(slots=True)
class IntegrationFetchResult:
    logs: list[FetchedLog]
    error: str | None = None


class IntegrationLogFetcher(Protocol):
    async def fetch_recent_logs(self, integration: ProjectIntegration) -> IntegrationFetchResult:
        ...
