"""Domain models mirroring proto/incident.proto plus orchestrator-local report.

These Pydantic models are the HTTP/JSON and in-process counterparts of the
gRPC messages. Field names and enums stay aligned with the protobuf contract
so unary equivalence tests remain straightforward.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class LogLevel(str, Enum):
    UNSPECIFIED = "LOG_LEVEL_UNSPECIFIED"
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    FATAL = "FATAL"


class AgentStatus(str, Enum):
    UNSPECIFIED = "AGENT_STATUS_UNSPECIFIED"
    OK = "OK"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    UNAVAILABLE = "UNAVAILABLE"


class SeverityLevel(str, Enum):
    UNSPECIFIED = "SEVERITY_LEVEL_UNSPECIFIED"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class LogAnalysisEventType(str, Enum):
    UNSPECIFIED = "LOG_ANALYSIS_EVENT_TYPE_UNSPECIFIED"
    STARTED = "STARTED"
    EVIDENCE_FOUND = "EVIDENCE_FOUND"
    LLM_SUMMARY = "LLM_SUMMARY"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


class LogEntry(BaseModel):
    timestamp: str
    service: str
    level: LogLevel
    message: str
    metadata: dict[str, str] = Field(default_factory=dict)


class IncidentRequest(BaseModel):
    incident_id: str
    scenario: str = ""
    logs: list[LogEntry] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    service: str
    summary: str
    count: int = 0
    sample_message: str = ""


class SeverityResponse(BaseModel):
    level: SeverityLevel = SeverityLevel.UNSPECIFIED
    score: int = 0
    evidence: list[EvidenceItem] = Field(default_factory=list)
    rationale: str = ""
    status: AgentStatus = AgentStatus.OK
    error_message: str = ""


class RunbookStep(BaseModel):
    order: int
    action: str
    detail: str = ""


class RunbookMatch(BaseModel):
    runbook_id: str
    title: str
    confidence: float = 0.0
    matched_terms: list[str] = Field(default_factory=list)
    steps: list[RunbookStep] = Field(default_factory=list)


class RunbookResponse(BaseModel):
    recommendations: list[RunbookMatch] = Field(default_factory=list)
    status: AgentStatus = AgentStatus.OK
    error_message: str = ""


class LogAnalysisResult(BaseModel):
    evidence: list[EvidenceItem] = Field(default_factory=list)
    summary: str = ""
    likely_cause: str = ""
    status: AgentStatus = AgentStatus.OK
    error_message: str = ""


class LogAnalysisEvent(BaseModel):
    type: LogAnalysisEventType
    message: str = ""
    evidence: Optional[EvidenceItem] = None
    result: Optional[LogAnalysisResult] = None
    error_message: str = ""


class AgentOutcome(BaseModel):
    """Per-agent status recorded in the orchestrator report."""

    name: str
    status: AgentStatus
    error_message: str = ""
    latency_ms: Optional[float] = None


class IncidentReport(BaseModel):
    """Orchestrator-local combined report (not a gRPC message).

    Partial-report minimum: any completed unary agent response, any Log
    Analysis stream events already received, and per-agent AgentStatus.
    """

    incident_id: str
    scenario: str = ""
    severity: Optional[SeverityResponse] = None
    runbook: Optional[RunbookResponse] = None
    log_analysis: Optional[LogAnalysisResult] = None
    log_analysis_events: list[LogAnalysisEvent] = Field(default_factory=list)
    agent_outcomes: list[AgentOutcome] = Field(default_factory=list)
    partial: bool = False
