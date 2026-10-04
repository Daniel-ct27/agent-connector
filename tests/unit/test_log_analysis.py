"""Unit tests for the Log Analysis agent core logic."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_connector.agents.log_analysis import analyze_logs, analyze_logs_stream
from agent_connector.domain.models import (
    AgentStatus,
    IncidentRequest,
    LogAnalysisEventType,
    LogEntry,
    LogLevel,
)

FIXTURES = Path(__file__).resolve().parents[2] / "scenarios" / "fixtures"
EXPECTED = FIXTURES / "expected"

INCIDENTS = (
    "inc-db-001.json",
    "inc-retry-001.json",
    "inc-cert-001.json",
)


def _load_incident(name: str) -> IncidentRequest:
    return IncidentRequest.model_validate(
        json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    )


@pytest.mark.parametrize("name", INCIDENTS)
def test_analyze_logs_matches_expected_contract(name: str) -> None:
    request = _load_incident(name)
    expected = json.loads((EXPECTED / name).read_text(encoding="utf-8"))["log_analysis"]

    result = analyze_logs(request)

    assert result.status == AgentStatus(expected["status"])
    assert result.summary
    cause = result.likely_cause.lower()
    assert any(token.lower() in cause for token in expected["likely_cause_contains_any"])
    evidence_services = {item.service for item in result.evidence}
    assert set(expected["evidence_services"]).issubset(evidence_services)


@pytest.mark.parametrize("name", INCIDENTS)
def test_analyze_logs_stream_event_order_and_final_result(name: str) -> None:
    request = _load_incident(name)
    expected = json.loads((EXPECTED / name).read_text(encoding="utf-8"))["log_analysis"]

    events = list(analyze_logs_stream(request))
    types = [event.type for event in events]

    compact: list[LogAnalysisEventType] = []
    for event_type in types:
        if (
            event_type == LogAnalysisEventType.EVIDENCE_FOUND
            and compact
            and compact[-1] == LogAnalysisEventType.EVIDENCE_FOUND
        ):
            continue
        compact.append(event_type)

    assert [event_type.value for event_type in compact] == expected["stream_event_order"]

    unary = analyze_logs(request)
    completed = events[-1].result
    assert completed is not None
    assert completed.summary == unary.summary
    assert completed.likely_cause == unary.likely_cause
    assert completed.evidence == unary.evidence


def test_analyze_logs_rejects_missing_incident_id() -> None:
    request = IncidentRequest(
        incident_id=" ",
        logs=[
            LogEntry(
                timestamp="2026-03-15T14:00:00Z",
                service="api",
                level=LogLevel.ERROR,
                message="boom",
            )
        ],
    )

    result = analyze_logs(request)

    assert result.status == AgentStatus.INVALID_ARGUMENT
    assert "incident_id" in result.error_message


def test_analyze_logs_rejects_empty_logs() -> None:
    result = analyze_logs(IncidentRequest(incident_id="inc-empty", logs=[]))

    assert result.status == AgentStatus.INVALID_ARGUMENT
    assert "logs" in result.error_message


def test_analyze_logs_stream_emits_error_for_invalid_request() -> None:
    events = list(analyze_logs_stream(IncidentRequest(incident_id="inc-empty", logs=[])))

    assert len(events) == 1
    assert events[0].type == LogAnalysisEventType.ERROR
    assert events[0].result is not None
    assert events[0].result.status == AgentStatus.INVALID_ARGUMENT
