"""Real-channel integration tests for the Severity gRPC service."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import socket
import threading

import grpc
import pytest

from agent_connector.agents.severity import analyze_severity
from agent_connector.domain.models import IncidentRequest, SeverityResponse
from agent_connector.generated import incident_pb2 as pb
from agent_connector.generated import incident_pb2_grpc as pb_grpc
from agent_connector.config import MAX_GRPC_REQUEST_BYTES
from agent_connector.grpc_services.lifecycle import ServerBindError, start_server
from agent_connector.grpc_services.severity import SeverityGrpcService
from agent_connector.protocol.protobuf import (
    incident_request_to_proto,
    severity_response_from_proto,
)


FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "scenarios"
    / "fixtures"
    / "inc-db-001.json"
)


def _load_request() -> IncidentRequest:
    return IncidentRequest.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))


async def _start_severity(
    analyzer=analyze_severity,
):
    service = SeverityGrpcService(analyzer)
    return await start_server(
        lambda server: pb_grpc.add_SeverityServiceServicer_to_server(service, server),
        port=0,
    )


def test_analyze_severity_matches_direct_result() -> None:
    async def exercise() -> None:
        incident = _load_request()
        running = await _start_severity()
        try:
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


def test_invalid_request_uses_native_grpc_status() -> None:
    async def exercise() -> None:
        running = await _start_severity()
        try:
            async with grpc.aio.insecure_channel(running.target) as channel:
                stub = pb_grpc.SeverityServiceStub(channel)
                with pytest.raises(grpc.aio.AioRpcError) as captured:
                    await stub.AnalyzeSeverity(
                        pb.IncidentRequest(incident_id="inc-empty"),
                        timeout=2.0,
                    )
            assert captured.value.code() == grpc.StatusCode.INVALID_ARGUMENT
            assert captured.value.details() == "logs must not be empty"
        finally:
            await running.stop(0)

    asyncio.run(exercise())


def test_invalid_enum_uses_invalid_argument_status() -> None:
    async def exercise() -> None:
        running = await _start_severity()
        try:
            request = incident_request_to_proto(_load_request())
            request.logs[0].level = 999
            async with grpc.aio.insecure_channel(running.target) as channel:
                stub = pb_grpc.SeverityServiceStub(channel)
                with pytest.raises(grpc.aio.AioRpcError) as captured:
                    await stub.AnalyzeSeverity(request, timeout=2.0)
            assert captured.value.code() == grpc.StatusCode.INVALID_ARGUMENT
            assert captured.value.details() == "request contains an invalid enum value"
        finally:
            await running.stop(0)

    asyncio.run(exercise())


def test_oversized_request_is_rejected_before_analysis() -> None:
    called = False

    def record_call(request: IncidentRequest) -> SeverityResponse:
        nonlocal called
        called = True
        return analyze_severity(request)

    async def exercise() -> None:
        running = await _start_severity(record_call)
        try:
            request = pb.IncidentRequest(
                incident_id="inc-oversized",
                logs=[
                    pb.LogEntry(
                        timestamp="2026-03-15T14:00:00Z",
                        service="api",
                        level=pb.ERROR,
                        message="x" * MAX_GRPC_REQUEST_BYTES,
                    )
                ],
            )
            assert MAX_GRPC_REQUEST_BYTES <= request.ByteSize() < 4 * 1024 * 1024

            async with grpc.aio.insecure_channel(running.target) as channel:
                stub = pb_grpc.SeverityServiceStub(channel)
                with pytest.raises(grpc.aio.AioRpcError) as captured:
                    await stub.AnalyzeSeverity(request, timeout=2.0)
            assert captured.value.code() == grpc.StatusCode.INVALID_ARGUMENT
            assert "request must be smaller" in captured.value.details()
            assert not called
        finally:
            await running.stop(0)

    asyncio.run(exercise())


def test_unexpected_failure_is_sanitized() -> None:
    def fail(_request: IncidentRequest):
        raise RuntimeError("private failure detail")

    async def exercise() -> None:
        running = await _start_severity(fail)
        try:
            async with grpc.aio.insecure_channel(running.target) as channel:
                stub = pb_grpc.SeverityServiceStub(channel)
                with pytest.raises(grpc.aio.AioRpcError) as captured:
                    await stub.AnalyzeSeverity(
                        incident_request_to_proto(_load_request()),
                        timeout=2.0,
                    )
            assert captured.value.code() == grpc.StatusCode.INTERNAL
            assert captured.value.details() == "internal agent error"
            assert "private failure detail" not in captured.value.details()
        finally:
            await running.stop(0)

    asyncio.run(exercise())


def test_analysis_runs_outside_event_loop_thread() -> None:
    event_loop_thread = threading.get_ident()
    analyzer_thread: int | None = None

    def record_thread(request: IncidentRequest) -> SeverityResponse:
        nonlocal analyzer_thread
        analyzer_thread = threading.get_ident()
        return analyze_severity(request)

    async def exercise() -> None:
        running = await _start_severity(record_thread)
        try:
            async with grpc.aio.insecure_channel(running.target) as channel:
                stub = pb_grpc.SeverityServiceStub(channel)
                await stub.AnalyzeSeverity(
                    incident_request_to_proto(_load_request()),
                    timeout=2.0,
                )
        finally:
            await running.stop(0)

    asyncio.run(exercise())
    assert analyzer_thread is not None
    assert analyzer_thread != event_loop_thread


def test_bind_failure_releases_server_resources() -> None:
    async def exercise() -> None:
        with socket.socket() as blocker:
            blocker.bind(("127.0.0.1", 0))
            blocker.listen()
            port = blocker.getsockname()[1]

            with pytest.raises(ServerBindError):
                await start_server(lambda _server: None, port=port)

        running = await start_server(lambda _server: None, port=port)
        await running.stop(0)

    asyncio.run(exercise())
