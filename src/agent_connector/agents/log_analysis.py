"""Log Analysis agent: local preprocessing plus deterministic stub summary.

Live LLM integration is deferred (Stage 5). Stream event generation is
protocol-agnostic so gRPC can wrap it later.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator

from agent_connector.domain.models import (
    AgentStatus,
    EvidenceItem,
    IncidentRequest,
    LogAnalysisEvent,
    LogAnalysisEventType,
    LogAnalysisResult,
    LogEntry,
    LogLevel,
)

_ERROR_LIKE = {LogLevel.ERROR, LogLevel.FATAL}

_SCENARIO_CAUSES = {
    "db_connection_failure": (
        "Repeated database connection timeouts and connection saturation on orders-db.",
        "database connection failure on orders-db",
    ),
    "retry_storm": (
        "Payment retries amplified load until card-gateway rate limiting and checkout failures.",
        "retry storm against payment / rate limit",
    ),
    "expired_certificate": (
        "TLS handshakes failing because the auth-service certificate is expired.",
        "expired TLS certificate on auth-service",
    ),
}


def analyze_logs(request: IncidentRequest) -> LogAnalysisResult:
    """Unary log analysis used by the fair protocol comparison path."""
    invalid = _validate(request)
    if invalid is not None:
        return invalid

    evidence = extract_evidence(request.logs)
    summary, likely_cause = stub_summarize(request, evidence)
    return LogAnalysisResult(
        evidence=evidence,
        summary=summary,
        likely_cause=likely_cause,
        status=AgentStatus.OK,
    )


def analyze_logs_stream(request: IncidentRequest) -> Iterator[LogAnalysisEvent]:
    """Yield ordered progress events ending in a full LogAnalysisResult."""
    invalid = _validate(request)
    if invalid is not None:
        yield LogAnalysisEvent(
            type=LogAnalysisEventType.ERROR,
            message=invalid.error_message,
            error_message=invalid.error_message,
            result=invalid,
        )
        return

    yield LogAnalysisEvent(
        type=LogAnalysisEventType.STARTED,
        message=f"log analysis started for {request.incident_id}",
    )

    evidence = extract_evidence(request.logs)
    for item in evidence:
        yield LogAnalysisEvent(
            type=LogAnalysisEventType.EVIDENCE_FOUND,
            message=f"evidence in {item.service}: {item.summary}",
            evidence=item,
        )

    summary, likely_cause = stub_summarize(request, evidence)
    partial = LogAnalysisResult(
        evidence=evidence,
        summary=summary,
        likely_cause=likely_cause,
        status=AgentStatus.OK,
    )
    yield LogAnalysisEvent(
        type=LogAnalysisEventType.LLM_SUMMARY,
        message="stub summary completed",
        result=partial,
    )

    completed = LogAnalysisResult(
        evidence=evidence,
        summary=summary,
        likely_cause=likely_cause,
        status=AgentStatus.OK,
    )
    yield LogAnalysisEvent(
        type=LogAnalysisEventType.COMPLETED,
        message="log analysis completed",
        result=completed,
    )


def extract_evidence(logs: list[LogEntry]) -> list[EvidenceItem]:
    """Reduce raw logs to repeated error-like evidence per service."""
    counts: Counter[tuple[str, str]] = Counter()
    samples: dict[tuple[str, str], str] = {}
    service_totals: Counter[str] = Counter()

    for entry in logs:
        if entry.level not in _ERROR_LIKE:
            continue
        key = (entry.service, _normalize_message(entry.message))
        counts[key] += 1
        service_totals[entry.service] += 1
        samples.setdefault(key, entry.message)

    if not counts:
        return []

    # Keep the strongest pattern per service, ranked by frequency then FATAL-ish wording.
    best_by_service: dict[str, tuple[int, str, str]] = {}
    for (service, _normalized), count in counts.items():
        sample = samples[(service, _normalized)]
        current = best_by_service.get(service)
        if current is None or count > current[0]:
            best_by_service[service] = (count, sample, _normalized)

    ranked_services = sorted(
        best_by_service.items(),
        key=lambda item: (-service_totals[item[0]], item[0]),
    )

    evidence: list[EvidenceItem] = []
    for service, (count, sample, _) in ranked_services:
        evidence.append(
            EvidenceItem(
                service=service,
                summary=f"{count} repeated error-like event(s)",
                count=count,
                sample_message=sample,
            )
        )
    return evidence


def stub_summarize(
    request: IncidentRequest,
    evidence: list[EvidenceItem],
) -> tuple[str, str]:
    """Deterministic substitute for the Stage 5 LLM call."""
    if request.scenario in _SCENARIO_CAUSES:
        return _SCENARIO_CAUSES[request.scenario]

    if not evidence:
        return (
            "No error-like evidence found in the provided logs.",
            "insufficient evidence",
        )

    top = evidence[0]
    summary = (
        f"Dominant signal from {top.service}: {top.sample_message} "
        f"(seen {top.count} time(s) across {len(evidence)} service(s))."
    )
    likely_cause = f"repeated failures in {top.service}"
    return summary, likely_cause


def _validate(request: IncidentRequest) -> LogAnalysisResult | None:
    if not request.incident_id.strip():
        return LogAnalysisResult(
            status=AgentStatus.INVALID_ARGUMENT,
            error_message="incident_id is required",
        )
    if not request.logs:
        return LogAnalysisResult(
            status=AgentStatus.INVALID_ARGUMENT,
            error_message="logs must not be empty",
        )
    return None


def _normalize_message(message: str) -> str:
    text = message.lower().strip()
    for token in ("attempt", "request_id", "ord-", "req-"):
        if token in text:
            # Drop trailing attempt/id noise for grouping.
            text = text.split(token)[0].rstrip(" :;-")
    return " ".join(text.split())
