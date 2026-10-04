"""Unit tests for the Runbook Agent core logic."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_connector.agents.runbook import recommend_actions
from agent_connector.domain.models import (
    AgentStatus,
    IncidentRequest,
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
def test_recommend_actions_matches_expected_top_runbook(name: str) -> None:
    request = _load_incident(name)
    expected = json.loads((EXPECTED / name).read_text(encoding="utf-8"))["runbook"]

    result = recommend_actions(request)

    assert result.status == AgentStatus(expected["status"])
    assert len(result.recommendations) >= expected["min_recommendations"]
    top = result.recommendations[0]
    assert top.runbook_id == expected["top_runbook_id"]
    assert top.steps
    assert top.confidence > 0
    matched_lower = {term.lower() for term in top.matched_terms}
    assert any(
        term.lower() in matched_lower or term.lower() in " ".join(matched_lower)
        for term in expected["required_matched_terms_any"]
    )


def test_recommend_actions_rejects_missing_incident_id() -> None:
    request = IncidentRequest(
        incident_id="",
        logs=[
            LogEntry(
                timestamp="2026-03-15T14:00:00Z",
                service="api",
                level=LogLevel.ERROR,
                message="database connection timeout",
            )
        ],
    )

    result = recommend_actions(request)

    assert result.status == AgentStatus.INVALID_ARGUMENT
    assert "incident_id" in result.error_message


def test_recommend_actions_rejects_empty_logs() -> None:
    result = recommend_actions(IncidentRequest(incident_id="inc-empty", logs=[]))

    assert result.status == AgentStatus.INVALID_ARGUMENT
    assert "logs" in result.error_message


def test_recommend_actions_returns_empty_when_no_keywords_match() -> None:
    request = IncidentRequest(
        incident_id="inc-noise",
        scenario="unrelated",
        logs=[
            LogEntry(
                timestamp="2026-03-15T14:00:00Z",
                service="metrics-agent",
                level=LogLevel.INFO,
                message="heartbeat ok",
            )
        ],
    )

    result = recommend_actions(request)

    assert result.status == AgentStatus.OK
    assert result.recommendations == []
