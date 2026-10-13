"""Round-trip tests for domain/protobuf conversion boundaries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_connector.agents.log_analysis import analyze_logs_stream
from agent_connector.agents.runbook import recommend_actions
from agent_connector.agents.severity import analyze_severity
from agent_connector.domain.models import IncidentRequest, LogAnalysisEventType
from agent_connector.generated import incident_pb2 as pb
from agent_connector.protocol.protobuf import (
    incident_request_from_proto,
    incident_request_to_proto,
    log_analysis_event_from_proto,
    log_analysis_event_to_proto,
    runbook_response_from_proto,
    runbook_response_to_proto,
    severity_response_from_proto,
    severity_response_to_proto,
)


FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "scenarios"
    / "fixtures"
    / "inc-db-001.json"
)


@pytest.fixture
def incident() -> IncidentRequest:
    return IncidentRequest.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))


def test_incident_request_round_trip(incident: IncidentRequest) -> None:
    assert incident_request_from_proto(incident_request_to_proto(incident)) == incident


def test_severity_response_round_trip(incident: IncidentRequest) -> None:
    response = analyze_severity(incident)
    assert severity_response_from_proto(severity_response_to_proto(response)) == response


def test_runbook_response_round_trip(incident: IncidentRequest) -> None:
    response = recommend_actions(incident)
    converted = runbook_response_from_proto(runbook_response_to_proto(response))
    assert converted.model_dump(exclude={"recommendations": {"__all__": {"confidence"}}}) == (
        response.model_dump(exclude={"recommendations": {"__all__": {"confidence"}}})
    )
    assert converted.recommendations[0].confidence == pytest.approx(
        response.recommendations[0].confidence,
        abs=1e-6,
    )


def test_log_analysis_events_round_trip(incident: IncidentRequest) -> None:
    for event in analyze_logs_stream(incident):
        assert log_analysis_event_from_proto(log_analysis_event_to_proto(event)) == event


def test_domain_error_event_uses_prefixed_proto_symbol() -> None:
    event = log_analysis_event_to_proto(
        list(analyze_logs_stream(IncidentRequest(incident_id="empty")))[0]
    )

    assert event.type == pb.LOG_ANALYSIS_ERROR
    assert log_analysis_event_from_proto(event).type == LogAnalysisEventType.ERROR
