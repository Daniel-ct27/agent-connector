"""HTTP adapter tests for the Log Analysis Agent."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from agent_connector.agents.log_analysis import analyze_logs
from agent_connector.analyzers import DeterministicAnalyzer
from agent_connector.domain.models import IncidentRequest, LogAnalysisResult
from agent_connector.http_services.log_analysis import create_log_analysis_app


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


def test_analyze_logs_matches_direct_result() -> None:
    incident = _load_request()
    analyzer = DeterministicAnalyzer()

    def unary(request: IncidentRequest) -> LogAnalysisResult:
        return analyze_logs(request, analyzer=analyzer)

    client = TestClient(create_log_analysis_app(unary))
    response = client.post(
        "/v1/log-analysis/analyze",
        json=incident.model_dump(mode="json"),
    )
    assert response.status_code == 200
    assert LogAnalysisResult.model_validate(response.json()) == analyze_logs(
        incident,
        analyzer=analyzer,
    )


def test_invalid_request_returns_400() -> None:
    client = TestClient(create_log_analysis_app())
    response = client.post(
        "/v1/log-analysis/analyze",
        json={"incident_id": "inc-empty", "scenario": "", "logs": []},
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "logs must not be empty"}
