from __future__ import annotations

from dataclasses import dataclass

from app.analyzers.base import LogAnalyzer
from app.analyzers.llm import LLMLogAnalyzer, OpenAICompatibleProviderStub
from app.analyzers.mock import MockAnalyzer
from app.analyzers.rule_based import RuleBasedAnalyzer
from app.config import Settings
from app.schemas.analysis import AnalysisMeta, AnalyzerMode, AnalyzeResponse
from app.services.report_service import MarkdownReportService
from app.utils.log_parser import build_log_excerpt, parse_log


@dataclass(slots=True)
class AnalyzerSelection:
    analyzer: LogAnalyzer
    fallback_used: bool


class AnalysisService:
    def __init__(
        self,
        *,
        settings: Settings,
        report_service: MarkdownReportService | None = None,
    ) -> None:
        self._settings = settings
        self._rule_based = RuleBasedAnalyzer()
        self._mock = MockAnalyzer(self._rule_based)
        self._llm = LLMLogAnalyzer(
            provider=OpenAICompatibleProviderStub(api_key=settings.openai_api_key),
            fallback_analyzer=self._mock,
        )
        self._report_service = report_service or MarkdownReportService()

    def analyze_text(
        self,
        text: str,
        *,
        analyzer_mode: AnalyzerMode = AnalyzerMode.AUTO,
        llm_provider: str | None = None,
        llm_model: str | None = None,
        include_report: bool = True,
        source_name: str | None = None,
    ) -> AnalyzeResponse:
        selection = self._select_analyzer(analyzer_mode, llm_provider=llm_provider, llm_model=llm_model)
        analysis = selection.analyzer.analyze(text)
        analyzer_used = selection.analyzer.name
        fallback_used = selection.fallback_used
        if isinstance(selection.analyzer, LLMLogAnalyzer):
            analyzer_used = selection.analyzer.last_effective_analyzer_name
            fallback_used = selection.fallback_used or selection.analyzer.last_fallback_used
        meta = AnalysisMeta(
            analyzer_used=analyzer_used,
            fallback_used=fallback_used,
            source_name=source_name,
        )
        report_markdown = None
        if include_report:
            parsed_log = parse_log(text, max_chars=self._settings.max_log_chars)
            report_markdown = self._report_service.render(
                analysis,
                meta=meta,
                log_excerpt=build_log_excerpt(parsed_log),
            )
        return AnalyzeResponse(analysis=analysis, report_markdown=report_markdown, meta=meta)

    @property
    def report_service(self) -> MarkdownReportService:
        return self._report_service

    def _select_analyzer(
        self,
        requested_mode: AnalyzerMode,
        *,
        llm_provider: str | None = None,
        llm_model: str | None = None,
    ) -> AnalyzerSelection:
        provider = (llm_provider or self._settings.llm_provider).lower()
        if requested_mode == AnalyzerMode.RULE_BASED:
            return AnalyzerSelection(analyzer=self._rule_based, fallback_used=False)
        if requested_mode == AnalyzerMode.MOCK:
            return AnalyzerSelection(analyzer=self._mock, fallback_used=False)
        if requested_mode == AnalyzerMode.LLM:
            return AnalyzerSelection(analyzer=self._llm, fallback_used=False)

        if self._settings.openai_api_key and provider == "openai":
            return AnalyzerSelection(analyzer=self._llm, fallback_used=False)
        return AnalyzerSelection(analyzer=self._mock, fallback_used=True)
