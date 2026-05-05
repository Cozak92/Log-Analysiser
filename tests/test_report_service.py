from pathlib import Path

import pytest

from app.schemas.analysis import AnalysisMeta
from app.services.analysis_service import AnalysisService
from app.config import Settings


def test_report_service_refuses_to_overwrite_existing_file(tmp_path) -> None:
    service = AnalysisService(settings=Settings())
    response = service.analyze_text("status=500\nAttributeError: NoneType", analyzer_mode="mock")
    report_path = tmp_path / "analysis_report.md"
    report_path.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError):
        service.report_service.write_report(response.report_markdown or "", report_path)
