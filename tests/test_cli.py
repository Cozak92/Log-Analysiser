from pathlib import Path

from app.cli import main


def test_cli_generates_report_file(tmp_path, capsys) -> None:
    report_path = tmp_path / "analysis_report.md"

    exit_code = main(
        [
            "--file",
            "samples/null_reference.log",
            "--mode",
            "mock",
            "--report-out",
            str(report_path),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Summary:" in output
    assert report_path.exists()

