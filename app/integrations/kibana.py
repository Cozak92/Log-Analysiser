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
            return IntegrationFetchResult(logs=self._load_demo_logs(integration.resource_name))

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
            return IntegrationFetchResult(logs=[self._hit_to_log(hit) for hit in hits])
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

    def _hit_to_log(self, hit: dict[str, Any]) -> FetchedLog:
        source = hit.get("_source") if isinstance(hit.get("_source"), dict) else hit
        timestamp = first_present(source, "@timestamp", "timestamp", "time")
        level = first_present(source, "level", "log.level", "severity")
        service = first_present(source, "service.name", "service", "app")
        message = first_present(source, "message", "log", "error.message")
        stack = first_present(source, "error.stack_trace", "stack_trace", "exception")
        status = first_present(source, "http.response.status_code", "status", "status_code")

        parts = [
            str(value)
            for value in [timestamp, level, service, f"status={status}" if status else None, message, stack]
            if value
        ]
        if not parts:
            parts = [json.dumps(source, ensure_ascii=False, default=str)]

        return FetchedLog(raw_log="\n".join(parts), external_id=str(hit.get("_id")) if hit.get("_id") else None)

    def _load_demo_logs(self, resource_name: str) -> list[FetchedLog]:
        sample_dir = Path("samples")
        sample_name = "db_timeout.log" if "db" in resource_name.lower() else "null_reference.log"
        sample_path = sample_dir / sample_name
        if sample_path.exists():
            return [FetchedLog(raw_log=sample_path.read_text(encoding="utf-8"), external_id=f"demo:{sample_name}")]
        return [
            FetchedLog(
                raw_log="status=500\nAttributeError: 'NoneType' object has no attribute 'email'",
                external_id="demo:inline",
            )
        ]


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
