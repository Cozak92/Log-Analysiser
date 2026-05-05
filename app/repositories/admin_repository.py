from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.config import Settings
from app.schemas.admin import DetectionRecord, IntegrationType, ProjectIntegration


class AdminRepository(Protocol):
    def ensure_indexes(self) -> None:
        ...

    def upsert_integration(
        self,
        *,
        project_name: str,
        integration_type: str,
        endpoint_url: str,
        resource_name: str,
        analyzer_mode: str,
        llm_provider: str,
        llm_model: str | None,
    ) -> ProjectIntegration:
        ...

    def list_integrations(self) -> list[ProjectIntegration]:
        ...

    def get_integration(self, integration_id: str) -> ProjectIntegration | None:
        ...

    def update_integration(
        self,
        integration_id: str,
        *,
        project_name: str,
        integration_type: str,
        endpoint_url: str,
        resource_name: str,
        analyzer_mode: str,
        llm_provider: str,
        llm_model: str | None,
    ) -> ProjectIntegration | None:
        ...

    def set_integration_enabled(self, integration_id: str, enabled: bool) -> ProjectIntegration | None:
        ...

    def update_integration_poll_result(
        self,
        integration_id: str,
        *,
        status: str,
        fetched_count: int,
        detected_count: int,
        error: str | None,
    ) -> None:
        ...

    def upsert_detection(self, detection: dict[str, Any]) -> DetectionRecord:
        ...

    def list_detections(self, *, limit: int = 100) -> list[DetectionRecord]:
        ...


class MongoAdminRepository:
    def __init__(self, settings: Settings) -> None:
        self._client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=1_000)
        self._db = self._client[settings.mongo_db_name]
        self._integrations = self._db["project_integrations"]
        self._detections = self._db["detections"]

    def ensure_indexes(self) -> None:
        self._integrations.create_index(
            [
                ("project_name", ASCENDING),
                ("integration_type", ASCENDING),
                ("endpoint_url", ASCENDING),
                ("resource_name", ASCENDING),
            ],
            unique=True,
            name="project_integration_identity",
        )
        self._detections.create_index("fingerprint", unique=True, name="detection_fingerprint")
        self._detections.create_index([("last_seen_at", DESCENDING)], name="detection_last_seen")
        self._detections.create_index([("project_name", ASCENDING), ("last_seen_at", DESCENDING)], name="detection_project")
        self._detections.create_index([("severity", ASCENDING), ("last_seen_at", DESCENDING)], name="detection_severity")

    def upsert_integration(
        self,
        *,
        project_name: str,
        integration_type: str,
        endpoint_url: str,
        resource_name: str,
        analyzer_mode: str,
        llm_provider: str,
        llm_model: str | None,
    ) -> ProjectIntegration:
        now = utc_now()
        identity = {
            "project_name": project_name,
            "integration_type": integration_type,
            "endpoint_url": endpoint_url,
            "resource_name": resource_name,
        }
        doc = self._integrations.find_one_and_update(
            identity,
            {
                "$setOnInsert": {
                    "created_at": now,
                    "last_status": "pending",
                    "last_fetched_count": 0,
                    "last_detected_count": 0,
                },
                "$set": {
                    **identity,
                    "analyzer_mode": analyzer_mode,
                    "llm_provider": llm_provider,
                    "llm_model": llm_model,
                    "enabled": True,
                    "updated_at": now,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return integration_from_doc(doc)

    def list_integrations(self) -> list[ProjectIntegration]:
        docs = self._integrations.find().sort([("project_name", ASCENDING), ("created_at", DESCENDING)])
        return [integration_from_doc(doc) for doc in docs]

    def get_integration(self, integration_id: str) -> ProjectIntegration | None:
        doc = self._integrations.find_one({"_id": to_object_id(integration_id)})
        return integration_from_doc(doc) if doc else None

    def update_integration(
        self,
        integration_id: str,
        *,
        project_name: str,
        integration_type: str,
        endpoint_url: str,
        resource_name: str,
        analyzer_mode: str,
        llm_provider: str,
        llm_model: str | None,
    ) -> ProjectIntegration | None:
        now = utc_now()
        doc = self._integrations.find_one_and_update(
            {"_id": to_object_id(integration_id)},
            {
                "$set": {
                    "project_name": project_name,
                    "integration_type": integration_type,
                    "endpoint_url": endpoint_url,
                    "resource_name": resource_name,
                    "analyzer_mode": analyzer_mode,
                    "llm_provider": llm_provider,
                    "llm_model": llm_model,
                    "last_status": "pending",
                    "last_error": None,
                    "last_fetched_count": 0,
                    "last_detected_count": 0,
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return integration_from_doc(doc) if doc else None

    def set_integration_enabled(self, integration_id: str, enabled: bool) -> ProjectIntegration | None:
        now = utc_now()
        updates: dict[str, Any] = {"enabled": enabled, "updated_at": now}
        if enabled:
            updates.update({"last_status": "pending", "last_error": None})
        else:
            updates.update({"last_status": "disabled", "last_error": None})

        doc = self._integrations.find_one_and_update(
            {"_id": to_object_id(integration_id)},
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )
        return integration_from_doc(doc) if doc else None

    def update_integration_poll_result(
        self,
        integration_id: str,
        *,
        status: str,
        fetched_count: int,
        detected_count: int,
        error: str | None,
    ) -> None:
        self._integrations.update_one(
            {"_id": to_object_id(integration_id)},
            {
                "$set": {
                    "last_polled_at": utc_now(),
                    "last_status": status,
                    "last_error": error,
                    "last_fetched_count": fetched_count,
                    "last_detected_count": detected_count,
                    "updated_at": utc_now(),
                }
            },
        )

    def upsert_detection(self, detection: dict[str, Any]) -> DetectionRecord:
        now = utc_now()
        doc = self._detections.find_one_and_update(
            {"fingerprint": detection["fingerprint"]},
            {
                "$set": {"last_seen_at": now},
                "$inc": {"seen_count": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
        if doc:
            return detection_from_doc(doc)

        doc = {
            **detection,
            "created_at": now,
            "last_seen_at": now,
            "seen_count": 1,
        }
        try:
            result = self._detections.insert_one(doc)
        except DuplicateKeyError:
            doc = self._detections.find_one_and_update(
                {"fingerprint": detection["fingerprint"]},
                {
                    "$set": {"last_seen_at": now},
                    "$inc": {"seen_count": 1},
                },
                return_document=ReturnDocument.AFTER,
            )
            if doc:
                return detection_from_doc(doc)
            raise

        doc["_id"] = result.inserted_id
        return detection_from_doc(doc)

    def list_detections(self, *, limit: int = 100) -> list[DetectionRecord]:
        docs = self._detections.find().sort("last_seen_at", DESCENDING).limit(limit)
        return [detection_from_doc(doc) for doc in docs]


class InMemoryAdminRepository:
    def __init__(self) -> None:
        self._integrations: dict[str, dict[str, Any]] = {}
        self._detections: dict[str, dict[str, Any]] = {}

    def ensure_indexes(self) -> None:
        return None

    def upsert_integration(
        self,
        *,
        project_name: str,
        integration_type: str,
        endpoint_url: str,
        resource_name: str,
        analyzer_mode: str,
        llm_provider: str,
        llm_model: str | None,
    ) -> ProjectIntegration:
        existing = next(
            (
                doc
                for doc in self._integrations.values()
                if doc["project_name"] == project_name
                and doc["integration_type"] == integration_type
                and doc["endpoint_url"] == endpoint_url
                and doc["resource_name"] == resource_name
            ),
            None,
        )
        now = utc_now()
        if existing:
            existing.update(
                {
                    "analyzer_mode": analyzer_mode,
                    "llm_provider": llm_provider,
                    "llm_model": llm_model,
                    "enabled": True,
                    "updated_at": now,
                }
            )
            return integration_from_doc(existing)

        integration_id = uuid4().hex
        doc = {
            "_id": integration_id,
            "project_name": project_name,
            "integration_type": integration_type,
            "endpoint_url": endpoint_url,
            "resource_name": resource_name,
            "analyzer_mode": analyzer_mode,
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "enabled": True,
            "created_at": now,
            "updated_at": now,
            "last_status": "pending",
            "last_fetched_count": 0,
            "last_detected_count": 0,
        }
        self._integrations[integration_id] = doc
        return integration_from_doc(doc)

    def list_integrations(self) -> list[ProjectIntegration]:
        docs = sorted(self._integrations.values(), key=lambda doc: (doc["project_name"], doc["created_at"]))
        return [integration_from_doc(doc) for doc in docs]

    def get_integration(self, integration_id: str) -> ProjectIntegration | None:
        doc = self._integrations.get(integration_id)
        return integration_from_doc(doc) if doc else None

    def update_integration(
        self,
        integration_id: str,
        *,
        project_name: str,
        integration_type: str,
        endpoint_url: str,
        resource_name: str,
        analyzer_mode: str,
        llm_provider: str,
        llm_model: str | None,
    ) -> ProjectIntegration | None:
        doc = self._integrations.get(integration_id)
        if not doc:
            return None
        doc.update(
            {
                "project_name": project_name,
                "integration_type": integration_type,
                "endpoint_url": endpoint_url,
                "resource_name": resource_name,
                "analyzer_mode": analyzer_mode,
                "llm_provider": llm_provider,
                "llm_model": llm_model,
                "last_status": "pending",
                "last_error": None,
                "last_fetched_count": 0,
                "last_detected_count": 0,
                "updated_at": utc_now(),
            }
        )
        return integration_from_doc(doc)

    def set_integration_enabled(self, integration_id: str, enabled: bool) -> ProjectIntegration | None:
        doc = self._integrations.get(integration_id)
        if not doc:
            return None
        doc.update(
            {
                "enabled": enabled,
                "updated_at": utc_now(),
                "last_status": "pending" if enabled else "disabled",
                "last_error": None,
            }
        )
        return integration_from_doc(doc)

    def update_integration_poll_result(
        self,
        integration_id: str,
        *,
        status: str,
        fetched_count: int,
        detected_count: int,
        error: str | None,
    ) -> None:
        doc = self._integrations.get(integration_id)
        if not doc:
            return
        doc.update(
            {
                "last_polled_at": utc_now(),
                "last_status": status,
                "last_error": error,
                "last_fetched_count": fetched_count,
                "last_detected_count": detected_count,
                "updated_at": utc_now(),
            }
        )

    def upsert_detection(self, detection: dict[str, Any]) -> DetectionRecord:
        now = utc_now()
        existing = self._detections.get(detection["fingerprint"])
        if existing:
            existing["last_seen_at"] = now
            existing["seen_count"] += 1
            return detection_from_doc(existing)

        doc = {
            "_id": uuid4().hex,
            **detection,
            "created_at": now,
            "last_seen_at": now,
            "seen_count": 1,
        }
        self._detections[detection["fingerprint"]] = doc
        return detection_from_doc(doc)

    def list_detections(self, *, limit: int = 100) -> list[DetectionRecord]:
        docs = sorted(self._detections.values(), key=lambda doc: doc["last_seen_at"], reverse=True)
        return [detection_from_doc(doc) for doc in docs[:limit]]


def build_admin_repository(settings: Settings) -> AdminRepository:
    if settings.mongo_uri == "memory://":
        return InMemoryAdminRepository()
    return MongoAdminRepository(settings)


def integration_from_doc(doc: dict[str, Any]) -> ProjectIntegration:
    return ProjectIntegration(
        id=str(doc["_id"]),
        project_name=doc.get("project_name", "DEFAULT"),
        integration_type=doc.get("integration_type", IntegrationType.KIBANA.value),
        endpoint_url=doc.get("endpoint_url", doc.get("kibana_url", "")),
        resource_name=doc.get("resource_name", doc.get("data_view_name", "")),
        analyzer_mode=doc.get("analyzer_mode", "auto"),
        llm_provider=doc.get("llm_provider", "mock"),
        llm_model=doc.get("llm_model"),
        enabled=bool(doc.get("enabled", True)),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
        last_polled_at=doc.get("last_polled_at"),
        last_status=doc.get("last_status", "pending"),
        last_error=doc.get("last_error"),
        last_fetched_count=int(doc.get("last_fetched_count", 0)),
        last_detected_count=int(doc.get("last_detected_count", 0)),
    )


def detection_from_doc(doc: dict[str, Any]) -> DetectionRecord:
    return DetectionRecord(
        id=str(doc["_id"]),
        integration_id=str(doc.get("integration_id", doc.get("source_id", ""))),
        project_name=doc.get("project_name", "DEFAULT"),
        integration_type=doc.get("integration_type", IntegrationType.KIBANA.value),
        endpoint_url=doc.get("endpoint_url", doc.get("kibana_url", "")),
        resource_name=doc.get("resource_name", doc.get("data_view_name", "")),
        summary=doc["summary"],
        severity=doc["severity"],
        error_type=doc["error_type"],
        analyzer_used=doc["analyzer_used"],
        llm_provider=doc.get("llm_provider", "mock"),
        llm_model=doc.get("llm_model"),
        fallback_used=bool(doc["fallback_used"]),
        raw_log=doc["raw_log"],
        report_markdown=doc.get("report_markdown"),
        created_at=doc["created_at"],
        last_seen_at=doc["last_seen_at"],
        seen_count=int(doc.get("seen_count", 1)),
    )


def to_object_id(value: str) -> ObjectId | str:
    if ObjectId.is_valid(value):
        return ObjectId(value)
    return value


def utc_now() -> datetime:
    return datetime.now(UTC)
