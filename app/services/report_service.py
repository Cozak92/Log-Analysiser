from __future__ import annotations

from pathlib import Path

from app.schemas.analysis import AnalysisMeta, AnalysisResult


class MarkdownReportService:
    def render(
        self,
        analysis: AnalysisResult,
        *,
        meta: AnalysisMeta,
        log_excerpt: str | None = None,
    ) -> str:
        sections: list[str] = [
            "# Log Analysis Report",
            "",
            "> Safety notice: this report suggests code changes only. It does not modify files, push commits, or deploy anything.",
            "",
            f"- Analyzer: `{meta.analyzer_used}`",
            f"- Fallback used: `{str(meta.fallback_used).lower()}`",
            f"- Source: `{meta.source_name or 'unknown'}`",
            "",
            "## Summary",
            "",
            analysis.summary,
            "",
            "## Structured Result",
            "",
            f"- Severity: `{analysis.severity.value}`",
            f"- Error type: `{analysis.error_type}`",
            f"- Keywords: {', '.join(analysis.keywords) if analysis.keywords else 'n/a'}",
            "",
            "## Root Cause Candidates",
            "",
        ]

        for candidate in analysis.root_cause_candidates:
            sections.append(
                f"- {candidate.title} (confidence={candidate.confidence:.2f}): {candidate.reason}"
            )

        sections.extend(
            [
                "",
                "## Impact",
                "",
                analysis.impact,
                "",
                "## Reproduction Steps",
                "",
            ]
        )
        sections.extend(f"- {item}" for item in analysis.reproduction_steps)

        sections.extend(
            [
                "",
                "## Immediate Checks",
                "",
            ]
        )
        sections.extend(f"- {item}" for item in analysis.immediate_checks)

        sections.extend(
            [
                "",
                "## Fix Suggestions",
                "",
            ]
        )
        for suggestion in analysis.fix_suggestions:
            sections.extend(
                [
                    f"### {suggestion.title}",
                    "",
                    suggestion.description,
                    "",
                    suggestion.example_patch,
                    "",
                ]
            )

        sections.extend(
            [
                "## Test Suggestions",
                "",
            ]
        )
        sections.extend(f"- {item}" for item in analysis.test_suggestions)

        sections.extend(
            [
                "",
                "## Verification Steps",
                "",
            ]
        )
        sections.extend(f"- {item}" for item in analysis.verification_steps)

        sections.extend(
            [
                "",
                "## Unknowns",
                "",
            ]
        )
        sections.extend(f"- {item}" for item in analysis.unknowns)

        if analysis.parser_notes:
            sections.extend(
                [
                    "",
                    "## Parser Notes",
                    "",
                ]
            )
            sections.extend(f"- {item}" for item in analysis.parser_notes)

        if log_excerpt:
            sections.extend(
                [
                    "",
                    "## Log Excerpt",
                    "",
                    "```text",
                    log_excerpt,
                    "```",
                ]
            )

        return "\n".join(sections).strip() + "\n"

    def write_report(self, report_markdown: str, output_path: str | Path) -> Path:
        path = Path(output_path)
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite existing report file: {path}")
        path.write_text(report_markdown, encoding="utf-8")
        return path

