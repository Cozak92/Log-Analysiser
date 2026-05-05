from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_analyze_text_endpoint_returns_structured_response() -> None:
    response = client.post(
        "/analyze/text",
        json={
            "text": Path("samples/null_reference.log").read_text(encoding="utf-8"),
            "include_report": True,
            "analyzer_mode": "mock",
        },
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["analysis"]["error_type"] == "null_reference"
    assert "report_markdown" in payload
    assert payload["meta"]["analyzer_used"] == "mock"


def test_analyze_file_endpoint_accepts_upload() -> None:
    response = client.post(
        "/analyze/file",
        files={"file": ("db_timeout.log", Path("samples/db_timeout.log").read_bytes(), "text/plain")},
        data={"analyzer_mode": "rule-based", "include_report": "true"},
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["analysis"]["severity"] == "critical"
    assert payload["meta"]["source_name"] == "db_timeout.log"

