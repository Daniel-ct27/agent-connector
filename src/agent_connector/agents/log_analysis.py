"""Log Analysis agent: local preprocessing plus deterministic stub summary.

Live LLM integration is deferred (Stage 5). Stream event generation is
protocol-agnostic so gRPC can wrap it later.
"""

from __future__ import annotations

from collections.abc import Iterator

from agent_connector.agents.evidence import extract_evidence
from agent_connector.domain.models import (
    AgentStatus,
    EvidenceItem,
    IncidentRequest,
    LogAnalysisEvent,
    LogAnalysisEventType,
    LogAnalysisResult,
)

# Stable outputs used only by the three protocol-comparison fixtures. This is
# not the production analysis path; unknown scenarios use the log-derived
# fallback below until a real analyzer provider replaces this stub.
_FIXTURE_SUMMARIES = {
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


def stub_summarize(
    request: IncidentRequest,
    evidence: list[EvidenceItem],
) -> tuple[str, str]:
    """Deterministic protocol-test substitute for the future analyzer."""
    if request.scenario in _FIXTURE_SUMMARIES:
        return _FIXTURE_SUMMARIES[request.scenario]

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
