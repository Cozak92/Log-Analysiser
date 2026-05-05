from __future__ import annotations

from app.schemas.analysis import AnalysisResult


def build_analysis_system_prompt() -> str:
    schema = AnalysisResult.model_json_schema()
    return (
        "You are a senior software engineer and SRE. "
        "Analyze logs without claiming certainty when evidence is incomplete. "
        "Never suggest automatic deployment or direct production edits. "
        "Return JSON only. Use this schema: "
        f"{schema}"
    )


def build_analysis_user_prompt(log_text: str) -> str:
    return (
        "Analyze the following log input. "
        "Return likely root cause candidates, impact, reproduction steps, safe fix suggestions, "
        "test guidance, verification steps, and unknowns.\n\n"
        f"{log_text}"
    )

