"""Unit tests for the Severity Agent core logic."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_connector.agents.severity import analyze_severity
from agent_connector.domain.models import (
    AgentStatus,
    IncidentRequest,
    LogEntry,
    LogLevel,
    SeverityLevel,
)

FIXTURES = Path(__file__).resolve().parents[2] / "scenarios" / "fixtures"


def _load_incident(name: str) -> IncidentRequest:
    raw = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return IncidentRequest.model_validate(raw)


def test_analyze_severity_db_fixture_is_critical() -> None:
    request = _load_incident("inc-db-001.json")

    result = analyze_severity(request)

    assert result.status == AgentStatus.OK
    assert result.level == SeverityLevel.CRITICAL
    assert result.score >= 75
    assert result.rationale
    services = {item.service for item in result.evidence}
    assert "checkout-service" in services
    assert "orders-db" in services
    assert all(item.count > 0 for item in result.evidence)


def test_analyze_severity_rejects_missing_incident_id() -> None:
    request = IncidentRequest(
        incident_id="  ",
        logs=[
            LogEntry(
                timestamp="2026-03-15T14:00:00Z",
                service="api",
                level=LogLevel.ERROR,
                message="boom",
            )
        ],
    )

    result = analyze_severity(request)

    assert result.status == AgentStatus.INVALID_ARGUMENT
    assert "incident_id" in result.error_message


def test_analyze_severity_rejects_empty_logs() -> None:
    request = IncidentRequest(incident_id="inc-empty", logs=[])

    result = analyze_severity(request)

    assert result.status == AgentStatus.INVALID_ARGUMENT
    assert "logs" in result.error_message


@pytest.mark.parametrize(
    ("error_count", "services", "stretch_duration", "expected_level"),
    [
        (1, 1, False, SeverityLevel.LOW),
        (2, 2, False, SeverityLevel.MEDIUM),
        (4, 2, True, SeverityLevel.HIGH),
    ],
)
def test_analyze_severity_level_bands(
    error_count: int,
    services: int,
    stretch_duration: bool,
    expected_level: SeverityLevel,
) -> None:
    logs = [
        LogEntry(
            timestamp=f"2026-03-15T14:00:{i:02d}Z",
            service=f"svc-{i % services}",
            level=LogLevel.ERROR,
            message=f"error {i}",
        )
        for i in range(error_count)
    ]
    if stretch_duration:
        logs[-1] = logs[-1].model_copy(update={"timestamp": "2026-03-15T14:00:15Z"})

    result = analyze_severity(IncidentRequest(incident_id="inc-bands", logs=logs))

    assert result.status == AgentStatus.OK
    assert result.level == expected_level
