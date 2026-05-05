from __future__ import annotations

import re
from dataclasses import dataclass

from app.analyzers.base import LogAnalyzer
from app.schemas.analysis import AnalysisResult, FixSuggestion, RootCauseCandidate, SeverityLevel
from app.utils.log_parser import ParsedLog, parse_log


@dataclass(frozen=True, slots=True)
class RuleDefinition:
    name: str
    patterns: tuple[str, ...]
    error_type: str
    severity: SeverityLevel
    candidate_title: str
    candidate_reason: str
    impact: str
    immediate_checks: tuple[str, ...]
    reproduction_steps: tuple[str, ...]
    verification_steps: tuple[str, ...]
    test_suggestions: tuple[str, ...]
    unknowns: tuple[str, ...]
    fix_suggestions: tuple[FixSuggestion, ...]


NULL_REFERENCE_FIX = FixSuggestion(
    title="Guard nullable values before dereferencing",
    description="Add an explicit null check close to the failing access point and return a controlled error or fallback path.",
    example_patch="""```python
def build_profile_response(user: User | None) -> dict[str, str]:
    if user is None:
        raise ValueError("user must be loaded before building the response")

    return {"email": user.email}
```""",
)

TIMEOUT_FIX = FixSuggestion(
    title="Bound the slow dependency and fail fast",
    description="Set explicit client/database timeouts and handle timeout exceptions at the request boundary so the service can degrade predictably.",
    example_patch="""```python
from sqlalchemy.exc import OperationalError

def fetch_order(repository: OrderRepository, order_id: str) -> Order:
    try:
        return repository.get(order_id, timeout_seconds=2)
    except TimeoutError as exc:
        raise RuntimeError("database lookup timed out") from exc
    except OperationalError as exc:
        raise RuntimeError("database connection unavailable") from exc
```""",
)

DB_CONNECTION_FIX = FixSuggestion(
    title="Validate connection pool and startup health",
    description="Fail early when the database is unreachable and surface a clearer error before requests start piling up.",
    example_patch="""```python
def verify_database_connectivity(engine) -> None:
    with engine.connect() as connection:
        connection.execute("SELECT 1")


def create_app() -> FastAPI:
    verify_database_connectivity(engine)
    return FastAPI()
```""",
)

HTTP_FIX = FixSuggestion(
    title="Convert unhandled exceptions into controlled HTTP failures",
    description="Wrap request handlers or service boundaries so unexpected failures become traceable HTTP responses with request identifiers.",
    example_patch="""```python
from fastapi import HTTPException

def load_invoice(invoice_id: str) -> dict[str, str]:
    try:
        return invoice_service.get_invoice(invoice_id)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="invoice backend timed out") from exc
```""",
)

GENERIC_FIX = FixSuggestion(
    title="Add defensive logging and isolate the failing code path",
    description="Capture the failing input, dependency state, and request context around the exception so the next incident is reproducible.",
    example_patch="""```python
def process_event(event: dict[str, object]) -> None:
    logger.error("event processing failed", extra={"event": event})
    raise
```""",
)


class RuleBasedAnalyzer(LogAnalyzer):
    name = "rule-based"

    RULES: tuple[RuleDefinition, ...] = (
        RuleDefinition(
            name="null_reference",
            patterns=(
                r"nullpointerexception",
                r"null reference",
                r"nonetype",
                r"cannot read propert(?:y|ies) of null",
                r"attributeerror",
            ),
            error_type="null_reference",
            severity=SeverityLevel.HIGH,
            candidate_title="Object was dereferenced before required data was loaded",
            candidate_reason="The log contains null-reference markers or missing-object access patterns, which usually indicate missing guards or assumptions about dependency output.",
            impact="Requests that hit the unguarded path are likely to fail with a 5xx response or abort the job entirely.",
            immediate_checks=(
                "Inspect the exact variable or object name near the failing line.",
                "Confirm whether the upstream repository or API can legitimately return null or empty data.",
                "Check whether the failing path was recently changed to skip validation.",
            ),
            reproduction_steps=(
                "Replay the same request or job input with the smallest payload that still leaves the referenced object empty.",
                "Run the target code path with debug logging enabled around the null-producing dependency.",
            ),
            verification_steps=(
                "Re-run the failing request with missing or partial data and confirm the service returns a controlled error or fallback result.",
                "Verify the previous happy-path behavior still succeeds with a fully populated object.",
            ),
            test_suggestions=(
                "Add a unit test where the dependency returns None and assert a controlled exception or fallback response.",
                "Add an integration test for the endpoint or worker path that previously triggered the null dereference.",
            ),
            unknowns=(
                "The log does not prove whether the null value originated from stale data, bad input, or a missing DB row.",
            ),
            fix_suggestions=(NULL_REFERENCE_FIX,),
        ),
        RuleDefinition(
            name="timeout",
            patterns=(
                r"timeout",
                r"timed out",
                r"deadline exceeded",
                r"sockettimeout",
                r"read timed out",
            ),
            error_type="timeout",
            severity=SeverityLevel.HIGH,
            candidate_title="A dependency exceeded its response budget",
            candidate_reason="Timeout markers indicate a slow or unreachable downstream service, database, or network hop that caused the request to exceed configured limits.",
            impact="User-facing latency and retry amplification are likely; under load this can cascade into wider service instability.",
            immediate_checks=(
                "Check dependency latency and saturation around the incident timestamp.",
                "Confirm whether retry logic or thread pools were exhausted.",
                "Review recent timeout configuration changes in clients and gateways.",
            ),
            reproduction_steps=(
                "Replay the request against a slow stub or throttled dependency to reproduce the timeout path.",
                "Run the service locally with reduced timeout thresholds to confirm the exception handling path.",
            ),
            verification_steps=(
                "Confirm slow dependencies now fail fast with a controlled error instead of hanging the request path.",
                "Measure that the endpoint recovers within the intended timeout budget under a synthetic slow dependency test.",
            ),
            test_suggestions=(
                "Add an integration test using a delayed dependency response and assert the timeout boundary.",
                "Add a regression test that verifies retries stay bounded and do not multiply request load.",
            ),
            unknowns=(
                "The log does not show whether the timeout was caused by network issues, pool starvation, or a slow query.",
            ),
            fix_suggestions=(TIMEOUT_FIX,),
        ),
        RuleDefinition(
            name="db_connection",
            patterns=(
                r"could not connect to server",
                r"connection refused",
                r"too many connections",
                r"sqlstate\[?08001\]?",
                r"operationalerror",
                r"database unavailable",
                r"connection pool",
            ),
            error_type="db_connection_error",
            severity=SeverityLevel.CRITICAL,
            candidate_title="Database connectivity or pool availability failed",
            candidate_reason="The log includes classic database connection failure markers, which usually mean the service could not acquire or establish a DB session.",
            impact="New requests depending on the database are likely failing broadly, making this a service-level or environment-level incident.",
            immediate_checks=(
                "Check database health, connection counts, and pool exhaustion.",
                "Confirm credentials, network routes, and TLS settings have not changed.",
                "Inspect whether a deploy increased connection usage without pool tuning.",
            ),
            reproduction_steps=(
                "Point the application at an unreachable database host in a local environment to reproduce the connection failure path.",
                "Simulate pool exhaustion by reducing pool size and driving concurrent requests through the same code path.",
            ),
            verification_steps=(
                "Verify the application starts cleanly and can execute a simple health query after the connection fix.",
                "Confirm concurrent requests stay within the configured connection pool without raising OperationalError.",
            ),
            test_suggestions=(
                "Add a startup health-check test that fails when the database is unreachable.",
                "Add an integration test that asserts a clear application error when the pool is exhausted.",
            ),
            unknowns=(
                "The log does not confirm whether the problem is database-side downtime, secret rotation, or pool misconfiguration.",
            ),
            fix_suggestions=(DB_CONNECTION_FIX, TIMEOUT_FIX),
        ),
        RuleDefinition(
            name="http_5xx",
            patterns=(
                r"\b500\b",
                r"\b502\b",
                r"\b503\b",
                r"\b504\b",
                r"internal server error",
                r"upstream connect error",
            ),
            error_type="http_server_error",
            severity=SeverityLevel.HIGH,
            candidate_title="Unhandled application failure surfaced as an HTTP 5xx",
            candidate_reason="HTTP 5xx markers usually mean an exception or unavailable dependency escaped the request boundary and propagated to the caller.",
            impact="Callers of the affected endpoint are receiving server errors and may be retrying aggressively.",
            immediate_checks=(
                "Identify the endpoint, request ID, and dependency call immediately before the 5xx.",
                "Measure whether the error is isolated to one route or multiple entry points.",
                "Check if retries from clients or the gateway are increasing error volume.",
            ),
            reproduction_steps=(
                "Replay the failing HTTP request with the same headers and payload against a non-production environment.",
                "Trigger the same dependency failure locally and observe whether it returns the same 5xx status.",
            ),
            verification_steps=(
                "Confirm the endpoint now returns the expected status code and response shape for both failure and success paths.",
                "Verify request tracing or logs include enough context to diagnose the next failure quickly.",
            ),
            test_suggestions=(
                "Add an API test for the exact route and payload that previously returned 5xx.",
                "Add a regression test that asserts known dependency failures map to controlled 4xx/5xx responses.",
            ),
            unknowns=(
                "The log alone does not prove whether the 5xx originated inside the app, an upstream proxy, or a dependency gateway.",
            ),
            fix_suggestions=(HTTP_FIX,),
        ),
    )

    def analyze(self, log_text: str) -> AnalysisResult:
        parsed_log = parse_log(log_text)
        matched_rules = self._match_rules(parsed_log)
        if not matched_rules:
            return self._build_generic_result(parsed_log)
        return self._build_result(parsed_log, matched_rules)

    def _match_rules(self, parsed_log: ParsedLog) -> list[tuple[RuleDefinition, int]]:
        matches: list[tuple[RuleDefinition, int]] = []
        text = parsed_log.normalized_text
        for rule in self.RULES:
            score = 0
            for pattern in rule.patterns:
                if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
                    score += 1
            if score:
                if parsed_log.has_stack_trace and rule.error_type in {"null_reference", "http_server_error"}:
                    score += 1
                if any(status >= 500 for status in parsed_log.http_statuses) and rule.error_type == "http_server_error":
                    score += 1
                matches.append((rule, score))
        matches.sort(key=lambda item: item[1], reverse=True)
        return matches

    def _build_result(
        self,
        parsed_log: ParsedLog,
        matched_rules: list[tuple[RuleDefinition, int]],
    ) -> AnalysisResult:
        severity = max((rule.severity for rule, _score in matched_rules), key=self._severity_rank)
        top_rule = matched_rules[0][0]
        root_cause_candidates: list[RootCauseCandidate] = []
        immediate_checks: list[str] = []
        reproduction_steps: list[str] = []
        verification_steps: list[str] = []
        test_suggestions: list[str] = []
        unknowns: list[str] = []
        fix_suggestions: list[FixSuggestion] = []

        for rule, score in matched_rules[:3]:
            confidence = min(0.95, 0.45 + (score * 0.15))
            root_cause_candidates.append(
                RootCauseCandidate(
                    title=rule.candidate_title,
                    confidence=round(confidence, 2),
                    reason=rule.candidate_reason,
                )
            )
            immediate_checks.extend(rule.immediate_checks)
            reproduction_steps.extend(rule.reproduction_steps)
            verification_steps.extend(rule.verification_steps)
            test_suggestions.extend(rule.test_suggestions)
            unknowns.extend(rule.unknowns)
            fix_suggestions.extend(rule.fix_suggestions)

        if parsed_log.has_stack_trace:
            immediate_checks.append("Inspect the first application frame in the stack trace; it is usually the highest-signal code location.")
        if parsed_log.http_statuses:
            test_suggestions.append("Capture the observed HTTP status code in the regression test to prevent silent behavior drift.")

        summary = self._build_summary(parsed_log, top_rule, severity)
        keywords = [top_rule.error_type, *parsed_log.keywords]

        return AnalysisResult(
            summary=summary,
            severity=severity,
            error_type=top_rule.error_type,
            keywords=self._dedupe(keywords),
            root_cause_candidates=root_cause_candidates,
            impact=top_rule.impact,
            reproduction_steps=self._dedupe(reproduction_steps),
            immediate_checks=self._dedupe(immediate_checks),
            fix_suggestions=self._dedupe_fix_suggestions(fix_suggestions),
            test_suggestions=self._dedupe(test_suggestions),
            verification_steps=self._dedupe(verification_steps),
            unknowns=self._dedupe(unknowns),
            parser_notes=parsed_log.parser_notes,
        )

    def _build_generic_result(self, parsed_log: ParsedLog) -> AnalysisResult:
        return AnalysisResult(
            summary="The log contains an application failure signal, but the exact failure mode is unclear from the available text alone.",
            severity=SeverityLevel.MEDIUM,
            error_type="unknown_application_error",
            keywords=parsed_log.keywords,
            root_cause_candidates=[
                RootCauseCandidate(
                    title="Unhandled application exception",
                    confidence=0.42,
                    reason="The log includes failure text but not enough structured context to isolate a single dominant cause.",
                ),
                RootCauseCandidate(
                    title="Dependency-specific failure hidden by generic logging",
                    confidence=0.37,
                    reason="Many operational logs collapse downstream errors into a generic error line without exposing the real dependency or input that failed.",
                ),
            ],
            impact="The affected request or job likely failed, but the broader service impact is still uncertain.",
            reproduction_steps=[
                "Replay the same input in a non-production environment with debug logging enabled around the failing code path.",
                "Capture request identifiers, dependency targets, and recent configuration changes before attempting a fix.",
            ],
            immediate_checks=[
                "Locate the first surrounding log lines before and after the failure to recover missing context.",
                "Check whether the failure is isolated or recurring across multiple requests.",
            ],
            fix_suggestions=[GENERIC_FIX],
            test_suggestions=[
                "Add a regression test for the observed failing input once the real trigger is identified.",
                "Add structured logging around the failing branch so the next incident is diagnosable from one log bundle.",
            ],
            verification_steps=[
                "Re-run the failing scenario after the change and confirm the log now contains clearer context or a controlled failure.",
            ],
            unknowns=[
                "The log does not identify the exact dependency, input payload, or service version involved in the failure.",
            ],
            parser_notes=parsed_log.parser_notes,
        )

    @staticmethod
    def _severity_rank(severity: SeverityLevel) -> int:
        return {
            SeverityLevel.LOW: 0,
            SeverityLevel.MEDIUM: 1,
            SeverityLevel.HIGH: 2,
            SeverityLevel.CRITICAL: 3,
        }[severity]

    @staticmethod
    def _build_summary(parsed_log: ParsedLog, top_rule: RuleDefinition, severity: SeverityLevel) -> str:
        if parsed_log.http_statuses:
            return (
                f"Detected a likely {top_rule.error_type} incident with {severity.value} severity; "
                f"the log also shows HTTP status {parsed_log.http_statuses[0]}, so this likely surfaced to callers."
            )
        if parsed_log.has_stack_trace:
            return (
                f"Detected a likely {top_rule.error_type} incident with {severity.value} severity and an accompanying stack trace, "
                "which suggests the exception escaped normal error handling."
            )
        return f"Detected a likely {top_rule.error_type} incident with {severity.value} severity based on the strongest error markers in the log."

    @staticmethod
    def _dedupe(items: list[str]) -> list[str]:
        seen: list[str] = []
        for item in items:
            normalized = item.strip()
            if normalized and normalized not in seen:
                seen.append(normalized)
        return seen

    @staticmethod
    def _dedupe_fix_suggestions(items: list[FixSuggestion]) -> list[FixSuggestion]:
        seen_titles: set[str] = set()
        deduped: list[FixSuggestion] = []
        for item in items:
            if item.title in seen_titles:
                continue
            seen_titles.add(item.title)
            deduped.append(item)
        return deduped
