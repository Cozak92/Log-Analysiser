from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.analysis import AnalysisResult


class LogAnalyzer(ABC):
    name: str

    @abstractmethod
    def analyze(self, log_text: str) -> AnalysisResult:
        raise NotImplementedError
