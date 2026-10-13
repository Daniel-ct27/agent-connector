"""Unit tests for the Severity Agent core logic."""

from __future__ import annotations

import json
from pathlib import Path

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


def test_analyze_severity_db_fixture_is_medium() -> None:
    request = _load_incident("inc-db-001.json")

    result = analyze_severity(request)

    assert result.status == AgentStatus.OK
    assert result.level == SeverityLevel.MEDIUM
    assert result.score == 37
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


def _request_with_errors(error_count: int, services: int) -> IncidentRequest:
    logs = [
        LogEntry(
            timestamp="2026-03-15T14:00:00Z",
            service=f"svc-{i % services}",
            level=LogLevel.ERROR,
            message=f"error {i}",
        )
        for i in range(error_count)
    ]
    return IncidentRequest(incident_id="inc-weighted", logs=logs)


def test_high_isolated_volume_scores_above_small_wide_incident() -> None:
    isolated = analyze_severity(_request_with_errors(error_count=100, services=1))
    wide = analyze_severity(_request_with_errors(error_count=5, services=5))

    assert isolated.score > wide.score
    assert isolated.level == SeverityLevel.HIGH
    assert wide.level == SeverityLevel.MEDIUM


def test_wider_reach_scores_higher_for_equal_volume() -> None:
    isolated = analyze_severity(_request_with_errors(error_count=20, services=1))
    wide = analyze_severity(_request_with_errors(error_count=20, services=4))

    assert wide.score > isolated.score


def test_info_logs_do_not_increase_breadth_or_duration() -> None:
    base = _request_with_errors(error_count=10, services=1)
    with_info = base.model_copy(
        update={
            "logs": base.logs
            + [
                LogEntry(
                    timestamp="2026-03-15T15:00:00Z",
                    service=f"healthy-{i}",
                    level=LogLevel.INFO,
                    message="health check passed",
                )
                for i in range(10)
            ]
        }
    )

    assert analyze_severity(with_info).score == analyze_severity(base).score


def test_longer_error_duration_scores_higher() -> None:
    brief = _request_with_errors(error_count=10, services=1)
    persistent = brief.model_copy(
        update={
            "logs": brief.logs[:-1]
            + [brief.logs[-1].model_copy(update={"timestamp": "2026-03-15T14:05:00Z"})]
        }
    )

    assert analyze_severity(persistent).score > analyze_severity(brief).score


def test_fatal_log_scores_higher_than_error_at_equal_volume() -> None:
    errors = _request_with_errors(error_count=10, services=1)
    fatal = errors.model_copy(
        update={
            "logs": errors.logs[:-1]
            + [errors.logs[-1].model_copy(update={"level": LogLevel.FATAL})]
        }
    )

    assert analyze_severity(fatal).score > analyze_severity(errors).score
