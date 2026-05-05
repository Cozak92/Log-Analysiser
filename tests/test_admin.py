from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def build_client() -> TestClient:
    app = create_app(
        Settings(
            mongo_uri="memory://",
            polling_enabled=False,
            default_analyzer_mode="mock",
        )
    )
    return TestClient(app)


def test_admin_page_loads() -> None:
    with build_client() as client:
        response = client.get("/admin")

    assert response.status_code == 200
    assert "Project Observability Admin" in response.text
    assert "Latest Detections By Project" in response.text
    assert 'id="custom-provider-input"' in response.text
    assert "disabled" in response.text


def test_admin_can_create_project_integration_and_poll_detection() -> None:
    with build_client() as client:
        create_response = client.post(
            "/admin/integrations",
            data={
                "project_name": "GOA",
                "integration_type": "kibana",
                "endpoint_url": "demo://local",
                "resource_name": "db-*",
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
    assert summary_response.json()["projects"][0]["name"] == "GOA"
    assert summary_response.json()["integrations"][0]["project_name"] == "GOA"
    assert summary_response.json()["integrations"][0]["llm_provider"] == "openai"
    assert summary_response.json()["integrations"][0]["llm_model"] == "gpt-test"
    assert summary_response.json()["detections"][0]["severity"] == "critical"
    assert summary_response.json()["detections"][0]["project_name"] == "GOA"
    assert summary_response.json()["detections"][0]["llm_provider"] == "openai"

    with build_client() as client:
        client.post(
            "/admin/integrations",
            data={
                "project_name": "DOBO",
                "integration_type": "kibana",
                "endpoint_url": "demo://local",
                "resource_name": "payments-*",
                "analyzer_mode": "mock",
                "llm_provider": "mock",
            },
        )
        client.post("/admin/api/poll-now")
        detections_page = client.get("/admin/detections")

    assert "Detected Anomalies By Project" in detections_page.text
    assert "DOBO" in detections_page.text


def test_admin_api_accepts_custom_llm_provider() -> None:
    with build_client() as client:
        create_response = client.post(
            "/admin/api/integrations",
            json={
                "project_name": "dobo",
                "integration_type": "kibana",
                "endpoint_url": "demo://local",
                "resource_name": "payments-*",
                "analyzer_mode": "llm",
                "llm_provider": "custom",
                "custom_llm_provider": "internal-gateway",
                "llm_model": "incident-model-v1",
            },
        )
        summary_response = client.get("/admin/api/summary")

    assert create_response.status_code == 200
    integration = summary_response.json()["integrations"][0]
    assert integration["project_name"] == "DOBO"
    assert integration["analyzer_mode"] == "llm"
    assert integration["llm_provider"] == "internal-gateway"
    assert integration["llm_model"] == "incident-model-v1"
