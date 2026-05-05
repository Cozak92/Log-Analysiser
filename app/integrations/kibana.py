from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.integrations.base import FetchedLog, IntegrationFetchResult
from app.schemas.admin import ProjectIntegration


class KibanaLogFetcher:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def fetch_recent_logs(self, integration: ProjectIntegration) -> IntegrationFetchResult:
        if integration.endpoint_url.startswith("demo://"):
            return IntegrationFetchResult(logs=self._load_demo_logs(integration))

        base_url = integration.endpoint_url.rstrip("/")
        search_url = f"{base_url}/internal/search/es"
        payload = {
            "params": {
                "index": integration.resource_name,
                "body": {
                    "size": self._settings.kibana_batch_size,
                    "sort": [{"@timestamp": {"order": "desc", "unmapped_type": "date"}}],
                    "query": {
                        "bool": {
                            "filter": [
                                {
                                    "range": {
                                        "@timestamp": {
                                            "gte": f"now-{self._settings.poll_interval_seconds}s",
                                            "lte": "now",
                                        }
                                    }
                                }
                            ]
                        }
                    },
                },
            }
        }

        try:
            async with httpx.AsyncClient(timeout=self._settings.kibana_request_timeout_seconds) as client:
                response = await client.post(
                    search_url,
                    json=payload,
                    headers={"kbn-xsrf": "log-analysis-mvp", "Content-Type": "application/json"},
                )
            if response.status_code >= 400:
                return IntegrationFetchResult(
                    logs=[],
                    error=f"Kibana returned HTTP {response.status_code}: {response.text[:300]}",
                )

            hits = self._extract_hits(response.json())
            return IntegrationFetchResult(logs=[self._hit_to_log(hit, integration) for hit in hits])
        except Exception as exc:
            return IntegrationFetchResult(logs=[], error=f"Kibana fetch failed: {exc}")

    def _extract_hits(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        candidates = [
            payload.get("rawResponse", {}).get("hits", {}).get("hits"),
            payload.get("hits", {}).get("hits"),
            payload.get("response", {}).get("hits", {}).get("hits"),
        ]
        for candidate in candidates:
            if isinstance(candidate, list):
                return [item for item in candidate if isinstance(item, dict)]
        return []

    def _hit_to_log(self, hit: dict[str, Any], integration: ProjectIntegration) -> FetchedLog:
        source = hit.get("_source") if isinstance(hit.get("_source"), dict) else hit
        external_id = str(hit.get("_id")) if hit.get("_id") else None
        return FetchedLog(
            raw_log=build_kibana_analysis_payload(
                integration=integration,
                source=source,
                external_id=external_id,
            ),
            external_id=external_id,
        )

    def _load_demo_logs(self, integration: ProjectIntegration) -> list[FetchedLog]:
        sample_dir = Path("samples")
        sample_name = "db_timeout.log" if "db" in integration.resource_name.lower() else "null_reference.log"
        sample_path = sample_dir / sample_name
        external_id = f"demo:{sample_name}"
        if sample_path.exists():
            sample_text = sample_path.read_text(encoding="utf-8")
            source = {
                "@timestamp": "demo",
                "log": {"level": "ERROR"},
                "service": {"name": integration.project_name.lower()},
                "message": sample_text,
                "error": {"message": sample_text, "stack_trace": sample_text},
            }
            return [
                FetchedLog(
                    raw_log=build_kibana_analysis_payload(
                        integration=integration,
                        source=source,
                        external_id=external_id,
                    ),
                    external_id=external_id,
                )
            ]
        source = {
            "@timestamp": "demo",
            "log": {"level": "ERROR"},
            "message": "status=500\nAttributeError: 'NoneType' object has no attribute 'email'",
            "error": {"message": "AttributeError: 'NoneType' object has no attribute 'email'"},
            "http": {"response": {"status_code": 500}},
        }
        return [
            FetchedLog(
                raw_log=build_kibana_analysis_payload(
                    integration=integration,
                    source=source,
                    external_id="demo:inline",
                ),
                external_id="demo:inline",
            )
        ]


def build_kibana_analysis_payload(
    *,
    integration: ProjectIntegration,
    source: dict[str, Any],
    external_id: str | None = None,
) -> str:
    selected_fields: dict[str, Any] = {}
    missing_fields: list[str] = []
    for field in integration.focus_fields:
        value = nested_get(source, field)
        if value in (None, ""):
            missing_fields.append(field)
            continue
        selected_fields[field] = value

    payload = {
        "analysis_input_version": "kibana.focus_fields.v1",
        "project": integration.project_name,
        "integration": {
            "id": integration.id,
            "type": integration.integration_type.value,
            "resource_name": integration.resource_name,
            "external_id": external_id,
        },
        "focus_fields": integration.focus_fields,
        "selected_fields": selected_fields,
        "missing_fields": missing_fields,
        "llm_instruction": "Analyze the selected Kibana fields first. Treat missing fields as unavailable evidence, not proof that the error is absent.",
    }
    if not selected_fields:
        payload["fallback_source_excerpt"] = json.dumps(source, ensure_ascii=False, default=str)[:4_000]
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def first_present(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = nested_get(payload, key)
        if value not in (None, ""):
            return value
    return None


def nested_get(payload: dict[str, Any], dotted_key: str) -> Any:
    if dotted_key in payload:
        return payload[dotted_key]

    current: Any = payload
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current
