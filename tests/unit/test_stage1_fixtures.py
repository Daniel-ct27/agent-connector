"""Stage 1 checks: sample incidents load and severity matches expected contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_connector.agents.severity import analyze_severity
from agent_connector.domain.models import AgentStatus, IncidentRequest, SeverityLevel

FIXTURES = Path(__file__).resolve().parents[2] / "scenarios" / "fixtures"
EXPECTED = FIXTURES / "expected"

INCIDENTS = (
    "inc-db-001.json",
    "inc-retry-001.json",
    "inc-cert-001.json",
)


@pytest.mark.parametrize("name", INCIDENTS)
def test_sample_incident_loads(name: str) -> None:
    raw = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    request = IncidentRequest.model_validate(raw)

    assert request.incident_id
    assert request.scenario
    assert len(request.logs) >= 2
    services = {entry.service for entry in request.logs}
    assert len(services) >= 2


@pytest.mark.parametrize("name", INCIDENTS)
def test_severity_matches_expected_contract(name: str) -> None:
    request = IncidentRequest.model_validate(
        json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    )
    expected = json.loads((EXPECTED / name).read_text(encoding="utf-8"))
    severity_spec = expected["severity"]

    result = analyze_severity(request)

    assert result.status == AgentStatus(severity_spec["status"])
    assert result.level == SeverityLevel(severity_spec["level"])
    assert result.score >= severity_spec["score_min"]
    evidence_services = {item.service for item in result.evidence}
    assert evidence_services == set(severity_spec["evidence_services"])


@pytest.mark.parametrize("name", INCIDENTS)
def test_expected_output_contract_shape(name: str) -> None:
    expected = json.loads((EXPECTED / name).read_text(encoding="utf-8"))

    assert expected["incident_id"]
    assert "severity" in expected
    assert "runbook" in expected
    assert "log_analysis" in expected
    assert expected["runbook"]["top_runbook_id"]
    assert expected["log_analysis"]["stream_event_order"] == [
        "STARTED",
        "EVIDENCE_FOUND",
        "LLM_SUMMARY",
        "COMPLETED",
    ]
