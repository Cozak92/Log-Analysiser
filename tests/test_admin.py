from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def build_client() -> TestClient:
    app = create_app(
        Settings(
            mongo_uri="memory://",
            kibana_poll_enabled=False,
            default_analyzer_mode="mock",
        )
    )
    return TestClient(app)


def test_admin_page_loads() -> None:
    with build_client() as client:
        response = client.get("/admin")

    assert response.status_code == 200
    assert "Kibana Polling Admin" in response.text
    assert 'id="custom-provider-input"' in response.text
    assert "disabled" in response.text


def test_admin_can_create_demo_source_and_poll_detection() -> None:
    with build_client() as client:
        create_response = client.post(
            "/admin/sources",
            data={
                "kibana_url": "demo://local",
                "data_view_name": "db-*",
                "analyzer_mode": "mock",
                "llm_provider": "openai",
                "llm_model": "gpt-test",
            },
            follow_redirects=False,
        )
        poll_response = client.post("/admin/api/poll-now")
        summary_response = client.get("/admin/api/summary")

    assert create_response.status_code == 303
    assert poll_response.status_code == 200
    assert poll_response.json()[0]["detected_count"] >= 1
    assert summary_response.json()["sources"][0]["llm_provider"] == "openai"
    assert summary_response.json()["sources"][0]["llm_model"] == "gpt-test"
    assert summary_response.json()["detections"][0]["severity"] == "critical"
    assert summary_response.json()["detections"][0]["llm_provider"] == "openai"


def test_admin_api_accepts_custom_llm_provider() -> None:
    with build_client() as client:
        create_response = client.post(
            "/admin/api/sources",
            json={
                "kibana_url": "demo://local",
                "data_view_name": "payments-*",
                "analyzer_mode": "llm",
                "llm_provider": "custom",
                "custom_llm_provider": "internal-gateway",
                "llm_model": "incident-model-v1",
            },
        )
        summary_response = client.get("/admin/api/summary")

    assert create_response.status_code == 200
    source = summary_response.json()["sources"][0]
    assert source["analyzer_mode"] == "llm"
    assert source["llm_provider"] == "internal-gateway"
    assert source["llm_model"] == "incident-model-v1"
