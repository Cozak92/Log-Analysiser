from __future__ import annotations

import hashlib

from app.config import Settings
from app.integrations.registry import IntegrationFetcherRegistry
from app.repositories.admin_repository import AdminRepository
from app.schemas.admin import ProjectIntegration, PollResult
from app.schemas.analysis import AnalyzerMode, SeverityLevel
from app.services.analysis_service import AnalysisService


class DetectionService:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: AdminRepository,
        analysis_service: AnalysisService,
        fetcher_registry: IntegrationFetcherRegistry | None = None,
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._analysis_service = analysis_service
        self._fetcher_registry = fetcher_registry or IntegrationFetcherRegistry(settings)

    async def poll_integration(self, integration: ProjectIntegration) -> PollResult:
        current_integration = self._fresh_enabled_integration(integration)
        if current_integration is None:
            return PollResult(integration_id=integration.id, status="disabled")
        integration = current_integration

        fetch_result = await self._fetcher_registry.fetch_recent_logs(integration)
        current_integration = self._fresh_enabled_integration(integration)
        if current_integration is None:
            return PollResult(integration_id=integration.id, status="disabled")
        integration = current_integration

        if fetch_result.error:
            self._repository.update_integration_poll_result(
                integration.id,
                status="error",
                fetched_count=0,
                detected_count=0,
                error=fetch_result.error,
            )
            return PollResult(integration_id=integration.id, status="error", error=fetch_result.error)

        detected_count = 0
        analyzer_mode = self._integration_analyzer_mode(integration)
        for fetched_log in fetch_result.logs:
            current_integration = self._fresh_enabled_integration(integration)
            if current_integration is None:
                return PollResult(integration_id=integration.id, status="disabled", fetched_count=len(fetch_result.logs))
            integration = current_integration

            response = self._analysis_service.analyze_text(
                fetched_log.raw_log,
                analyzer_mode=analyzer_mode,
                llm_provider=integration.llm_provider,
                llm_model=integration.llm_model,
                include_report=True,
                source_name=f"{integration.project_name}/{integration.resource_name}:{fetched_log.external_id or integration.integration_type.value}",
            )
            if not self._is_anomalous(response.analysis.severity, response.analysis.error_type):
                continue

            detected_count += 1
            self._repository.upsert_detection(
                {
                    "fingerprint": self._fingerprint(integration, fetched_log.raw_log, response.analysis.error_type),
                    "integration_id": integration.id,
                    "project_name": integration.project_name,
                    "integration_type": integration.integration_type.value,
                    "endpoint_url": integration.endpoint_url,
                    "resource_name": integration.resource_name,
                    "summary": response.analysis.summary,
                    "severity": response.analysis.severity.value,
                    "error_type": response.analysis.error_type,
                    "analyzer_used": response.meta.analyzer_used,
                    "llm_provider": integration.llm_provider,
                    "llm_model": integration.llm_model,
                    "fallback_used": response.meta.fallback_used,
                    "raw_log": fetched_log.raw_log,
                    "report_markdown": response.report_markdown,
                }
            )

        if self._fresh_enabled_integration(integration) is None:
            return PollResult(
                integration_id=integration.id,
                status="disabled",
                fetched_count=len(fetch_result.logs),
                detected_count=detected_count,
            )

        self._repository.update_integration_poll_result(
            integration.id,
            status="ok",
            fetched_count=len(fetch_result.logs),
            detected_count=detected_count,
            error=None,
        )
        return PollResult(
            integration_id=integration.id,
            status="ok",
            fetched_count=len(fetch_result.logs),
            detected_count=detected_count,
        )

    async def poll_all_enabled_integrations(self) -> list[PollResult]:
        integrations = [integration for integration in self._repository.list_integrations() if integration.enabled]
        results: list[PollResult] = []
        for integration in integrations:
            results.append(await self.poll_integration(integration))
        return results

    def _integration_analyzer_mode(self, integration: ProjectIntegration) -> AnalyzerMode:
        if integration.analyzer_mode:
            return integration.analyzer_mode
        try:
            return AnalyzerMode(self._settings.default_analyzer_mode)
        except ValueError:
            return AnalyzerMode.AUTO

    def _fresh_enabled_integration(self, integration: ProjectIntegration) -> ProjectIntegration | None:
        current_integration = self._repository.get_integration(integration.id)
        if current_integration is None or not current_integration.enabled:
            return None
        return current_integration

    @staticmethod
    def _is_anomalous(severity: SeverityLevel, error_type: str) -> bool:
        if severity in {SeverityLevel.HIGH, SeverityLevel.CRITICAL}:
            return True
        return error_type not in {"unknown_application_error", "unknown"}

    @staticmethod
    def _fingerprint(integration: ProjectIntegration, raw_log: str, error_type: str) -> str:
        digest = hashlib.sha256()
        digest.update(integration.id.encode("utf-8"))
        digest.update(error_type.encode("utf-8"))
        digest.update(raw_log[:2_000].encode("utf-8", errors="ignore"))
        return digest.hexdigest()
