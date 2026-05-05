from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.config import get_settings
from app.schemas.analysis import AnalyzeResponse, AnalyzeTextRequest, AnalyzerMode, HealthResponse
from app.services.analysis_service import AnalysisService

router = APIRouter()


def get_analysis_service() -> AnalysisService:
    return AnalysisService(settings=get_settings())


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@router.post("/analyze/text", response_model=AnalyzeResponse)
def analyze_text(
    request: AnalyzeTextRequest,
    service: AnalysisService = Depends(get_analysis_service),
) -> AnalyzeResponse:
    return service.analyze_text(
        request.text,
        analyzer_mode=request.analyzer_mode,
        include_report=request.include_report,
        source_name=request.source_name or "raw-text",
    )


@router.post("/analyze/file", response_model=AnalyzeResponse)
async def analyze_file(
    file: UploadFile = File(...),
    analyzer_mode: AnalyzerMode = Form(default=AnalyzerMode.AUTO),
    include_report: bool = Form(default=True),
    service: AnalysisService = Depends(get_analysis_service),
) -> AnalyzeResponse:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("utf-8", errors="replace")

    return service.analyze_text(
        text,
        analyzer_mode=analyzer_mode,
        include_report=include_report,
        source_name=file.filename or "uploaded-log",
    )

