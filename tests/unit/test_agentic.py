"""Unit tests for LLM-agnostic agentic infrastructure."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from agent_connector.agentic.loop import run_agentic
from agent_connector.agentic.observe import observe_incident
from agent_connector.agentic.providers import (
    CloudflareWorkersAIPlanner,
    DeterministicPlanner,
    HttpJsonPlanner,
    OpenAICompatiblePlanner,
    PlannerContext,
    build_planner,
)
from agent_connector.agentic.schema import parse_plan_json
from agent_connector.agentic.tools import (
    TOOL_ANALYZE_LOGS,
    TOOL_ANALYZE_SEVERITY,
    TOOL_FINISH,
    TOOL_RECOMMEND_RUNBOOK,
)
from agent_connector.domain.models import IncidentRequest, LogEntry, LogLevel


FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "scenarios"
    / "fixtures"
    / "inc-db-001.json"
)


def _load_db_incident() -> IncidentRequest:
    return IncidentRequest.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))


def test_parse_plan_json_accepts_fenced_and_plain() -> None:
    plain = parse_plan_json('{"tools":["analyze_logs"],"reason":"errors"}')
    assert plain.tools == (TOOL_ANALYZE_LOGS,)
    fenced = parse_plan_json('```json\n{"tools":["finish"],"reason":"done"}\n```')
    assert fenced.tools == (TOOL_FINISH,)


def test_deterministic_planner_and_loop() -> None:
    request = _load_db_incident()
    first = DeterministicPlanner().decide(
        request,
        PlannerContext(observation=observe_incident(request), round_index=1),
    )
    assert first.tools == (TOOL_ANALYZE_LOGS,)

    report = run_agentic(request, planner="deterministic")
    tools = [step.tool for step in report.agentic_steps if step.phase == "act"]
    assert tools[0] == TOOL_ANALYZE_LOGS
    assert TOOL_ANALYZE_SEVERITY in tools
    assert TOOL_RECOMMEND_RUNBOOK in tools
    assert report.severity is not None
    assert report.runbook is not None
    assert report.log_analysis is not None
    assert not report.partial
    assert report.agentic_mode == "deterministic"


def test_openai_compatible_planner_parses_json_object() -> None:
    class FakeCompletions:
        def create(self, **_kwargs):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content='{"tools":["analyze_logs"],"reason":"inspect"}'
                        )
                    )
                ]
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    planner = OpenAICompatiblePlanner(
        api_key="test-key",
        model="gpt-4o-mini",
        timeout_s=5.0,
        client=client,
    )
    decision = planner.decide(
        _load_db_incident(),
        PlannerContext(observation="demo", round_index=1),
    )
    assert decision.tools == (TOOL_ANALYZE_LOGS,)


def test_cloudflare_planner_reads_response_field() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"result": {"response": '{"tools":["finish"],"reason":"enough"}'}},
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        planner = CloudflareWorkersAIPlanner(
            account_id="acct",
            api_token="token",
            model="@cf/meta/llama-3.1-8b-instruct",
            timeout_s=5.0,
            transport=client,
        )
        decision = planner.decide(
            _load_db_incident(),
            PlannerContext(observation="demo", round_index=1),
        )
    assert decision.tools == (TOOL_FINISH,)


def test_http_planner_accepts_direct_plan_object() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"tools": ["analyze_severity"], "reason": "impact"},
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        planner = HttpJsonPlanner(
            url="https://example.test/plan",
            transport=client,
        )
        decision = planner.decide(
            _load_db_incident(),
            PlannerContext(observation="demo", round_index=2),
        )
    assert decision.tools == (TOOL_ANALYZE_SEVERITY,)


def test_build_planner_defaults_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_CONNECTOR_PLANNER", raising=False)
    assert build_planner().name == "deterministic"


def test_info_only_incident_still_finishes() -> None:
    request = IncidentRequest(
        incident_id="inc-info",
        logs=[
            LogEntry(
                timestamp="2026-03-15T14:00:00Z",
                service="api",
                level=LogLevel.INFO,
                message="ok",
            )
        ],
    )
    report = run_agentic(request, planner=DeterministicPlanner())
    assert report.severity is not None
    assert any(step.tool == TOOL_FINISH for step in report.agentic_steps)
