from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import ValidationError

from app.analyzers.base import LogAnalyzer
from app.prompts.templates import build_analysis_system_prompt, build_analysis_user_prompt
from app.schemas.analysis import AnalysisResult


class ProviderNotConfiguredError(RuntimeError):
    """Raised when an LLM provider cannot be used in the current environment."""


class LLMProvider(ABC):
    name: str

    @abstractmethod
    def generate_analysis(self, *, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError


class OpenAICompatibleProviderStub(LLMProvider):
    name = "openai-compatible-stub"

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key

    def generate_analysis(self, *, system_prompt: str, user_prompt: str) -> str:
        if not self._api_key:
            raise ProviderNotConfiguredError("OPENAI_API_KEY is not configured.")
        raise ProviderNotConfiguredError(
            "OpenAI provider integration is intentionally left as a safe stub in MVP 1. "
            "Implement the HTTP call in this adapter when you are ready to connect a real provider."
        )


class LLMLogAnalyzer(LogAnalyzer):
    name = "llm"

    def __init__(self, provider: LLMProvider, fallback_analyzer: LogAnalyzer) -> None:
        self._provider = provider
        self._fallback_analyzer = fallback_analyzer
        self.last_fallback_used = False
        self.last_effective_analyzer_name = self.name

    def analyze(self, log_text: str) -> AnalysisResult:
        system_prompt = build_analysis_system_prompt()
        user_prompt = build_analysis_user_prompt(log_text)
        try:
            response = self._provider.generate_analysis(system_prompt=system_prompt, user_prompt=user_prompt)
            self.last_fallback_used = False
            self.last_effective_analyzer_name = self.name
            return AnalysisResult.model_validate_json(response)
        except (ProviderNotConfiguredError, ValidationError, ValueError):
            result = self._fallback_analyzer.analyze(log_text)
            self.last_fallback_used = True
            self.last_effective_analyzer_name = self._fallback_analyzer.name
            result.unknowns.append(
                "LLM provider was unavailable or returned invalid data, so the analyzer fell back to the safe local strategy."
            )
            return result
