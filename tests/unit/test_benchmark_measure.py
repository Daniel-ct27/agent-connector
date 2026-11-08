"""Unit tests for Stage 7 measurement helpers."""

from __future__ import annotations

from agent_connector.benchmarks.fixtures import generate_incident
from agent_connector.benchmarks.measure import request_bytes_for, response_bytes_for
from agent_connector.domain.models import (
    AgentOutcome,
    AgentStatus,
    IncidentReport,
    SeverityLevel,
    SeverityResponse,
)
from agent_connector.protocol.protobuf import incident_request_to_proto


def test_request_bytes_match_locked_definitions() -> None:
    incident = generate_incident(100)
    http_bytes = request_bytes_for("http", incident)
    grpc_bytes = request_bytes_for("grpc", incident)
    assert http_bytes == len(incident.model_dump_json().encode("utf-8"))
    assert grpc_bytes == incident_request_to_proto(incident).ByteSize()
    assert http_bytes > 0
    assert grpc_bytes > 0


def test_response_bytes_count_present_agents_only() -> None:
    report = IncidentReport(
        incident_id="inc-bench-100",
        scenario="db_connection_failure",
        severity=SeverityResponse(
            level=SeverityLevel.HIGH,
            score=70,
            status=AgentStatus.OK,
        ),
        agent_outcomes=[
            AgentOutcome(name="severity", status=AgentStatus.OK),
        ],
    )
    assert response_bytes_for("http", report) > 0
    assert response_bytes_for("grpc", report) > 0
