from __future__ import annotations

import hashlib

from app.config import Settings
from app.integrations.kibana import KibanaLogFetcher
from app.repositories.admin_repository import AdminRepository
from app.schemas.admin import KibanaSource, PollResult
from app.schemas.analysis import AnalyzerMode, SeverityLevel
from app.services.analysis_service import AnalysisService


class DetectionService:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: AdminRepository,
        analysis_service: AnalysisService,
        kibana_fetcher: KibanaLogFetcher | None = None,
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._analysis_service = analysis_service
        self._kibana_fetcher = kibana_fetcher or KibanaLogFetcher(settings)

    async def poll_source(self, source: KibanaSource) -> PollResult:
        fetch_result = await self._kibana_fetcher.fetch_recent_logs(source)
        if fetch_result.error:
            self._repository.update_source_poll_result(
                source.id,
                status="error",
                fetched_count=0,
                detected_count=0,
                error=fetch_result.error,
            )
            return PollResult(source_id=source.id, status="error", error=fetch_result.error)

        detected_count = 0
        analyzer_mode = self._source_analyzer_mode(source)
        for fetched_log in fetch_result.logs:
            response = self._analysis_service.analyze_text(
                fetched_log.raw_log,
                analyzer_mode=analyzer_mode,
                llm_provider=source.llm_provider,
                llm_model=source.llm_model,
                include_report=True,
                source_name=f"{source.data_view_name}:{fetched_log.external_id or 'kibana'}",
            )
            if not self._is_anomalous(response.analysis.severity, response.analysis.error_type):
                continue

            detected_count += 1
            self._repository.upsert_detection(
                {
                    "fingerprint": self._fingerprint(source, fetched_log.raw_log, response.analysis.error_type),
                    "source_id": source.id,
                    "kibana_url": source.kibana_url,
                    "data_view_name": source.data_view_name,
                    "summary": response.analysis.summary,
                    "severity": response.analysis.severity.value,
                    "error_type": response.analysis.error_type,
                    "analyzer_used": response.meta.analyzer_used,
                    "llm_provider": source.llm_provider,
                    "llm_model": source.llm_model,
                    "fallback_used": response.meta.fallback_used,
                    "raw_log": fetched_log.raw_log,
                    "report_markdown": response.report_markdown,
                }
            )

        self._repository.update_source_poll_result(
            source.id,
            status="ok",
            fetched_count=len(fetch_result.logs),
            detected_count=detected_count,
            error=None,
        )
        return PollResult(
            source_id=source.id,
            status="ok",
            fetched_count=len(fetch_result.logs),
            detected_count=detected_count,
        )

    async def poll_all_enabled_sources(self) -> list[PollResult]:
        sources = [source for source in self._repository.list_sources() if source.enabled]
        results: list[PollResult] = []
        for source in sources:
            results.append(await self.poll_source(source))
        return results

    def _source_analyzer_mode(self, source: KibanaSource) -> AnalyzerMode:
        if source.analyzer_mode:
            return source.analyzer_mode
        try:
            return AnalyzerMode(self._settings.default_analyzer_mode)
        except ValueError:
            return AnalyzerMode.AUTO

    @staticmethod
    def _is_anomalous(severity: SeverityLevel, error_type: str) -> bool:
        if severity in {SeverityLevel.HIGH, SeverityLevel.CRITICAL}:
            return True
        return error_type not in {"unknown_application_error", "unknown"}

    @staticmethod
    def _fingerprint(source: KibanaSource, raw_log: str, error_type: str) -> str:
        digest = hashlib.sha256()
        digest.update(source.id.encode("utf-8"))
        digest.update(error_type.encode("utf-8"))
        digest.update(raw_log[:2_000].encode("utf-8", errors="ignore"))
        return digest.hexdigest()
