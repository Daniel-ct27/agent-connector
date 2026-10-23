"""Integration checks for independently runnable agent server entry points."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import grpc
import pytest

from agent_connector.agents.log_analysis import analyze_logs
from agent_connector.agents.runbook import recommend_actions
from agent_connector.agents.severity import analyze_severity
from agent_connector.config import (
    DEFAULT_GRPC_HOST,
    LOG_ANALYSIS_GRPC_PORT,
    RUNBOOK_GRPC_PORT,
    SEVERITY_GRPC_PORT,
)
from agent_connector.domain.models import IncidentRequest
from agent_connector.generated import incident_pb2_grpc as pb_grpc
from agent_connector.grpc_services.lifecycle import ServerBindError, start_server
from agent_connector.protocol.protobuf import (
    incident_request_to_proto,
    log_analysis_result_from_proto,
    runbook_response_from_proto,
    severity_response_from_proto,
)
from agent_connector.servers import log_analysis as log_analysis_server
from agent_connector.servers import runbook as runbook_server
from agent_connector.servers import severity as severity_server
from agent_connector.servers.runtime import serve_agent

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "scenarios"
    / "fixtures"
    / "inc-db-001.json"
)


def _load_request() -> IncidentRequest:
    return IncidentRequest.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))


def test_locked_ports_use_standard_grpc_demo_range() -> None:
    assert DEFAULT_GRPC_HOST == "127.0.0.1"
    assert SEVERITY_GRPC_PORT == 50051
    assert RUNBOOK_GRPC_PORT == 50052
    assert LOG_ANALYSIS_GRPC_PORT == 50053


def test_severity_process_register_serves_requests() -> None:
    async def exercise() -> None:
        running = await start_server(severity_server.register, port=0)
        try:
            incident = _load_request()
            async with grpc.aio.insecure_channel(running.target) as channel:
                stub = pb_grpc.SeverityServiceStub(channel)
                response = await stub.AnalyzeSeverity(
                    incident_request_to_proto(incident),
                    timeout=2.0,
                )
            assert severity_response_from_proto(response) == analyze_severity(incident)
        finally:
            await running.stop(0)

    asyncio.run(exercise())


def test_runbook_process_register_serves_requests() -> None:
    async def exercise() -> None:
        running = await start_server(runbook_server.register, port=0)
        try:
            incident = _load_request()
            expected = recommend_actions(incident)
            async with grpc.aio.insecure_channel(running.target) as channel:
                stub = pb_grpc.RunbookServiceStub(channel)
                response = await stub.RecommendActions(
                    incident_request_to_proto(incident),
                    timeout=2.0,
                )
            converted = runbook_response_from_proto(response)
            assert converted.status == expected.status
            assert [item.runbook_id for item in converted.recommendations] == [
                item.runbook_id for item in expected.recommendations
            ]
            assert converted.recommendations[0].steps == expected.recommendations[0].steps
        finally:
            await running.stop(0)

    asyncio.run(exercise())


def test_log_analysis_process_register_serves_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # register() reads AGENT_CONNECTOR_ANALYZER; pin deterministic so this
    # process-entry test stays independent of the developer's shell env.
    monkeypatch.setenv("AGENT_CONNECTOR_ANALYZER", "deterministic")
    monkeypatch.delenv("AGENT_CONNECTOR_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    async def exercise() -> None:
        running = await start_server(log_analysis_server.register, port=0)
        try:
            incident = _load_request()
            async with grpc.aio.insecure_channel(running.target) as channel:
                stub = pb_grpc.LogAnalysisServiceStub(channel)
                response = await stub.AnalyzeLogs(
                    incident_request_to_proto(incident),
                    timeout=2.0,
                )
            assert log_analysis_result_from_proto(response) == analyze_logs(incident)
        finally:
            await running.stop(0)

    asyncio.run(exercise())


def test_serve_agent_exits_when_port_unavailable() -> None:
    async def exercise() -> None:
        blocker = await start_server(lambda _server: None, port=0)
        try:
            with pytest.raises(ServerBindError):
                await serve_agent(
                    severity_server.register,
                    service_name="Severity Agent",
                    port=blocker.port,
                )
        finally:
            await blocker.stop(0)

    asyncio.run(exercise())
