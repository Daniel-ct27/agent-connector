"""Tests for shared incident-request validation."""

from __future__ import annotations

import pytest

from agent_connector.agents.log_analysis import analyze_logs
from agent_connector.agents.runbook import recommend_actions
from agent_connector.agents.severity import analyze_severity
from agent_connector.domain.models import (
    AgentStatus,
    IncidentRequest,
    LogEntry,
    LogLevel,
)
from agent_connector.domain.validation import (
    MAX_LOG_ENTRIES,
    IncidentValidationError,
    validate_incident_request,
)


def _log() -> LogEntry:
    return LogEntry(
        timestamp="2026-03-15T14:00:00Z",
        service="api",
        level=LogLevel.ERROR,
        message="request failed",
    )


def test_accepts_valid_incident() -> None:
    validate_incident_request(
        IncidentRequest(incident_id="inc-valid", logs=[_log()])
    )


@pytest.mark.parametrize("incident_id", ["", " ", "\t\r\n"])
def test_rejects_blank_incident_id(incident_id: str) -> None:
    request = IncidentRequest(incident_id=incident_id, logs=[_log()])

    with pytest.raises(IncidentValidationError, match="incident_id is required"):
        validate_incident_request(request)


def test_rejects_empty_logs() -> None:
    request = IncidentRequest(incident_id="inc-empty")

    with pytest.raises(IncidentValidationError, match="logs must not be empty"):
        validate_incident_request(request)


def test_accepts_exact_log_limit() -> None:
    request = IncidentRequest(
        incident_id="inc-limit",
        logs=[_log()] * MAX_LOG_ENTRIES,
    )

    validate_incident_request(request)


def test_rejects_more_than_log_limit() -> None:
    request = IncidentRequest(
        incident_id="inc-too-large",
        logs=[_log()] * (MAX_LOG_ENTRIES + 1),
    )

    with pytest.raises(
        IncidentValidationError,
        match=f"at most {MAX_LOG_ENTRIES} entries",
    ):
        validate_incident_request(request)


def test_unary_agents_apply_shared_log_limit() -> None:
    request = IncidentRequest(
        incident_id="inc-too-large",
        logs=[_log()] * (MAX_LOG_ENTRIES + 1),
    )

    for analyze in (analyze_severity, recommend_actions, analyze_logs):
        result = analyze(request)

        assert result.status == AgentStatus.INVALID_ARGUMENT
        assert result.error_message == (
            f"logs must contain at most {MAX_LOG_ENTRIES} entries"
        )
