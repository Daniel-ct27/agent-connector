"""Conversions between domain models and transport contracts."""

from agent_connector.protocol.protobuf import (
    incident_request_from_proto,
    incident_request_to_proto,
    log_analysis_event_from_proto,
    log_analysis_event_to_proto,
    log_analysis_result_from_proto,
    log_analysis_result_to_proto,
    runbook_response_from_proto,
    runbook_response_to_proto,
    severity_response_from_proto,
    severity_response_to_proto,
)

__all__ = [
    "incident_request_from_proto",
    "incident_request_to_proto",
    "severity_response_from_proto",
    "severity_response_to_proto",
    "runbook_response_from_proto",
    "runbook_response_to_proto",
    "log_analysis_result_from_proto",
    "log_analysis_result_to_proto",
    "log_analysis_event_from_proto",
    "log_analysis_event_to_proto",
]
