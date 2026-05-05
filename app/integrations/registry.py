from __future__ import annotations

from app.config import Settings
from app.integrations.base import IntegrationFetchResult, IntegrationLogFetcher
from app.integrations.kibana import KibanaLogFetcher
from app.schemas.admin import IntegrationType, ProjectIntegration


class IntegrationFetcherRegistry:
    def __init__(self, settings: Settings, kibana_fetcher: IntegrationLogFetcher | None = None) -> None:
        self._fetchers: dict[IntegrationType, IntegrationLogFetcher] = {
            IntegrationType.KIBANA: kibana_fetcher or KibanaLogFetcher(settings),
        }

    async def fetch_recent_logs(self, integration: ProjectIntegration) -> IntegrationFetchResult:
        fetcher = self._fetchers.get(integration.integration_type)
        if not fetcher:
            return IntegrationFetchResult(
                logs=[],
                error=f"{integration.integration_type.value} integration is registered but no fetcher is implemented yet.",
            )
        return await fetcher.fetch_recent_logs(integration)
