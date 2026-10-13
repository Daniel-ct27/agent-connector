"""Explicit conversions between Pydantic models and generated protobufs."""

from __future__ import annotations

from agent_connector.domain import models
from agent_connector.generated import incident_pb2 as pb


_EVENT_TO_PROTO = {
    models.LogAnalysisEventType.UNSPECIFIED: pb.LOG_ANALYSIS_EVENT_TYPE_UNSPECIFIED,
    models.LogAnalysisEventType.STARTED: pb.STARTED,
    models.LogAnalysisEventType.EVIDENCE_FOUND: pb.EVIDENCE_FOUND,
    models.LogAnalysisEventType.COMPLETED: pb.COMPLETED,
    models.LogAnalysisEventType.ERROR: pb.LOG_ANALYSIS_ERROR,
}
_EVENT_FROM_PROTO = {value: key for key, value in _EVENT_TO_PROTO.items()}


def incident_request_to_proto(value: models.IncidentRequest) -> pb.IncidentRequest:
    return pb.IncidentRequest(
        incident_id=value.incident_id,
        scenario=value.scenario,
        logs=[_log_entry_to_proto(item) for item in value.logs],
    )


def incident_request_from_proto(value: pb.IncidentRequest) -> models.IncidentRequest:
    return models.IncidentRequest(
        incident_id=value.incident_id,
        scenario=value.scenario,
        logs=[_log_entry_from_proto(item) for item in value.logs],
    )


def severity_response_to_proto(value: models.SeverityResponse) -> pb.SeverityResponse:
    return pb.SeverityResponse(
        level=pb.SeverityLevel.Value(value.level.value),
        score=value.score,
        evidence=[_evidence_to_proto(item) for item in value.evidence],
        rationale=value.rationale,
        status=pb.AgentStatus.Value(value.status.value),
        error_message=value.error_message,
    )


def severity_response_from_proto(value: pb.SeverityResponse) -> models.SeverityResponse:
    return models.SeverityResponse(
        level=models.SeverityLevel(pb.SeverityLevel.Name(value.level)),
        score=value.score,
        evidence=[_evidence_from_proto(item) for item in value.evidence],
        rationale=value.rationale,
        status=models.AgentStatus(pb.AgentStatus.Name(value.status)),
        error_message=value.error_message,
    )


def runbook_response_to_proto(value: models.RunbookResponse) -> pb.RunbookResponse:
    return pb.RunbookResponse(
        recommendations=[
            pb.RunbookMatch(
                runbook_id=item.runbook_id,
                title=item.title,
                confidence=item.confidence,
                matched_terms=item.matched_terms,
                steps=[
                    pb.RunbookStep(order=step.order, action=step.action, detail=step.detail)
                    for step in item.steps
                ],
            )
            for item in value.recommendations
        ],
        status=pb.AgentStatus.Value(value.status.value),
        error_message=value.error_message,
    )


def runbook_response_from_proto(value: pb.RunbookResponse) -> models.RunbookResponse:
    return models.RunbookResponse(
        recommendations=[
            models.RunbookMatch(
                runbook_id=item.runbook_id,
                title=item.title,
                confidence=item.confidence,
                matched_terms=list(item.matched_terms),
                steps=[
                    models.RunbookStep(
                        order=step.order,
                        action=step.action,
                        detail=step.detail,
                    )
                    for step in item.steps
                ],
            )
            for item in value.recommendations
        ],
        status=models.AgentStatus(pb.AgentStatus.Name(value.status)),
        error_message=value.error_message,
    )


def log_analysis_result_to_proto(
    value: models.LogAnalysisResult,
) -> pb.LogAnalysisResult:
    return pb.LogAnalysisResult(
        evidence=[_evidence_to_proto(item) for item in value.evidence],
        summary=value.summary,
        likely_cause=value.likely_cause,
        status=pb.AgentStatus.Value(value.status.value),
        error_message=value.error_message,
    )


def log_analysis_result_from_proto(
    value: pb.LogAnalysisResult,
) -> models.LogAnalysisResult:
    return models.LogAnalysisResult(
        evidence=[_evidence_from_proto(item) for item in value.evidence],
        summary=value.summary,
        likely_cause=value.likely_cause,
        status=models.AgentStatus(pb.AgentStatus.Name(value.status)),
        error_message=value.error_message,
    )


def log_analysis_event_to_proto(value: models.LogAnalysisEvent) -> pb.LogAnalysisEvent:
    result = pb.LogAnalysisEvent(
        type=_EVENT_TO_PROTO[value.type],
        message=value.message,
        error_message=value.error_message,
    )
    if value.evidence is not None:
        result.evidence.CopyFrom(_evidence_to_proto(value.evidence))
    if value.result is not None:
        result.result.CopyFrom(log_analysis_result_to_proto(value.result))
    return result


def log_analysis_event_from_proto(value: pb.LogAnalysisEvent) -> models.LogAnalysisEvent:
    return models.LogAnalysisEvent(
        type=_EVENT_FROM_PROTO[value.type],
        message=value.message,
        evidence=(
            _evidence_from_proto(value.evidence)
            if value.HasField("evidence")
            else None
        ),
        result=(
            log_analysis_result_from_proto(value.result)
            if value.HasField("result")
            else None
        ),
        error_message=value.error_message,
    )


def _log_entry_to_proto(value: models.LogEntry) -> pb.LogEntry:
    return pb.LogEntry(
        timestamp=value.timestamp,
        service=value.service,
        level=pb.LogLevel.Value(value.level.value),
        message=value.message,
        metadata=value.metadata,
    )


def _log_entry_from_proto(value: pb.LogEntry) -> models.LogEntry:
    return models.LogEntry(
        timestamp=value.timestamp,
        service=value.service,
        level=models.LogLevel(pb.LogLevel.Name(value.level)),
        message=value.message,
        metadata=dict(value.metadata),
    )


def _evidence_to_proto(value: models.EvidenceItem) -> pb.EvidenceItem:
    return pb.EvidenceItem(
        service=value.service,
        summary=value.summary,
        count=value.count,
        sample_message=value.sample_message,
    )


def _evidence_from_proto(value: pb.EvidenceItem) -> models.EvidenceItem:
    return models.EvidenceItem(
        service=value.service,
        summary=value.summary,
        count=value.count,
        sample_message=value.sample_message,
    )
