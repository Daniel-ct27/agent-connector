"""Integration tests for concurrent unary gRPC and HTTP orchestration."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import socket
import time

import pytest
import uvicorn

from agent_connector.agents.log_analysis import analyze_logs, analyze_logs_stream
from agent_connector.agents.runbook import recommend_actions
from agent_connector.agents.severity import analyze_severity
from agent_connector.analyzers import DeterministicAnalyzer
from agent_connector.domain.models import (
    AgentStatus,
    IncidentRequest,
    LogAnalysisResult,
    SeverityResponse,
)
from agent_connector.generated import incident_pb2_grpc as pb_grpc
from agent_connector.grpc_services.lifecycle import RunningServer, start_server
from agent_connector.grpc_services.log_analysis import LogAnalysisGrpcService
from agent_connector.grpc_services.runbook import RunbookGrpcService
from agent_connector.grpc_services.severity import SeverityGrpcService
from agent_connector.http_services.log_analysis import create_log_analysis_app
from agent_connector.http_services.runbook import create_runbook_app
from agent_connector.http_services.severity import create_severity_app
from agent_connector.orchestrator import (
    AgentEndpoints,
    HttpAgentEndpoints,
    orchestrate_unary,
)


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


def _jsonl_dir() -> Path:
    path = Path(__file__).resolve().parents[2] / ".pytest_tmp" / "orchestrator_unary"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _start_grpc_agents(
    *,
    severity=analyze_severity,
    runbook=recommend_actions,
    logs=None,
) -> tuple[RunningServer, RunningServer, RunningServer, AgentEndpoints]:
    analyzer = DeterministicAnalyzer()

    def default_logs(request: IncidentRequest) -> LogAnalysisResult:
        return analyze_logs(request, analyzer=analyzer)

    log_fn = logs or default_logs
    severity_svc = SeverityGrpcService(severity)
    runbook_svc = RunbookGrpcService(runbook)
    log_svc = LogAnalysisGrpcService(log_fn, analyze_logs_stream)

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


async def _stop_grpc(*servers: RunningServer) -> None:
    for server in servers:
        await server.stop(0)


class _HttpServer:
    def __init__(self, server: uvicorn.Server, task: asyncio.Task, base_url: str) -> None:
        self.server = server
        self.task = task
        self.base_url = base_url

    async def stop(self) -> None:
        self.server.should_exit = True
        await self.task


async def _start_http_app(app, *, host: str = "127.0.0.1") -> _HttpServer:
    port = _free_port()
    config = uvicorn.Config(app, host=host, port=port, log_level="error")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    for _ in range(200):
        if server.started:
            break
        await asyncio.sleep(0.01)
    else:
        server.should_exit = True
        await task
        raise RuntimeError("HTTP server failed to start")
    return _HttpServer(server, task, f"http://{host}:{port}")


async def _start_http_agents(
    *,
    severity=analyze_severity,
    runbook=recommend_actions,
    logs=None,
) -> tuple[_HttpServer, _HttpServer, _HttpServer, HttpAgentEndpoints]:
    analyzer = DeterministicAnalyzer()

    def default_logs(request: IncidentRequest) -> LogAnalysisResult:
        return analyze_logs(request, analyzer=analyzer)

    log_fn = logs or default_logs
    severity_s = await _start_http_app(create_severity_app(severity))
    runbook_s = await _start_http_app(create_runbook_app(runbook))
    log_s = await _start_http_app(create_log_analysis_app(log_fn))
    endpoints = HttpAgentEndpoints(
        severity=severity_s.base_url,
        runbook=runbook_s.base_url,
        log_analysis=log_s.base_url,
    )
    return severity_s, runbook_s, log_s, endpoints


async def _stop_http(*servers: _HttpServer) -> None:
    for server in servers:
        await server.stop()


def _compare_successful_reports(grpc_report, http_report, incident: IncidentRequest) -> None:
    assert not grpc_report.partial
    assert not http_report.partial
    assert grpc_report.severity == http_report.severity == analyze_severity(incident)

    assert grpc_report.runbook is not None
    assert http_report.runbook is not None
    direct_runbook = recommend_actions(incident)
    for report in (grpc_report, http_report):
        assert report.runbook.status == direct_runbook.status
        assert len(report.runbook.recommendations) == len(
            direct_runbook.recommendations
        )
        for got, expected in zip(
            report.runbook.recommendations,
            direct_runbook.recommendations,
            strict=True,
        ):
            assert got.runbook_id == expected.runbook_id
            assert got.title == expected.title
            assert got.matched_terms == expected.matched_terms
            assert got.steps == expected.steps
            assert got.confidence == pytest.approx(
                expected.confidence,
                rel=1e-5,
                abs=1e-5,
            )

    expected_logs = analyze_logs(incident, analyzer=DeterministicAnalyzer())
    assert grpc_report.log_analysis == http_report.log_analysis == expected_logs


def test_unary_grpc_and_http_match_for_fixture() -> None:
    async def exercise() -> None:
        incident = _load_request()
        g_sev, g_run, g_log, grpc_endpoints = await _start_grpc_agents()
        h_sev, h_run, h_log, http_endpoints = await _start_http_agents()
        try:
            grpc_report = await orchestrate_unary(
                incident,
                transport="grpc",
                grpc_endpoints=grpc_endpoints,
                jsonl_path=_jsonl_dir() / "equiv-grpc.jsonl",
            )
            http_report = await orchestrate_unary(
                incident,
                transport="http",
                http_endpoints=http_endpoints,
                jsonl_path=_jsonl_dir() / "equiv-http.jsonl",
            )
        finally:
            await _stop_grpc(g_sev, g_run, g_log)
            await _stop_http(h_sev, h_run, h_log)

        _compare_successful_reports(grpc_report, http_report, incident)

    asyncio.run(exercise())


def test_http_unavailable_agent_keeps_siblings() -> None:
    async def exercise() -> None:
        incident = _load_request()
        h_sev, h_run, h_log, endpoints = await _start_http_agents()
        # Point Log Analysis at a free port with no listener so httpx
        # surfaces ConnectError -> UNAVAILABLE (not a shutdown race/timeout).
        endpoints = HttpAgentEndpoints(
            severity=endpoints.severity,
            runbook=endpoints.runbook,
            log_analysis=f"http://127.0.0.1:{_free_port()}",
        )
        try:
            report = await orchestrate_unary(
                incident,
                transport="http",
                http_endpoints=endpoints,
                jsonl_path=_jsonl_dir() / "http-unavailable.jsonl",
            )
        finally:
            await _stop_http(h_sev, h_run, h_log)

        assert report.partial
        assert report.severity is not None
        assert report.runbook is not None
        assert report.log_analysis is None
        outcomes = {item.name: item.status for item in report.agent_outcomes}
        assert outcomes["severity"] == AgentStatus.OK
        assert outcomes["runbook"] == AgentStatus.OK
        assert outcomes["log_analysis"] == AgentStatus.UNAVAILABLE

    asyncio.run(exercise())


def test_http_unary_timeout_does_not_cancel_siblings() -> None:
    def slow_severity(request: IncidentRequest) -> SeverityResponse:
        time.sleep(0.35)
        return analyze_severity(request)

    async def exercise() -> None:
        incident = _load_request()
        h_sev, h_run, h_log, endpoints = await _start_http_agents(
            severity=slow_severity,
        )
        try:
            report = await orchestrate_unary(
                incident,
                transport="http",
                http_endpoints=endpoints,
                unary_deadline_s=0.05,
                jsonl_path=_jsonl_dir() / "http-timeout.jsonl",
            )
        finally:
            await _stop_http(h_sev, h_run, h_log)

        assert report.partial
        assert report.severity is None
        assert report.runbook is not None
        assert report.log_analysis is not None
        outcomes = {item.name: item.status for item in report.agent_outcomes}
        assert outcomes["severity"] == AgentStatus.TIMEOUT
        assert outcomes["runbook"] == AgentStatus.OK
        assert outcomes["log_analysis"] == AgentStatus.OK

    asyncio.run(exercise())


def test_invalid_request_maps_to_invalid_argument_on_both() -> None:
    async def exercise() -> None:
        invalid = IncidentRequest(incident_id="inc-empty", scenario="", logs=[])
        g_sev, g_run, g_log, grpc_endpoints = await _start_grpc_agents()
        h_sev, h_run, h_log, http_endpoints = await _start_http_agents()
        try:
            grpc_report = await orchestrate_unary(
                invalid,
                transport="grpc",
                grpc_endpoints=grpc_endpoints,
                jsonl_path=_jsonl_dir() / "invalid-grpc.jsonl",
            )
            http_report = await orchestrate_unary(
                invalid,
                transport="http",
                http_endpoints=http_endpoints,
                jsonl_path=_jsonl_dir() / "invalid-http.jsonl",
            )
        finally:
            await _stop_grpc(g_sev, g_run, g_log)
            await _stop_http(h_sev, h_run, h_log)

        for report in (grpc_report, http_report):
            assert report.partial
            assert report.severity is None
            assert report.runbook is None
            assert report.log_analysis is None
            outcomes = {item.name: item.status for item in report.agent_outcomes}
            assert outcomes == {
                "severity": AgentStatus.INVALID_ARGUMENT,
                "runbook": AgentStatus.INVALID_ARGUMENT,
                "log_analysis": AgentStatus.INVALID_ARGUMENT,
            }

    asyncio.run(exercise())
