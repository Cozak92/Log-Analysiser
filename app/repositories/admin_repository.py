from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument

from app.config import Settings
from app.schemas.admin import DetectionRecord, KibanaSource


class AdminRepository(Protocol):
    def ensure_indexes(self) -> None:
        ...

    def upsert_source(
        self,
        *,
        kibana_url: str,
        data_view_name: str,
        analyzer_mode: str,
        llm_provider: str,
        llm_model: str | None,
    ) -> KibanaSource:
        ...

    def list_sources(self) -> list[KibanaSource]:
        ...

    def get_source(self, source_id: str) -> KibanaSource | None:
        ...

    def set_source_enabled(self, source_id: str, enabled: bool) -> KibanaSource | None:
        ...

    def update_source_poll_result(
        self,
        source_id: str,
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
        self._sources = self._db["kibana_sources"]
        self._detections = self._db["detections"]

    def ensure_indexes(self) -> None:
        self._sources.create_index(
            [("kibana_url", ASCENDING), ("data_view_name", ASCENDING)],
            unique=True,
            name="source_identity",
        )
        self._detections.create_index("fingerprint", unique=True, name="detection_fingerprint")
        self._detections.create_index([("last_seen_at", DESCENDING)], name="detection_last_seen")
        self._detections.create_index([("severity", ASCENDING), ("last_seen_at", DESCENDING)], name="detection_severity")

    def upsert_source(
        self,
        *,
        kibana_url: str,
        data_view_name: str,
        analyzer_mode: str,
        llm_provider: str,
        llm_model: str | None,
    ) -> KibanaSource:
        now = utc_now()
        doc = self._sources.find_one_and_update(
            {"kibana_url": kibana_url, "data_view_name": data_view_name},
            {
                "$setOnInsert": {
                    "created_at": now,
                    "last_status": "pending",
                    "last_fetched_count": 0,
                    "last_detected_count": 0,
                },
                "$set": {
                    "kibana_url": kibana_url,
                    "data_view_name": data_view_name,
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
        return source_from_doc(doc)

    def list_sources(self) -> list[KibanaSource]:
        docs = self._sources.find().sort("created_at", DESCENDING)
        return [source_from_doc(doc) for doc in docs]

    def get_source(self, source_id: str) -> KibanaSource | None:
        doc = self._sources.find_one({"_id": to_object_id(source_id)})
        return source_from_doc(doc) if doc else None

    def set_source_enabled(self, source_id: str, enabled: bool) -> KibanaSource | None:
        doc = self._sources.find_one_and_update(
            {"_id": to_object_id(source_id)},
            {"$set": {"enabled": enabled, "updated_at": utc_now()}},
            return_document=ReturnDocument.AFTER,
        )
        return source_from_doc(doc) if doc else None

    def update_source_poll_result(
        self,
        source_id: str,
        *,
        status: str,
        fetched_count: int,
        detected_count: int,
        error: str | None,
    ) -> None:
        self._sources.update_one(
            {"_id": to_object_id(source_id)},
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
                "$setOnInsert": {
                    **detection,
                    "created_at": now,
                    "seen_count": 0,
                },
                "$set": {"last_seen_at": now},
                "$inc": {"seen_count": 1},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return detection_from_doc(doc)

    def list_detections(self, *, limit: int = 100) -> list[DetectionRecord]:
        docs = self._detections.find().sort("last_seen_at", DESCENDING).limit(limit)
        return [detection_from_doc(doc) for doc in docs]


class InMemoryAdminRepository:
    def __init__(self) -> None:
        self._sources: dict[str, dict[str, Any]] = {}
        self._detections: dict[str, dict[str, Any]] = {}

    def ensure_indexes(self) -> None:
        return None

    def upsert_source(
        self,
        *,
        kibana_url: str,
        data_view_name: str,
        analyzer_mode: str,
        llm_provider: str,
        llm_model: str | None,
    ) -> KibanaSource:
        existing = next(
            (
                doc
                for doc in self._sources.values()
                if doc["kibana_url"] == kibana_url and doc["data_view_name"] == data_view_name
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
            return source_from_doc(existing)

        source_id = uuid4().hex
        doc = {
            "_id": source_id,
            "kibana_url": kibana_url,
            "data_view_name": data_view_name,
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
        self._sources[source_id] = doc
        return source_from_doc(doc)

    def list_sources(self) -> list[KibanaSource]:
        docs = sorted(self._sources.values(), key=lambda doc: doc["created_at"], reverse=True)
        return [source_from_doc(doc) for doc in docs]

    def get_source(self, source_id: str) -> KibanaSource | None:
        doc = self._sources.get(source_id)
        return source_from_doc(doc) if doc else None

    def set_source_enabled(self, source_id: str, enabled: bool) -> KibanaSource | None:
        doc = self._sources.get(source_id)
        if not doc:
            return None
        doc.update({"enabled": enabled, "updated_at": utc_now()})
        return source_from_doc(doc)

    def update_source_poll_result(
        self,
        source_id: str,
        *,
        status: str,
        fetched_count: int,
        detected_count: int,
        error: str | None,
    ) -> None:
        doc = self._sources.get(source_id)
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


def source_from_doc(doc: dict[str, Any]) -> KibanaSource:
    return KibanaSource(
        id=str(doc["_id"]),
        kibana_url=doc["kibana_url"],
        data_view_name=doc["data_view_name"],
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
        source_id=str(doc["source_id"]),
        kibana_url=doc["kibana_url"],
        data_view_name=doc["data_view_name"],
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
