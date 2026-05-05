from pathlib import Path

from app.analyzers.rule_based import RuleBasedAnalyzer
from app.schemas.analysis import SeverityLevel


def read_sample(name: str) -> str:
    return Path("samples", name).read_text(encoding="utf-8")


def test_rule_based_detects_null_reference() -> None:
    analyzer = RuleBasedAnalyzer()

    result = analyzer.analyze(read_sample("null_reference.log"))

    assert result.error_type == "null_reference"
    assert result.severity == SeverityLevel.HIGH
    assert any("null" in keyword for keyword in result.keywords)


def test_rule_based_detects_db_connection_issue() -> None:
    analyzer = RuleBasedAnalyzer()

    result = analyzer.analyze(read_sample("db_timeout.log"))

    assert result.error_type == "db_connection_error"
    assert result.severity == SeverityLevel.CRITICAL
    assert result.root_cause_candidates[0].confidence >= 0.6

