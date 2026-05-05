from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.admin import router as admin_router
from app.api.routes import router
from app.config import Settings, get_settings
from app.repositories.admin_repository import build_admin_repository
from app.services.analysis_service import AnalysisService
from app.services.detection_service import DetectionService
from app.workers.kibana_poller import KibanaPollingWorker


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    repository = build_admin_repository(settings)
    analysis_service = AnalysisService(settings=settings)
    detection_service = DetectionService(
        settings=settings,
        repository=repository,
        analysis_service=analysis_service,
    )
    poller = KibanaPollingWorker(settings=settings, detection_service=detection_service)

    app.state.admin_repository = repository
    app.state.analysis_service = analysis_service
    app.state.detection_service = detection_service
    app.state.kibana_poller = poller
    app.state.admin_startup_error = None

    try:
        repository.ensure_indexes()
    except Exception as exc:
        app.state.admin_startup_error = str(exc)

    if settings.kibana_poll_enabled:
        await poller.start()

    try:
        yield
    finally:
        await poller.stop()


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(
        title="Log Analysis MVP",
        version="0.1.0",
        description="Safe backend for reading logs, inferring root causes, and suggesting code changes without applying them.",
        lifespan=lifespan,
    )
    app.state.settings = settings or get_settings()
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    app.include_router(router)
    app.include_router(admin_router)
    return app


app = create_app()
