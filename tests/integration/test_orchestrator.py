"""Integration tests for concurrent mixed gRPC orchestration."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
import json
from pathlib import Path
import time

import pytest

from agent_connector.agents.log_analysis import analyze_logs, analyze_logs_stream
from agent_connector.agents.runbook import recommend_actions
from agent_connector.agents.severity import analyze_severity
from agent_connector.domain.models import (
    AgentStatus,
    IncidentRequest,
    LogAnalysisEvent,
    LogAnalysisEventType,
    LogAnalysisResult,
    SeverityResponse,
)
from agent_connector.generated import incident_pb2_grpc as pb_grpc
from agent_connector.grpc_services.lifecycle import RunningServer, start_server
from agent_connector.grpc_services.log_analysis import LogAnalysisGrpcService
from agent_connector.grpc_services.runbook import RunbookGrpcService
from agent_connector.grpc_services.severity import SeverityGrpcService
from agent_connector.orchestrator import AgentEndpoints, orchestrate


FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "scenarios"
    / "fixtures"
    / "inc-db-001.json"
)


def _load_request() -> IncidentRequest:
    return IncidentRequest.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))


async def _start_agents(
    *,
    severity=analyze_severity,
    runbook=recommend_actions,
    logs=analyze_logs,
    stream=analyze_logs_stream,
) -> tuple[RunningServer, RunningServer, RunningServer, AgentEndpoints]:
    severity_svc = SeverityGrpcService(severity)
    runbook_svc = RunbookGrpcService(runbook)
    log_svc = LogAnalysisGrpcService(logs, stream)

    severity_server = await start_server(
        lambda server: pb_grpc.add_SeverityServiceServicer_to_server(
            severity_svc,
            server,
        ),
        port=0,
    )
    runbook_server = await start_server(
        lambda server: pb_grpc.add_RunbookServiceServicer_to_server(
            runbook_svc,
            server,
        ),
        port=0,
    )
    log_server = await start_server(
        lambda server: pb_grpc.add_LogAnalysisServiceServicer_to_server(
            log_svc,
            server,
        ),
        port=0,
    )
    endpoints = AgentEndpoints(
        severity=severity_server.target,
        runbook=runbook_server.target,
        log_analysis=log_server.target,
    )
    return severity_server, runbook_server, log_server, endpoints


async def _stop_all(*servers: RunningServer) -> None:
    for server in servers:
        await server.stop(0)


def _jsonl_dir() -> Path:
    path = Path(__file__).resolve().parents[2] / ".pytest_tmp" / "orchestrator"
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_happy_path_matches_direct_agents() -> None:
    async def exercise() -> None:
        incident = _load_request()
        severity_s, runbook_s, log_s, endpoints = await _start_agents()
        jsonl_path = _jsonl_dir() / "run.jsonl"
        if jsonl_path.exists():
            jsonl_path.unlink()
        try:
            seen: list[LogAnalysisEvent] = []
            report = await orchestrate(
                incident,
                endpoints=endpoints,
                jsonl_path=jsonl_path,
                on_stream_event=seen.append,
            )
        finally:
            await _stop_all(severity_s, runbook_s, log_s)

        assert not report.partial
        assert report.severity == analyze_severity(incident)
        # protobuf float32 can nudge confidence slightly; compare structure.
        direct_runbook = recommend_actions(incident)
        assert report.runbook is not None
        assert report.runbook.status == direct_runbook.status
        assert len(report.runbook.recommendations) == len(direct_runbook.recommendations)
        for got, expected in zip(
            report.runbook.recommendations,
            direct_runbook.recommendations,
            strict=True,
        ):
            assert got.runbook_id == expected.runbook_id
            assert got.title == expected.title
            assert got.matched_terms == expected.matched_terms
            assert got.steps == expected.steps
            assert got.confidence == pytest.approx(expected.confidence, rel=1e-5, abs=1e-5)
        assert report.log_analysis == analyze_logs(incident)
        assert [event.type for event in report.log_analysis_events] == [
            event.type for event in analyze_logs_stream(incident)
        ]
        assert seen == report.log_analysis_events
        assert {item.name: item.status for item in report.agent_outcomes} == {
            "severity": AgentStatus.OK,
            "runbook": AgentStatus.OK,
            "log_analysis": AgentStatus.OK,
        }

        lines = [
            json.loads(line)
            for line in jsonl_path.read_text(encoding="utf-8").splitlines()
            if line
        ]
        events = [row["event"] for row in lines]
        assert events.count("call_started") == 3
        assert events.count("call_finished") == 3
        assert "stream_event" in events
        assert events[-1] == "report_complete"
        assert lines[-1]["partial"] is False

    asyncio.run(exercise())


def test_unavailable_agent_keeps_sibling_results() -> None:
    async def exercise() -> None:
        incident = _load_request()
        severity_s, runbook_s, log_s, endpoints = await _start_agents()
        await log_s.stop(0)
        try:
            report = await orchestrate(
                incident,
                endpoints=endpoints,
                jsonl_path=_jsonl_dir() / "unavailable.jsonl",
            )
        finally:
            await _stop_all(severity_s, runbook_s)

        assert report.partial
        assert report.severity is not None
        assert report.runbook is not None
        assert report.log_analysis is None
        outcomes = {item.name: item.status for item in report.agent_outcomes}
        assert outcomes["severity"] == AgentStatus.OK
        assert outcomes["runbook"] == AgentStatus.OK
        assert outcomes["log_analysis"] == AgentStatus.UNAVAILABLE

    asyncio.run(exercise())


def test_unary_timeout_does_not_cancel_siblings() -> None:
    def slow_severity(request: IncidentRequest) -> SeverityResponse:
        time.sleep(0.35)
        return analyze_severity(request)

    async def exercise() -> None:
        incident = _load_request()
        severity_s, runbook_s, log_s, endpoints = await _start_agents(
            severity=slow_severity,
        )
        try:
            report = await orchestrate(
                incident,
                endpoints=endpoints,
                unary_deadline_s=0.05,
                stream_deadline_s=10.0,
                jsonl_path=_jsonl_dir() / "timeout.jsonl",
            )
        finally:
            await _stop_all(severity_s, runbook_s, log_s)

        assert report.partial
        assert report.severity is None
        assert report.runbook is not None
        assert report.log_analysis is not None
        outcomes = {item.name: item.status for item in report.agent_outcomes}
        assert outcomes["severity"] == AgentStatus.TIMEOUT
        assert outcomes["runbook"] == AgentStatus.OK
        assert outcomes["log_analysis"] == AgentStatus.OK

    asyncio.run(exercise())


def test_stream_timeout_retains_partial_events() -> None:
    def slow_stream(request: IncidentRequest) -> Iterator[LogAnalysisEvent]:
        yield LogAnalysisEvent(
            type=LogAnalysisEventType.STARTED,
            message="started",
        )
        time.sleep(0.4)
        yield LogAnalysisEvent(
            type=LogAnalysisEventType.COMPLETED,
            message="completed",
            result=LogAnalysisResult(status=AgentStatus.OK, summary="late"),
        )

    async def exercise() -> None:
        incident = _load_request()
        severity_s, runbook_s, log_s, endpoints = await _start_agents(
            stream=slow_stream,
        )
        try:
            report = await orchestrate(
                incident,
                endpoints=endpoints,
                unary_deadline_s=2.0,
                stream_deadline_s=0.1,
                jsonl_path=_jsonl_dir() / "stream-timeout.jsonl",
            )
        finally:
            await _stop_all(severity_s, runbook_s, log_s)

        assert report.partial
        assert report.severity is not None
        assert report.runbook is not None
        assert report.log_analysis is None
        assert report.log_analysis_events
        assert report.log_analysis_events[0].type == LogAnalysisEventType.STARTED
        outcomes = {item.name: item.status for item in report.agent_outcomes}
        assert outcomes["log_analysis"] == AgentStatus.TIMEOUT

    asyncio.run(exercise())


def test_invalid_argument_marks_partial() -> None:
    async def exercise() -> None:
        bad = IncidentRequest(incident_id="inc-empty", scenario="x", logs=[])
        severity_s, runbook_s, log_s, endpoints = await _start_agents()
        try:
            report = await orchestrate(
                bad,
                endpoints=endpoints,
                jsonl_path=_jsonl_dir() / "invalid.jsonl",
            )
        finally:
            await _stop_all(severity_s, runbook_s, log_s)

        assert report.partial
        # Unary services abort with INVALID_ARGUMENT; stream emits ERROR event.
        outcomes = {item.name: item.status for item in report.agent_outcomes}
        assert outcomes["severity"] == AgentStatus.INVALID_ARGUMENT
        assert outcomes["runbook"] == AgentStatus.INVALID_ARGUMENT
        assert outcomes["log_analysis"] == AgentStatus.INVALID_ARGUMENT
        assert report.log_analysis is not None
        assert report.log_analysis.status == AgentStatus.INVALID_ARGUMENT

    asyncio.run(exercise())
