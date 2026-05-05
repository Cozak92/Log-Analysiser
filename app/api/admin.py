from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.repositories.admin_repository import AdminRepository
from app.schemas.admin import (
    AdminSummary,
    DetectionRecord,
    PLANNED_INTEGRATION_TYPES,
    ProjectIntegration,
    ProjectIntegrationCreate,
    ProjectSummary,
    PollResult,
    REPRESENTATIVE_LLM_PROVIDERS,
    SUPPORTED_INTEGRATION_TYPES,
)
from app.services.detection_service import DetectionService

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


@router.get("", response_class=HTMLResponse)
def admin_home(request: Request) -> HTMLResponse:
    return render_admin_page(request, template_name="admin/index.html")


@router.get("/integrations", response_class=HTMLResponse)
def integration_list(request: Request) -> HTMLResponse:
    return render_admin_page(request, template_name="admin/integrations.html")


@router.get("/detections", response_class=HTMLResponse)
def detection_list(request: Request) -> HTMLResponse:
    return render_admin_page(request, template_name="admin/detections.html")


@router.post("/integrations", response_model=None)
async def create_integration(
    request: Request,
    project_name: str = Form(...),
    integration_type: str = Form("kibana"),
    endpoint_url: str = Form(...),
    resource_name: str = Form(...),
    analyzer_mode: str = Form("auto"),
    llm_provider: str = Form("mock"),
    custom_llm_provider: str | None = Form(None),
    llm_model: str | None = Form(None),
) -> Response:
    repository = get_repository(request)
    try:
        payload = ProjectIntegrationCreate(
            project_name=project_name,
            integration_type=integration_type,
            endpoint_url=endpoint_url,
            resource_name=resource_name,
            analyzer_mode=analyzer_mode,
            llm_provider=llm_provider,
            custom_llm_provider=custom_llm_provider,
            llm_model=llm_model or None,
        )
        integration = repository.upsert_integration(
            project_name=payload.project_name,
            integration_type=payload.integration_type.value,
            endpoint_url=payload.endpoint_url,
            resource_name=payload.resource_name,
            analyzer_mode=payload.analyzer_mode.value,
            llm_provider=payload.llm_provider,
            llm_model=payload.llm_model,
        )
        await get_detection_service(request).poll_integration(integration)
    except (ValidationError, ValueError) as exc:
        return render_admin_page(request, template_name="admin/integrations.html", form_error=str(exc))
    except Exception as exc:
        return render_admin_page(request, template_name="admin/integrations.html", db_error=str(exc))
    return RedirectResponse(url="/admin/integrations", status_code=303)


@router.post("/integrations/{integration_id}/toggle")
def toggle_integration(request: Request, integration_id: str) -> RedirectResponse:
    repository = get_repository(request)
    integration = repository.get_integration(integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Project integration not found.")
    repository.set_integration_enabled(integration_id, not integration.enabled)
    return RedirectResponse(url="/admin/integrations", status_code=303)


@router.post("/integrations/{integration_id}/edit", response_model=None)
async def edit_integration(
    request: Request,
    integration_id: str,
    project_name: str = Form(...),
    integration_type: str = Form("kibana"),
    endpoint_url: str = Form(...),
    resource_name: str = Form(...),
    analyzer_mode: str = Form("auto"),
    llm_provider: str = Form("mock"),
    custom_llm_provider: str | None = Form(None),
    llm_model: str | None = Form(None),
) -> Response:
    repository = get_repository(request)
    try:
        payload = ProjectIntegrationCreate(
            project_name=project_name,
            integration_type=integration_type,
            endpoint_url=endpoint_url,
            resource_name=resource_name,
            analyzer_mode=analyzer_mode,
            llm_provider=llm_provider,
            custom_llm_provider=custom_llm_provider,
            llm_model=llm_model or None,
        )
        integration = repository.update_integration(
            integration_id,
            project_name=payload.project_name,
            integration_type=payload.integration_type.value,
            endpoint_url=payload.endpoint_url,
            resource_name=payload.resource_name,
            analyzer_mode=payload.analyzer_mode.value,
            llm_provider=payload.llm_provider,
            llm_model=payload.llm_model,
        )
        if not integration:
            raise HTTPException(status_code=404, detail="Project integration not found.")
        if integration.enabled:
            await get_detection_service(request).poll_integration(integration)
    except HTTPException:
        raise
    except (ValidationError, ValueError) as exc:
        return render_admin_page(request, template_name="admin/integrations.html", form_error=str(exc))
    except Exception as exc:
        return render_admin_page(request, template_name="admin/integrations.html", db_error=str(exc))
    return RedirectResponse(url="/admin/integrations", status_code=303)


@router.post("/poll-now")
async def poll_now(request: Request) -> RedirectResponse:
    detection_service = get_detection_service(request)
    await detection_service.poll_all_enabled_integrations()
    selected_project = request.query_params.get("project")
    redirect_url = f"/admin/detections?project={selected_project}" if selected_project else "/admin/detections"
    return RedirectResponse(url=redirect_url, status_code=303)


@router.get("/api/summary", response_model=AdminSummary)
def api_summary(request: Request) -> AdminSummary:
    repository = get_repository(request)
    integrations = repository.list_integrations()
    return AdminSummary(
        projects=build_project_summaries(integrations),
        integrations=integrations,
        detections=repository.list_detections(limit=100),
    )


@router.post("/api/integrations", response_model=dict)
async def api_create_integration(payload: ProjectIntegrationCreate, request: Request) -> dict[str, str]:
    repository = get_repository(request)
    integration = repository.upsert_integration(
        project_name=payload.project_name,
        integration_type=payload.integration_type.value,
        endpoint_url=payload.endpoint_url,
        resource_name=payload.resource_name,
        analyzer_mode=payload.analyzer_mode.value,
        llm_provider=payload.llm_provider,
        llm_model=payload.llm_model,
    )
    await get_detection_service(request).poll_integration(integration)
    return {"id": integration.id}


@router.post("/api/sources", response_model=dict)
async def api_create_source_compat(payload: ProjectIntegrationCreate, request: Request) -> dict[str, str]:
    return await api_create_integration(payload, request)


@router.post("/api/poll-now", response_model=list[PollResult])
async def api_poll_now(request: Request) -> list[PollResult]:
    detection_service = get_detection_service(request)
    return await detection_service.poll_all_enabled_integrations()


def render_admin_page(
    request: Request,
    *,
    template_name: str,
    form_error: str | None = None,
    db_error: str | None = None,
) -> HTMLResponse:
    integrations = []
    detections = []
    editing_integration = None
    startup_error = getattr(request.app.state, "admin_startup_error", None)
    try:
        repository = get_repository(request)
        integrations = repository.list_integrations()
        detections = repository.list_detections(limit=100)
        edit_id = request.query_params.get("edit")
        if edit_id:
            editing_integration = repository.get_integration(edit_id)
    except Exception as exc:
        db_error = db_error or str(exc)

    selected_project = request.query_params.get("project") or ""
    refresh_interval = normalize_refresh_interval(request.query_params.get("refresh"))
    project_names = sorted({integration.project_name for integration in integrations} | {detection.project_name for detection in detections})
    filtered_detections = [
        detection for detection in detections if not selected_project or detection.project_name == selected_project
    ]

    return templates.TemplateResponse(
        request,
        template_name,
        {
            "projects": build_project_summaries(integrations),
            "integrations": integrations,
            "detections": detections,
            "filtered_detections": filtered_detections,
            "detections_by_project": group_detections_by_project(detections),
            "project_names": project_names,
            "selected_project": selected_project,
            "refresh_interval": refresh_interval,
            "editing_integration": editing_integration,
            "form_error": form_error,
            "db_error": db_error,
            "startup_error": startup_error,
            "integration_type_options": SUPPORTED_INTEGRATION_TYPES,
            "planned_integration_type_options": PLANNED_INTEGRATION_TYPES,
            "provider_options": REPRESENTATIVE_LLM_PROVIDERS,
        },
    )


def get_repository(request: Request) -> AdminRepository:
    return request.app.state.admin_repository


def get_detection_service(request: Request) -> DetectionService:
    return request.app.state.detection_service


def build_project_summaries(integrations: list[ProjectIntegration]) -> list[ProjectSummary]:
    summaries: dict[str, ProjectSummary] = {}
    for integration in integrations:
        summary = summaries.setdefault(integration.project_name, ProjectSummary(name=integration.project_name))
        summary.integration_count += 1
        if integration.enabled:
            summary.enabled_integration_count += 1
    return sorted(summaries.values(), key=lambda summary: summary.name)


def group_detections_by_project(detections: list[DetectionRecord]) -> dict[str, list[DetectionRecord]]:
    grouped: dict[str, list[DetectionRecord]] = {}
    for detection in detections:
        grouped.setdefault(detection.project_name, []).append(detection)
    return dict(sorted(grouped.items()))


def normalize_refresh_interval(value: str | None) -> str:
    if value in {"10", "30"}:
        return value
    return "off"
