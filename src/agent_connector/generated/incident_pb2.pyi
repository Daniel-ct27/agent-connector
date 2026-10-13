from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class LogLevel(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    LOG_LEVEL_UNSPECIFIED: _ClassVar[LogLevel]
    DEBUG: _ClassVar[LogLevel]
    INFO: _ClassVar[LogLevel]
    WARN: _ClassVar[LogLevel]
    ERROR: _ClassVar[LogLevel]
    FATAL: _ClassVar[LogLevel]

class AgentStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    AGENT_STATUS_UNSPECIFIED: _ClassVar[AgentStatus]
    OK: _ClassVar[AgentStatus]
    PARTIAL: _ClassVar[AgentStatus]
    FAILED: _ClassVar[AgentStatus]
    TIMEOUT: _ClassVar[AgentStatus]
    INVALID_ARGUMENT: _ClassVar[AgentStatus]
    UNAVAILABLE: _ClassVar[AgentStatus]

class SeverityLevel(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SEVERITY_LEVEL_UNSPECIFIED: _ClassVar[SeverityLevel]
    LOW: _ClassVar[SeverityLevel]
    MEDIUM: _ClassVar[SeverityLevel]
    HIGH: _ClassVar[SeverityLevel]
    CRITICAL: _ClassVar[SeverityLevel]

class LogAnalysisEventType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    LOG_ANALYSIS_EVENT_TYPE_UNSPECIFIED: _ClassVar[LogAnalysisEventType]
    STARTED: _ClassVar[LogAnalysisEventType]
    EVIDENCE_FOUND: _ClassVar[LogAnalysisEventType]
    COMPLETED: _ClassVar[LogAnalysisEventType]
    LOG_ANALYSIS_ERROR: _ClassVar[LogAnalysisEventType]
LOG_LEVEL_UNSPECIFIED: LogLevel
DEBUG: LogLevel
INFO: LogLevel
WARN: LogLevel
ERROR: LogLevel
FATAL: LogLevel
AGENT_STATUS_UNSPECIFIED: AgentStatus
OK: AgentStatus
PARTIAL: AgentStatus
FAILED: AgentStatus
TIMEOUT: AgentStatus
INVALID_ARGUMENT: AgentStatus
UNAVAILABLE: AgentStatus
SEVERITY_LEVEL_UNSPECIFIED: SeverityLevel
LOW: SeverityLevel
MEDIUM: SeverityLevel
HIGH: SeverityLevel
CRITICAL: SeverityLevel
LOG_ANALYSIS_EVENT_TYPE_UNSPECIFIED: LogAnalysisEventType
STARTED: LogAnalysisEventType
EVIDENCE_FOUND: LogAnalysisEventType
COMPLETED: LogAnalysisEventType
LOG_ANALYSIS_ERROR: LogAnalysisEventType

class LogEntry(_message.Message):
    __slots__ = ("timestamp", "service", "level", "message", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    SERVICE_FIELD_NUMBER: _ClassVar[int]
    LEVEL_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    timestamp: str
    service: str
    level: LogLevel
    message: str
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, timestamp: _Optional[str] = ..., service: _Optional[str] = ..., level: _Optional[_Union[LogLevel, str]] = ..., message: _Optional[str] = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...

class IncidentRequest(_message.Message):
    __slots__ = ("incident_id", "scenario", "logs")
    INCIDENT_ID_FIELD_NUMBER: _ClassVar[int]
    SCENARIO_FIELD_NUMBER: _ClassVar[int]
    LOGS_FIELD_NUMBER: _ClassVar[int]
    incident_id: str
    scenario: str
    logs: _containers.RepeatedCompositeFieldContainer[LogEntry]
    def __init__(self, incident_id: _Optional[str] = ..., scenario: _Optional[str] = ..., logs: _Optional[_Iterable[_Union[LogEntry, _Mapping]]] = ...) -> None: ...

class EvidenceItem(_message.Message):
    __slots__ = ("service", "summary", "count", "sample_message")
    SERVICE_FIELD_NUMBER: _ClassVar[int]
    SUMMARY_FIELD_NUMBER: _ClassVar[int]
    COUNT_FIELD_NUMBER: _ClassVar[int]
    SAMPLE_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    service: str
    summary: str
    count: int
    sample_message: str
    def __init__(self, service: _Optional[str] = ..., summary: _Optional[str] = ..., count: _Optional[int] = ..., sample_message: _Optional[str] = ...) -> None: ...

class SeverityResponse(_message.Message):
    __slots__ = ("level", "score", "evidence", "rationale", "status", "error_message")
    LEVEL_FIELD_NUMBER: _ClassVar[int]
    SCORE_FIELD_NUMBER: _ClassVar[int]
    EVIDENCE_FIELD_NUMBER: _ClassVar[int]
    RATIONALE_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    level: SeverityLevel
    score: int
    evidence: _containers.RepeatedCompositeFieldContainer[EvidenceItem]
    rationale: str
    status: AgentStatus
    error_message: str
    def __init__(self, level: _Optional[_Union[SeverityLevel, str]] = ..., score: _Optional[int] = ..., evidence: _Optional[_Iterable[_Union[EvidenceItem, _Mapping]]] = ..., rationale: _Optional[str] = ..., status: _Optional[_Union[AgentStatus, str]] = ..., error_message: _Optional[str] = ...) -> None: ...

class RunbookStep(_message.Message):
    __slots__ = ("order", "action", "detail")
    ORDER_FIELD_NUMBER: _ClassVar[int]
    ACTION_FIELD_NUMBER: _ClassVar[int]
    DETAIL_FIELD_NUMBER: _ClassVar[int]
    order: int
    action: str
    detail: str
    def __init__(self, order: _Optional[int] = ..., action: _Optional[str] = ..., detail: _Optional[str] = ...) -> None: ...

class RunbookMatch(_message.Message):
    __slots__ = ("runbook_id", "title", "confidence", "matched_terms", "steps")
    RUNBOOK_ID_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    MATCHED_TERMS_FIELD_NUMBER: _ClassVar[int]
    STEPS_FIELD_NUMBER: _ClassVar[int]
    runbook_id: str
    title: str
    confidence: float
    matched_terms: _containers.RepeatedScalarFieldContainer[str]
    steps: _containers.RepeatedCompositeFieldContainer[RunbookStep]
    def __init__(self, runbook_id: _Optional[str] = ..., title: _Optional[str] = ..., confidence: _Optional[float] = ..., matched_terms: _Optional[_Iterable[str]] = ..., steps: _Optional[_Iterable[_Union[RunbookStep, _Mapping]]] = ...) -> None: ...

class RunbookResponse(_message.Message):
    __slots__ = ("recommendations", "status", "error_message")
    RECOMMENDATIONS_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    recommendations: _containers.RepeatedCompositeFieldContainer[RunbookMatch]
    status: AgentStatus
    error_message: str
    def __init__(self, recommendations: _Optional[_Iterable[_Union[RunbookMatch, _Mapping]]] = ..., status: _Optional[_Union[AgentStatus, str]] = ..., error_message: _Optional[str] = ...) -> None: ...

class LogAnalysisResult(_message.Message):
    __slots__ = ("evidence", "summary", "likely_cause", "status", "error_message")
    EVIDENCE_FIELD_NUMBER: _ClassVar[int]
    SUMMARY_FIELD_NUMBER: _ClassVar[int]
    LIKELY_CAUSE_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    evidence: _containers.RepeatedCompositeFieldContainer[EvidenceItem]
    summary: str
    likely_cause: str
    status: AgentStatus
    error_message: str
    def __init__(self, evidence: _Optional[_Iterable[_Union[EvidenceItem, _Mapping]]] = ..., summary: _Optional[str] = ..., likely_cause: _Optional[str] = ..., status: _Optional[_Union[AgentStatus, str]] = ..., error_message: _Optional[str] = ...) -> None: ...

class LogAnalysisEvent(_message.Message):
    __slots__ = ("type", "message", "evidence", "result", "error_message")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    EVIDENCE_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    type: LogAnalysisEventType
    message: str
    evidence: EvidenceItem
    result: LogAnalysisResult
    error_message: str
    def __init__(self, type: _Optional[_Union[LogAnalysisEventType, str]] = ..., message: _Optional[str] = ..., evidence: _Optional[_Union[EvidenceItem, _Mapping]] = ..., result: _Optional[_Union[LogAnalysisResult, _Mapping]] = ..., error_message: _Optional[str] = ...) -> None: ...
