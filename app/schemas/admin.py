from __future__ import annotations

from datetime import datetime
from enum import Enum

import re

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.analysis import AnalyzerMode

REPRESENTATIVE_LLM_PROVIDERS = (
    "mock",
    "openai",
    "anthropic",
    "gemini",
    "azure-openai",
    "bedrock",
    "vertex-ai",
    "openrouter",
    "ollama",
    "custom",
)


class IntegrationType(str, Enum):
    KIBANA = "kibana"
    SENTRY = "sentry"


SUPPORTED_INTEGRATION_TYPES = (IntegrationType.KIBANA.value,)
PLANNED_INTEGRATION_TYPES = (IntegrationType.SENTRY.value,)


class ProjectIntegrationCreate(BaseModel):
    project_name: str = Field(min_length=1, max_length=80)
    integration_type: IntegrationType = IntegrationType.KIBANA
    endpoint_url: str = Field(min_length=1, max_length=500)
    resource_name: str = Field(min_length=1, max_length=200)
    analyzer_mode: AnalyzerMode = AnalyzerMode.AUTO
    llm_provider: str = Field(default="mock", max_length=80)
    custom_llm_provider: str | None = Field(default=None, max_length=80)
    llm_model: str | None = Field(default=None, max_length=120)

    @field_validator("project_name")
    @classmethod
    def normalize_project_name(cls, value: str) -> str:
        normalized = re.sub(r"\s+", " ", value.strip()).upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9._ -]{0,79}", normalized):
            raise ValueError("project_name must start with a letter or number and use letters, numbers, spaces, dots, underscores, or hyphens")
        return normalized

    @field_validator("endpoint_url")
    @classmethod
    def normalize_endpoint_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized:
            raise ValueError("endpoint_url must not be empty")
        return normalized

    @field_validator("resource_name")
    @classmethod
    def normalize_resource_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("resource_name must not be empty")
        return normalized

    @field_validator("llm_provider")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("llm_provider must not be empty")
        return normalized

    @field_validator("custom_llm_provider")
    @classmethod
    def normalize_custom_provider(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        return normalized or None

    @field_validator("llm_model")
    @classmethod
    def normalize_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_integration(self) -> "ProjectIntegrationCreate":
        if self.integration_type == IntegrationType.KIBANA and not self.endpoint_url.startswith(
            ("http://", "https://", "demo://")
        ):
            raise ValueError("Kibana endpoint_url must start with http://, https://, or demo://")

        if self.integration_type == IntegrationType.SENTRY and not self.endpoint_url.startswith(("http://", "https://")):
            raise ValueError("Sentry endpoint_url must start with http:// or https://")

        if self.llm_provider == "custom":
            if not self.custom_llm_provider:
                raise ValueError("custom_llm_provider is required when llm_provider is custom")
            self.llm_provider = self.custom_llm_provider

        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,79}", self.llm_provider):
            raise ValueError("llm_provider must use lowercase letters, numbers, dots, underscores, or hyphens")
        return self


class ProjectIntegration(BaseModel):
    id: str
    project_name: str
    integration_type: IntegrationType
    endpoint_url: str
    resource_name: str
    analyzer_mode: AnalyzerMode = AnalyzerMode.AUTO
    llm_provider: str = "mock"
    llm_model: str | None = None
    enabled: bool
    created_at: datetime
    updated_at: datetime
    last_polled_at: datetime | None = None
    last_status: str = "pending"
    last_error: str | None = None
    last_fetched_count: int = 0
    last_detected_count: int = 0


class DetectionRecord(BaseModel):
    id: str
    integration_id: str
    project_name: str
    integration_type: IntegrationType
    endpoint_url: str
    resource_name: str
    summary: str
    severity: str
    error_type: str
    analyzer_used: str
    llm_provider: str
    llm_model: str | None = None
    fallback_used: bool
    raw_log: str
    report_markdown: str | None = None
    created_at: datetime
    last_seen_at: datetime
    seen_count: int = 1


class PollResult(BaseModel):
    integration_id: str
    status: str
    fetched_count: int = 0
    detected_count: int = 0
    error: str | None = None


class ProjectSummary(BaseModel):
    name: str
    integration_count: int = 0
    enabled_integration_count: int = 0


class AdminSummary(BaseModel):
    projects: list[ProjectSummary]
    integrations: list[ProjectIntegration]
    detections: list[DetectionRecord]
