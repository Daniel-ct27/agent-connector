"""Log Analysis agent: local preprocessing plus pluggable summarizer."""

from __future__ import annotations

from collections.abc import Iterator

from agent_connector.agents.evidence import extract_evidence
from agent_connector.analyzers.base import Analyzer, AnalyzerError, AnalyzerOutput
from agent_connector.analyzers.deterministic import DeterministicAnalyzer
from agent_connector.domain.models import (
    AgentStatus,
    EvidenceItem,
    IncidentRequest,
    LogAnalysisEvent,
    LogAnalysisEventType,
    LogAnalysisResult,
)
from agent_connector.domain.validation import (
    IncidentValidationError,
    validate_incident_request,
)

_DEFAULT_ANALYZER = DeterministicAnalyzer()


def analyze_logs(
    request: IncidentRequest,
    *,
    analyzer: Analyzer | None = None,
) -> LogAnalysisResult:
    """Unary log analysis used by the fair protocol comparison path."""
    invalid = _validate(request)
    if invalid is not None:
        return invalid

    evidence = extract_evidence(request.logs)
    active = analyzer or _DEFAULT_ANALYZER
    try:
        output = active.summarize(request, evidence)
    except AnalyzerError as error:
        return LogAnalysisResult(
            evidence=evidence,
            status=AgentStatus.FAILED,
            error_message=str(error),
        )
    return LogAnalysisResult(
        evidence=evidence,
        summary=output.summary,
        likely_cause=output.likely_cause,
        status=AgentStatus.OK,
    )


def analyze_logs_stream(
    request: IncidentRequest,
    *,
    analyzer: Analyzer | None = None,
) -> Iterator[LogAnalysisEvent]:
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

    active = analyzer or _DEFAULT_ANALYZER
    try:
        output = active.summarize(request, evidence)
    except AnalyzerError as error:
        failed = LogAnalysisResult(
            evidence=evidence,
            status=AgentStatus.FAILED,
            error_message=str(error),
        )
        yield LogAnalysisEvent(
            type=LogAnalysisEventType.ERROR,
            message=str(error),
            error_message=str(error),
            result=failed,
        )
        return

    completed = LogAnalysisResult(
        evidence=evidence,
        summary=output.summary,
        likely_cause=output.likely_cause,
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
    """Backward-compatible wrapper around DeterministicAnalyzer."""
    output: AnalyzerOutput = DeterministicAnalyzer().summarize(request, evidence)
    return output.summary, output.likely_cause


def _validate(request: IncidentRequest) -> LogAnalysisResult | None:
    try:
        validate_incident_request(request)
    except IncidentValidationError as error:
        return LogAnalysisResult(
            status=AgentStatus.INVALID_ARGUMENT,
            error_message=str(error),
        )
    return None
