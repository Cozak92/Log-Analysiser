from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.repositories.admin_repository import AdminRepository
from app.schemas.admin import AdminSummary, KibanaSourceCreate, PollResult, REPRESENTATIVE_LLM_PROVIDERS
from app.services.detection_service import DetectionService

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


@router.get("", response_class=HTMLResponse)
def admin_home(request: Request) -> HTMLResponse:
    return render_admin_page(request, template_name="admin/index.html")


@router.get("/detections", response_class=HTMLResponse)
def detection_list(request: Request) -> HTMLResponse:
    return render_admin_page(request, template_name="admin/detections.html")


@router.post("/sources", response_model=None)
def create_source(
    request: Request,
    kibana_url: str = Form(...),
    data_view_name: str = Form(...),
    analyzer_mode: str = Form("auto"),
    llm_provider: str = Form("mock"),
    custom_llm_provider: str | None = Form(None),
    llm_model: str | None = Form(None),
) -> Response:
    repository = get_repository(request)
    try:
        payload = KibanaSourceCreate(
            kibana_url=kibana_url,
            data_view_name=data_view_name,
            analyzer_mode=analyzer_mode,
            llm_provider=llm_provider,
            custom_llm_provider=custom_llm_provider,
            llm_model=llm_model or None,
        )
        repository.upsert_source(
            kibana_url=payload.kibana_url,
            data_view_name=payload.data_view_name,
            analyzer_mode=payload.analyzer_mode.value,
            llm_provider=payload.llm_provider,
            llm_model=payload.llm_model,
        )
    except (ValidationError, ValueError) as exc:
        return render_admin_page(request, template_name="admin/index.html", form_error=str(exc))
    except Exception as exc:
        return render_admin_page(request, template_name="admin/index.html", db_error=str(exc))
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/sources/{source_id}/toggle")
def toggle_source(request: Request, source_id: str) -> RedirectResponse:
    repository = get_repository(request)
    source = repository.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Kibana source not found.")
    repository.set_source_enabled(source_id, not source.enabled)
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/poll-now")
async def poll_now(request: Request) -> RedirectResponse:
    detection_service = get_detection_service(request)
    await detection_service.poll_all_enabled_sources()
    return RedirectResponse(url="/admin/detections", status_code=303)


@router.get("/api/summary", response_model=AdminSummary)
def api_summary(request: Request) -> AdminSummary:
    repository = get_repository(request)
    return AdminSummary(sources=repository.list_sources(), detections=repository.list_detections(limit=100))


@router.post("/api/sources", response_model=dict)
def api_create_source(payload: KibanaSourceCreate, request: Request) -> dict[str, str]:
    repository = get_repository(request)
    source = repository.upsert_source(
        kibana_url=payload.kibana_url,
        data_view_name=payload.data_view_name,
        analyzer_mode=payload.analyzer_mode.value,
        llm_provider=payload.llm_provider,
        llm_model=payload.llm_model,
    )
    return {"id": source.id}


@router.post("/api/poll-now", response_model=list[PollResult])
async def api_poll_now(request: Request) -> list[PollResult]:
    detection_service = get_detection_service(request)
    return await detection_service.poll_all_enabled_sources()


def render_admin_page(
    request: Request,
    *,
    template_name: str,
    form_error: str | None = None,
    db_error: str | None = None,
) -> HTMLResponse:
    sources = []
    detections = []
    startup_error = getattr(request.app.state, "admin_startup_error", None)
    try:
        repository = get_repository(request)
        sources = repository.list_sources()
        detections = repository.list_detections(limit=100)
    except Exception as exc:
        db_error = db_error or str(exc)

    return templates.TemplateResponse(
        request,
        template_name,
        {
            "sources": sources,
            "detections": detections,
            "form_error": form_error,
            "db_error": db_error,
            "startup_error": startup_error,
            "provider_options": REPRESENTATIVE_LLM_PROVIDERS,
        },
    )


def get_repository(request: Request) -> AdminRepository:
    return request.app.state.admin_repository


def get_detection_service(request: Request) -> DetectionService:
    return request.app.state.detection_service
