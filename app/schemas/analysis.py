from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class SeverityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AnalyzerMode(str, Enum):
    AUTO = "auto"
    RULE_BASED = "rule-based"
    MOCK = "mock"
    LLM = "llm"


class RootCauseCandidate(BaseModel):
    title: str
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class FixSuggestion(BaseModel):
    title: str
    description: str
    example_patch: str


class AnalysisResult(BaseModel):
    summary: str
    severity: SeverityLevel
    error_type: str
    keywords: list[str] = Field(default_factory=list)
    root_cause_candidates: list[RootCauseCandidate] = Field(default_factory=list)
    impact: str
    reproduction_steps: list[str] = Field(default_factory=list)
    immediate_checks: list[str] = Field(default_factory=list)
    fix_suggestions: list[FixSuggestion] = Field(default_factory=list)
    test_suggestions: list[str] = Field(default_factory=list)
    verification_steps: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    parser_notes: list[str] = Field(default_factory=list)

    @field_validator("keywords")
    @classmethod
    def limit_keywords(cls, value: list[str]) -> list[str]:
        unique: list[str] = []
        for item in value:
            cleaned = item.strip()
            if cleaned and cleaned not in unique:
                unique.append(cleaned)
            if len(unique) == 10:
                break
        return unique


class AnalysisMeta(BaseModel):
    analyzer_used: str
    fallback_used: bool = False
    source_name: str | None = None


class AnalyzeTextRequest(BaseModel):
    text: str = Field(min_length=1)
    source_name: str | None = None
    analyzer_mode: AnalyzerMode = AnalyzerMode.AUTO
    include_report: bool = True


class AnalyzeResponse(BaseModel):
    analysis: AnalysisResult
    report_markdown: str | None = None
    meta: AnalysisMeta


class HealthResponse(BaseModel):
    status: str = "ok"
