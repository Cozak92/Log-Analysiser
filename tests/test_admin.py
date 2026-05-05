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
    assert 'href="/admin/integrations"' in response.text


def test_integration_page_loads_dynamic_type_fields() -> None:
    with build_client() as client:
        response = client.get("/admin/integrations")

    assert response.status_code == 200
    assert "Project Integrations" in response.text
    assert 'id="integration-type-select"' in response.text
    assert "integrationFieldConfig" in response.text
    assert "Sentry URL" in response.text
    assert "Data view name" in response.text
    assert 'id="focus-fields-input"' in response.text
    assert "Kibana focus fields" in response.text
    assert "selected_fields JSON" in response.text
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
        summary_response = client.get("/admin/api/summary")

    assert create_response.status_code == 303
    assert create_response.headers["location"] == "/admin/integrations"
    assert summary_response.json()["projects"][0]["name"] == "GOA"
    assert summary_response.json()["integrations"][0]["project_name"] == "GOA"
    assert summary_response.json()["integrations"][0]["llm_provider"] == "openai"
    assert summary_response.json()["integrations"][0]["llm_model"] == "gpt-test"
    assert "message" in summary_response.json()["integrations"][0]["focus_fields"]
    assert summary_response.json()["integrations"][0]["last_status"] == "ok"
    assert summary_response.json()["integrations"][0]["last_fetched_count"] == 1
    assert summary_response.json()["integrations"][0]["last_detected_count"] == 1
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

    assert "Detected Anomalies" in detections_page.text
    assert 'name="project"' in detections_page.text
    assert 'id="refresh-select"' in detections_page.text
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
    assert integration["last_status"] == "ok"


def test_kibana_focus_fields_are_stored_and_sent_as_json_payload() -> None:
    with build_client() as client:
        create_response = client.post(
            "/admin/api/integrations",
            json={
                "project_name": "GOA",
                "integration_type": "kibana",
                "endpoint_url": "demo://local",
                "resource_name": "db-*",
                "analyzer_mode": "mock",
                "llm_provider": "mock",
                "focus_fields": ["@timestamp", "message", "error.stack_trace"],
            },
        )
        summary_response = client.get("/admin/api/summary")

    integration = summary_response.json()["integrations"][0]
    raw_log = summary_response.json()["detections"][0]["raw_log"]
    assert create_response.status_code == 200
    assert integration["focus_fields"] == ["@timestamp", "message", "error.stack_trace"]
    assert '"analysis_input_version": "kibana.focus_fields.v1"' in raw_log
    assert '"focus_fields": [' in raw_log
    assert '"selected_fields": {' in raw_log
    assert '"error.stack_trace"' in raw_log
    assert "OperationalError" in raw_log


def test_admin_api_accepts_sentry_integration_shape() -> None:
    with build_client() as client:
        create_response = client.post(
            "/admin/api/integrations",
            json={
                "project_name": "GOA",
                "integration_type": "sentry",
                "endpoint_url": "https://sentry.example.com",
                "resource_name": "goa-api",
                "analyzer_mode": "mock",
                "llm_provider": "mock",
            },
        )
        summary_response = client.get("/admin/api/summary")

    integration = summary_response.json()["integrations"][0]
    assert create_response.status_code == 200
    assert integration["integration_type"] == "sentry"
    assert integration["resource_name"] == "goa-api"
    assert integration["last_status"] == "error"
    assert "no fetcher is implemented yet" in integration["last_error"]


def test_registered_integration_can_be_edited() -> None:
    with build_client() as client:
        create_response = client.post(
            "/admin/api/integrations",
            json={
                "project_name": "GOA",
                "integration_type": "kibana",
                "endpoint_url": "demo://local",
                "resource_name": "db-*",
                "analyzer_mode": "mock",
                "llm_provider": "mock",
            },
        )
        integration_id = create_response.json()["id"]
        edit_page = client.get(f"/admin/integrations?edit={integration_id}")
        update_response = client.post(
            f"/admin/integrations/{integration_id}/edit",
            data={
                "project_name": "DOBO",
                "integration_type": "kibana",
                "endpoint_url": "demo://local",
                "resource_name": "payments-*",
                "analyzer_mode": "mock",
                "llm_provider": "openai",
                "llm_model": "gpt-test",
                "focus_fields": "message\nerror.message",
            },
            follow_redirects=False,
        )
        summary_response = client.get("/admin/api/summary")

    integration = summary_response.json()["integrations"][0]
    assert edit_page.status_code == 200
    assert "Edit Integration" in edit_page.text
    assert f'action="/admin/integrations/{integration_id}/edit"' in edit_page.text
    assert update_response.status_code == 303
    assert integration["project_name"] == "DOBO"
    assert integration["resource_name"] == "payments-*"
    assert integration["llm_provider"] == "openai"
    assert integration["llm_model"] == "gpt-test"
    assert integration["focus_fields"] == ["message", "error.message"]
    assert integration["last_status"] == "ok"


def test_detection_list_filters_by_project_and_exposes_error_anchors() -> None:
    with build_client() as client:
        client.post(
            "/admin/api/integrations",
            json={
                "project_name": "GOA",
                "integration_type": "kibana",
                "endpoint_url": "demo://local",
                "resource_name": "db-*",
                "analyzer_mode": "mock",
                "llm_provider": "mock",
            },
        )
        client.post(
            "/admin/api/integrations",
            json={
                "project_name": "DOBO",
                "integration_type": "kibana",
                "endpoint_url": "demo://local",
                "resource_name": "payments-*",
                "analyzer_mode": "mock",
                "llm_provider": "mock",
            },
        )
        summary_response = client.get("/admin/api/summary")
        goa_detection = next(
            detection for detection in summary_response.json()["detections"] if detection["project_name"] == "GOA"
        )
        home_response = client.get("/admin")
        filtered_response = client.get("/admin/detections?project=GOA")
        refresh_response = client.get("/admin/detections?project=GOA&refresh=10")

    assert f'/admin/detections?project=GOA#detection-{goa_detection["id"]}' in home_response.text
    assert 'name="project"' in filtered_response.text
    assert '<option value="GOA" selected>GOA</option>' in filtered_response.text
    assert f'id="detection-{goa_detection["id"]}"' in filtered_response.text
    assert f'href="#detection-{goa_detection["id"]}"' in filtered_response.text
    assert "db_connection_error" in filtered_response.text
    assert '<option value="10" selected>Every 10s</option>' in refresh_response.text
    assert 'id="filter-refresh-input" value="10"' in refresh_response.text


def test_detection_list_normalizes_unknown_refresh_interval() -> None:
    with build_client() as client:
        response = client.get("/admin/detections?refresh=5")

    assert response.status_code == 200
    assert '<option value="off" selected>Off</option>' in response.text


def test_poll_now_reuses_existing_detection_and_increments_seen_count() -> None:
    with build_client() as client:
        client.post(
            "/admin/api/integrations",
            json={
                "project_name": "GOA",
                "integration_type": "kibana",
                "endpoint_url": "demo://local",
                "resource_name": "db-*",
                "analyzer_mode": "mock",
                "llm_provider": "mock",
            },
        )
        poll_response = client.post("/admin/api/poll-now")
        summary_response = client.get("/admin/api/summary")

    detections = summary_response.json()["detections"]
    assert poll_response.status_code == 200
    assert poll_response.json()[0]["detected_count"] == 1
    assert len(detections) == 1
    assert detections[0]["seen_count"] == 2


def test_disable_integration_immediately_marks_status_disabled() -> None:
    with build_client() as client:
        create_response = client.post(
            "/admin/api/integrations",
            json={
                "project_name": "GOA",
                "integration_type": "kibana",
                "endpoint_url": "demo://local",
                "resource_name": "db-*",
                "analyzer_mode": "mock",
                "llm_provider": "mock",
            },
        )
        integration_id = create_response.json()["id"]
        before_disable_response = client.get("/admin/api/summary")
        toggle_response = client.post(f"/admin/integrations/{integration_id}/toggle", follow_redirects=False)
        poll_response = client.post("/admin/api/poll-now")
        summary_response = client.get("/admin/api/summary")

    integration = summary_response.json()["integrations"][0]
    assert toggle_response.status_code == 303
    assert poll_response.json() == []
    assert len(before_disable_response.json()["detections"]) == 1
    assert integration["enabled"] is False
    assert integration["last_status"] == "disabled"
    assert summary_response.json()["detections"][0]["seen_count"] == 1
