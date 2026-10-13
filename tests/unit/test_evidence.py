"""Tests for the shared evidence contract."""

from agent_connector.agents.evidence import extract_evidence
from agent_connector.agents.log_analysis import analyze_logs
from agent_connector.agents.severity import analyze_severity
from agent_connector.domain.models import IncidentRequest, LogEntry, LogLevel


def test_evidence_groups_by_service_and_normalized_pattern() -> None:
    request = IncidentRequest(
        incident_id="inc-evidence",
        logs=[
            LogEntry(
                timestamp="2026-03-15T14:00:00Z",
                service="checkout",
                level=LogLevel.ERROR,
                message="database timeout attempt 1",
            ),
            LogEntry(
                timestamp="2026-03-15T14:00:01Z",
                service="checkout",
                level=LogLevel.ERROR,
                message="database timeout attempt 2",
            ),
            LogEntry(
                timestamp="2026-03-15T14:00:02Z",
                service="checkout",
                level=LogLevel.ERROR,
                message="connection refused",
            ),
        ],
    )

    evidence = extract_evidence(request.logs)

    assert [(item.service, item.summary, item.count) for item in evidence] == [
        ("checkout", "database timeout", 2),
        ("checkout", "connection refused", 1),
    ]
    assert evidence[0].sample_message == "database timeout attempt 1"


def test_agents_share_the_same_evidence_contract() -> None:
    request = IncidentRequest(
        incident_id="inc-shared-evidence",
        logs=[
            LogEntry(
                timestamp="2026-03-15T14:00:00Z",
                service="api",
                level=LogLevel.ERROR,
                message="upstream timeout request_id req-1",
            ),
            LogEntry(
                timestamp="2026-03-15T14:00:01Z",
                service="api",
                level=LogLevel.ERROR,
                message="upstream timeout request_id req-2",
            ),
        ],
    )

    assert analyze_severity(request).evidence == analyze_logs(request).evidence
