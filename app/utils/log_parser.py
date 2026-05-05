from __future__ import annotations

import re
from dataclasses import dataclass, field


COMMON_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "into",
    "http",
    "https",
    "error",
    "traceback",
    "exception",
    "failed",
    "request",
    "response",
    "service",
    "server",
    "line",
}


@dataclass(slots=True)
class ParsedLog:
    normalized_text: str
    lines: list[str]
    keywords: list[str] = field(default_factory=list)
    has_stack_trace: bool = False
    http_statuses: list[int] = field(default_factory=list)
    parser_notes: list[str] = field(default_factory=list)


def normalize_log_text(text: str, *, max_chars: int = 20_000) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(normalized) > max_chars:
        normalized = normalized[:max_chars]
    return normalized


def extract_keywords(text: str, *, limit: int = 10) -> list[str]:
    candidates = re.findall(r"[A-Za-z_][A-Za-z0-9_./:-]{2,}", text)
    frequencies: dict[str, int] = {}
    for raw in candidates:
        token = raw.strip(".,:;()[]{}<>\"'").lower()
        if not token or token in COMMON_STOPWORDS or token.isdigit():
            continue
        frequencies[token] = frequencies.get(token, 0) + 1

    sorted_tokens = sorted(
        frequencies.items(),
        key=lambda item: (-item[1], -len(item[0]), item[0]),
    )
    return [token for token, _count in sorted_tokens[:limit]]


def parse_log(text: str, *, max_chars: int = 20_000) -> ParsedLog:
    parser_notes: list[str] = []
    normalized = normalize_log_text(text, max_chars=max_chars)
    if not normalized:
        parser_notes.append("Log text was empty after normalization; using fallback placeholders.")

    lines = [line for line in normalized.split("\n") if line.strip()]
    if not lines:
        lines = ["<empty log input>"]

    has_stack_trace = bool(
        re.search(r"traceback|exception in thread|^\s+at\s+.+\(.+:\d+\)", normalized, re.IGNORECASE | re.MULTILINE)
    )
    http_statuses = [
        int(match)
        for match in re.findall(r"\b(?:status=|status:|HTTP/[0-9.]\"?\s)(\d{3})\b", normalized, re.IGNORECASE)
    ]
    keywords = extract_keywords(normalized)

    if len(normalized) >= max_chars:
        parser_notes.append(f"Log text was truncated to {max_chars} characters for analysis safety.")
    if not keywords:
        parser_notes.append("Keyword extraction found no stable tokens; analysis used generic fallback hints.")

    return ParsedLog(
        normalized_text=normalized,
        lines=lines,
        keywords=keywords,
        has_stack_trace=has_stack_trace,
        http_statuses=http_statuses,
        parser_notes=parser_notes,
    )


def build_log_excerpt(parsed_log: ParsedLog, *, line_limit: int = 12) -> str:
    excerpt_lines = parsed_log.lines[:line_limit]
    return "\n".join(excerpt_lines)

