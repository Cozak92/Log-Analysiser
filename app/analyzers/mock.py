from __future__ import annotations

from app.analyzers.base import LogAnalyzer
from app.analyzers.rule_based import RuleBasedAnalyzer
from app.schemas.analysis import AnalysisResult


class MockAnalyzer(LogAnalyzer):
    name = "mock"

    def __init__(self, baseline_analyzer: RuleBasedAnalyzer | None = None) -> None:
        self._baseline_analyzer = baseline_analyzer or RuleBasedAnalyzer()

    def analyze(self, log_text: str) -> AnalysisResult:
        result = self._baseline_analyzer.analyze(log_text)
        result.summary = f"{result.summary} Mock analyzer generated the final suggestion set without calling an external LLM."
        result.unknowns.append("No external LLM provider was used, so prioritization is purely heuristic in this MVP mode.")
        return result

