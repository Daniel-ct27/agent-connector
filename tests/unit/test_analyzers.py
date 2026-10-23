"""Unit tests for deterministic and OpenAI analyzer providers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent_connector.analyzers.base import (
    AnalyzerConfigError,
    AnalyzerError,
    AnalyzerOutput,
)
from agent_connector.analyzers.deterministic import DeterministicAnalyzer
from agent_connector.analyzers.factory import build_analyzer
from agent_connector.analyzers.openai_provider import OpenAIAnalyzer
from agent_connector.agents.log_analysis import analyze_logs, analyze_logs_stream
from agent_connector.config import LLM_TIMEOUT_ENV_VAR
from agent_connector.domain.models import (
    AgentStatus,
    EvidenceItem,
    IncidentRequest,
    LogAnalysisEventType,
    LogEntry,
    LogLevel,
)


def test_deterministic_analyzer_uses_fixture_table() -> None:
    request = IncidentRequest(incident_id="inc-1", scenario="db_connection_failure")
    output = DeterministicAnalyzer().summarize(request, [])
    assert "database" in output.likely_cause.lower()


def test_build_analyzer_defaults_to_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_CONNECTOR_ANALYZER", raising=False)
    assert build_analyzer().name == "deterministic"
    assert build_analyzer("stub").name == "deterministic"


def test_build_analyzer_rejects_unknown_name() -> None:
    with pytest.raises(AnalyzerConfigError, match="unknown analyzer"):
        build_analyzer("nope")


def test_build_analyzer_rejects_invalid_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_CONNECTOR_ANALYZER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv(LLM_TIMEOUT_ENV_VAR, "abc")
    with pytest.raises(AnalyzerConfigError, match="positive number"):
        build_analyzer()


def test_build_analyzer_requires_api_key_for_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_CONNECTOR_ANALYZER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AGENT_CONNECTOR_OPENAI_API_KEY", raising=False)
    with pytest.raises(AnalyzerConfigError, match="OPENAI_API_KEY"):
        build_analyzer("live")


def test_build_analyzer_accepts_live_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    analyzer = build_analyzer("live")
    assert analyzer.name == "openai"


def test_analyze_logs_uses_injected_analyzer() -> None:
    class FixedAnalyzer:
        name = "fixed"

        def summarize(self, request, evidence):
            return AnalyzerOutput(summary="custom summary", likely_cause="custom cause")

    request = IncidentRequest(
        incident_id="inc-1",
        scenario="x",
        logs=[
            LogEntry(
                timestamp="2026-03-15T14:00:00Z",
                service="api",
                level=LogLevel.ERROR,
                message="boom",
            )
        ],
    )
    result = analyze_logs(request, analyzer=FixedAnalyzer())
    assert result.summary == "custom summary"
    assert result.likely_cause == "custom cause"
    assert result.status == AgentStatus.OK


def test_analyze_logs_maps_analyzer_error_to_failed() -> None:
    class BrokenAnalyzer:
        name = "broken"

        def summarize(self, request, evidence):
            raise AnalyzerError("live log analysis failed")

    request = IncidentRequest(
        incident_id="inc-1",
        scenario="x",
        logs=[
            LogEntry(
                timestamp="2026-03-15T14:00:00Z",
                service="api",
                level=LogLevel.ERROR,
                message="boom",
            )
        ],
    )
    result = analyze_logs(request, analyzer=BrokenAnalyzer())
    assert result.status == AgentStatus.FAILED
    assert result.error_message == "live log analysis failed"
    assert result.evidence


def test_analyze_logs_stream_emits_error_on_analyzer_failure() -> None:
    class BrokenAnalyzer:
        name = "broken"

        def summarize(self, request, evidence):
            raise AnalyzerError("live log analysis failed")

    request = IncidentRequest(
        incident_id="inc-1",
        scenario="x",
        logs=[
            LogEntry(
                timestamp="2026-03-15T14:00:00Z",
                service="api",
                level=LogLevel.ERROR,
                message="boom",
            )
        ],
    )
    events = list(analyze_logs_stream(request, analyzer=BrokenAnalyzer()))
    assert events[0].type == LogAnalysisEventType.STARTED
    assert events[-1].type == LogAnalysisEventType.ERROR
    assert events[-1].result is not None
    assert events[-1].result.status == AgentStatus.FAILED


def test_openai_analyzer_parses_json_response() -> None:
    class FakeCompletions:
        def create(self, **_kwargs):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content='{"summary":"db timeouts","likely_cause":"orders-db"}'
                        )
                    )
                ]
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    analyzer = OpenAIAnalyzer(
        api_key="test-key",
        model="gpt-4o-mini",
        timeout_s=5.0,
        client=client,
    )
    output = analyzer.summarize(
        IncidentRequest(incident_id="inc-1", scenario="x"),
        [EvidenceItem(service="orders-db", summary="timeout", count=2)],
    )
    assert output == AnalyzerOutput(summary="db timeouts", likely_cause="orders-db")


def test_openai_analyzer_sanitizes_provider_failures() -> None:
    class FakeCompletions:
        def create(self, **_kwargs):
            raise RuntimeError("secret api detail")

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    analyzer = OpenAIAnalyzer(
        api_key="test-key",
        model="gpt-4o-mini",
        timeout_s=5.0,
        client=client,
    )
    with pytest.raises(AnalyzerError, match="live log analysis failed") as captured:
        analyzer.summarize(IncidentRequest(incident_id="inc-1"), [])
    assert "secret api detail" not in str(captured.value)
