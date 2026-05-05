from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import get_settings
from app.schemas.analysis import AnalyzeResponse, AnalyzerMode
from app.services.analysis_service import AnalysisService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze logs and suggest safe code fixes.")
    parser.add_argument("--file", dest="file_path", help="Path to a log file to analyze.")
    parser.add_argument("--text", dest="raw_text", help="Raw log text to analyze directly.")
    parser.add_argument(
        "--mode",
        dest="mode",
        choices=[mode.value for mode in AnalyzerMode],
        default=AnalyzerMode.AUTO.value,
        help="Analyzer mode to use.",
    )
    parser.add_argument("--source-name", help="Optional source label shown in the report.")
    parser.add_argument("--report-out", help="Optional path for a markdown report file.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    return parser


def load_text(args: argparse.Namespace) -> tuple[str, str]:
    if args.file_path:
        path = Path(args.file_path)
        raw = path.read_bytes()
        return raw.decode("utf-8", errors="replace"), str(path)
    if args.raw_text:
        return args.raw_text, args.source_name or "raw-text"
    raise ValueError("Provide either --file or --text.")


def format_pretty_output(response: AnalyzeResponse) -> str:
    analysis = response.analysis
    lines = [
        "Log Analysis MVP",
        "================",
        f"Analyzer: {response.meta.analyzer_used}",
        f"Fallback used: {str(response.meta.fallback_used).lower()}",
        f"Source: {response.meta.source_name or 'unknown'}",
        "",
        f"Summary: {analysis.summary}",
        f"Severity: {analysis.severity.value}",
        f"Error type: {analysis.error_type}",
        f"Keywords: {', '.join(analysis.keywords) if analysis.keywords else 'n/a'}",
        "",
        "Root cause candidates:",
    ]
    lines.extend(
        f"- {candidate.title} ({candidate.confidence:.2f}): {candidate.reason}"
        for candidate in analysis.root_cause_candidates
    )
    lines.extend(
        [
            "",
            "Immediate checks:",
        ]
    )
    lines.extend(f"- {item}" for item in analysis.immediate_checks)
    lines.extend(
        [
            "",
            "Fix suggestions:",
        ]
    )
    lines.extend(f"- {item.title}: {item.description}" for item in analysis.fix_suggestions)
    lines.extend(
        [
            "",
            "Verification steps:",
        ]
    )
    lines.extend(f"- {item}" for item in analysis.verification_steps)
    return "\n".join(lines)


def run_cli(args: argparse.Namespace) -> int:
    text, inferred_source_name = load_text(args)
    service = AnalysisService(settings=get_settings())
    response = service.analyze_text(
        text,
        analyzer_mode=AnalyzerMode(args.mode),
        include_report=True,
        source_name=args.source_name or inferred_source_name,
    )

    if args.json:
        print(json.dumps(response.model_dump(mode="json"), indent=2))
    else:
        print(format_pretty_output(response))

    if args.report_out and response.report_markdown:
        output_path = service.report_service.write_report(response.report_markdown, args.report_out)
        print(f"\nMarkdown report written to {output_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run_cli(args)
    except (ValueError, OSError, FileExistsError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
