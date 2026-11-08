"""HTTP adapter tests for the Severity Agent."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from agent_connector.agents.severity import analyze_severity
from agent_connector.config import MAX_HTTP_REQUEST_BYTES
from agent_connector.domain.models import IncidentRequest, SeverityResponse
from agent_connector.http_services.severity import create_severity_app


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


def test_analyze_severity_matches_direct_result() -> None:
    incident = _load_request()
    client = TestClient(create_severity_app())
    response = client.post("/v1/severity/analyze", json=incident.model_dump(mode="json"))
    assert response.status_code == 200
    assert SeverityResponse.model_validate(response.json()) == analyze_severity(
        incident
    )


def test_invalid_request_returns_400() -> None:
    client = TestClient(create_severity_app())
    response = client.post(
        "/v1/severity/analyze",
        json={"incident_id": "inc-empty", "scenario": "", "logs": []},
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "logs must not be empty"}


def test_oversized_content_length_returns_400() -> None:
    client = TestClient(create_severity_app())
    response = client.post(
        "/v1/severity/analyze",
        content=b"{}",
        headers={
            "content-length": str(MAX_HTTP_REQUEST_BYTES),
            "content-type": "application/json",
        },
    )
    assert response.status_code == 400
    assert "smaller than" in response.json()["detail"]


def test_oversized_body_returns_400() -> None:
    client = TestClient(create_severity_app())
    # Build a JSON body at the shared ceiling without relying on Content-Length.
    padding = "x" * MAX_HTTP_REQUEST_BYTES
    payload = (
        '{"incident_id":"inc-big","scenario":"","logs":['
        f'{{"timestamp":"2024-01-01T00:00:00Z","service":"api",'
        f'"level":"ERROR","message":"{padding}"}}'
        "]}"
    ).encode("utf-8")
    assert len(payload) >= MAX_HTTP_REQUEST_BYTES
    response = client.post(
        "/v1/severity/analyze",
        content=payload,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    assert "smaller than" in response.json()["detail"]


def test_internal_failure_returns_500() -> None:
    def boom(_request: IncidentRequest) -> SeverityResponse:
        raise RuntimeError("boom")

    client = TestClient(create_severity_app(analyzer=boom), raise_server_exceptions=False)
    incident = _load_request()
    response = client.post("/v1/severity/analyze", json=incident.model_dump(mode="json"))
    assert response.status_code == 500
    assert response.json() == {"detail": "internal agent error"}
