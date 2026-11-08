"""HTTP adapter tests for the Runbook Agent."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from agent_connector.agents.runbook import recommend_actions
from agent_connector.domain.models import IncidentRequest, RunbookResponse
from agent_connector.http_services.runbook import create_runbook_app


FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "scenarios"
    / "fixtures"
    / "inc-db-001.json"
)


def _load_request() -> IncidentRequest:
    return IncidentRequest.model_validate(
        json.loads(FIXTURE.read_text(encoding="utf-8"))
    )


def test_recommend_actions_matches_direct_result() -> None:
    incident = _load_request()
    client = TestClient(create_runbook_app())
    response = client.post(
        "/v1/runbook/recommend",
        json=incident.model_dump(mode="json"),
    )
    assert response.status_code == 200
    assert RunbookResponse.model_validate(response.json()) == recommend_actions(
        incident
    )


def test_invalid_request_returns_400() -> None:
    client = TestClient(create_runbook_app())
    response = client.post(
        "/v1/runbook/recommend",
        json={"incident_id": "inc-empty", "scenario": "", "logs": []},
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "logs must not be empty"}
