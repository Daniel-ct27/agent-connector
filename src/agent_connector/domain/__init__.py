"""Shared domain types for agent-connector."""

from agent_connector.domain.models import (
    AgentOutcome,
    AgentStatus,
    EvidenceItem,
    IncidentReport,
    IncidentRequest,
    LogAnalysisEvent,
    LogAnalysisEventType,
    LogAnalysisResult,
    LogEntry,
    LogLevel,
    RunbookMatch,
    RunbookResponse,
    RunbookStep,
    SeverityLevel,
    SeverityResponse,
)
from agent_connector.config import MAX_LOG_ENTRIES
from agent_connector.domain.validation import (
    IncidentValidationError,
    validate_incident_request,
)

__all__ = [
    "AgentOutcome",
    "AgentStatus",
    "EvidenceItem",
    "IncidentReport",
    "IncidentRequest",
    "LogAnalysisEvent",
    "LogAnalysisEventType",
    "LogAnalysisResult",
    "LogEntry",
    "LogLevel",
    "RunbookMatch",
    "RunbookResponse",
    "RunbookStep",
    "SeverityLevel",
    "SeverityResponse",
    "MAX_LOG_ENTRIES",
    "IncidentValidationError",
    "validate_incident_request",
]
