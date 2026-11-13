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
from agent_connector.agentic.schema import PlanDecision, parse_plan_json
from agent_connector.agentic.tools import (
    TOOL_ANALYZE_LOGS,
    TOOL_ANALYZE_SEVERITY,
    TOOL_FINISH,
    TOOL_RECOMMEND_RUNBOOK,
)
from agent_connector.domain.models import AgentStatus, IncidentRequest, LogEntry, LogLevel


FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "scenarios"
    / "fixtures"
    / "inc-db-001.json"
)


def _load_db_incident() -> IncidentRequest:
    return IncidentRequest.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))


def test_parse_plan_json_accepts_nested_object() -> None:
    plain = parse_plan_json('{"tools":["analyze_logs"],"reason":"errors"}')
    assert plain.tools == (TOOL_ANALYZE_LOGS,)
    assert not plain.degraded
    nested = parse_plan_json(
        'Here:\n{"tools":["analyze_logs"],"reason":"see {not} finish yet"}\n'
    )
    assert nested.tools == (TOOL_ANALYZE_LOGS,)


def test_parse_plan_json_marks_invalid_and_unknown_tools() -> None:
    bad = parse_plan_json("before we finish, maybe analyze_logs")
    assert bad.degraded
    assert bad.tools == (TOOL_FINISH,)
    assert "valid JSON" in bad.error

    unknown = parse_plan_json('{"tools":["teleport"],"reason":"nope"}')
    assert unknown.degraded
    assert unknown.tools == (TOOL_FINISH,)
    assert "teleport" in unknown.error

    mixed = parse_plan_json(
        '{"tools":["analyze_logs","teleport"],"reason":"mixed"}'
    )
    assert mixed.degraded
    assert mixed.tools == (TOOL_ANALYZE_LOGS,)
    assert "teleport" in mixed.error


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
    assert not report.planner_degraded
    assert report.agentic_mode == "deterministic"


def test_openai_fallback_marks_degraded_mode() -> None:
    class FakeCompletions:
        def create(self, **_kwargs):
            raise TimeoutError("upstream timeout")

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    planner = OpenAICompatiblePlanner(
        api_key="test-key",
        model="gpt-4o-mini",
        timeout_s=5.0,
        client=client,
    )
    report = run_agentic(_load_db_incident(), planner=planner)
    assert report.planner_degraded
    assert report.agentic_mode == "openai+fallback"
    assert report.partial
    assert any(step.status == AgentStatus.PARTIAL for step in report.agentic_steps)


def test_repeated_tools_force_partial_finish() -> None:
    class StickyPlanner:
        name = "sticky"

        def decide(self, request, context):
            return PlanDecision(tools=(TOOL_ANALYZE_LOGS,), reason="again")

    report = run_agentic(_load_db_incident(), planner=StickyPlanner(), max_rounds=3)
    assert report.planner_degraded
    assert report.partial
    assert any("already called" in step.detail for step in report.agentic_steps)


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
    assert not decision.degraded



def test_cloudflare_planner_reads_object_response_and_choices() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": {
                    "response": {
                        "tools": ["analyze_logs"],
                        "reason": "inspect logs",
                    },
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": (
                                    '{"tools":["analyze_logs"],'
                                    '"reason":"inspect logs"}'
                                ),
                            }
                        }
                    ],
                },
            },
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
    assert decision.tools == ("analyze_logs",)
    assert not decision.degraded


def test_http_planner_rejects_non_object_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["analyze_logs"])

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        planner = HttpJsonPlanner(url="https://example.test/plan", transport=client)
        decision = planner.decide(
            _load_db_incident(),
            PlannerContext(observation="demo", round_index=2),
        )
    assert decision.degraded
    assert decision.tools == (TOOL_FINISH,)


def test_build_planner_defaults_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_CONNECTOR_PLANNER", raising=False)
    assert build_planner().name == "deterministic"


def test_build_planner_rejects_live_alias() -> None:
    with pytest.raises(Exception, match="unknown planner"):
        build_planner("live")


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
