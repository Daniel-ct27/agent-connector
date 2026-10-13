"""Real-channel integration tests for unary Log Analysis gRPC."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import grpc
import pytest

from agent_connector.agents.log_analysis import analyze_logs
from agent_connector.domain.models import (
    EvidenceItem,
    IncidentRequest,
    LogAnalysisResult,
    LogEntry,
    LogLevel,
)
from agent_connector.generated import incident_pb2 as pb
from agent_connector.generated import incident_pb2_grpc as pb_grpc
from agent_connector.grpc_services.lifecycle import start_server
from agent_connector.grpc_services.log_analysis import LogAnalysisGrpcService
from agent_connector.protocol.protobuf import (
    incident_request_to_proto,
    log_analysis_result_from_proto,
)


FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "scenarios"
    / "fixtures"
    / "inc-db-001.json"
)


def _load_request() -> IncidentRequest:
    return IncidentRequest.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))


async def _start_log_analysis(analyzer=analyze_logs):
    service = LogAnalysisGrpcService(analyzer)
    return await start_server(
        lambda server: pb_grpc.add_LogAnalysisServiceServicer_to_server(
            service,
            server,
        ),
        port=0,
    )


def test_analyze_logs_matches_direct_result() -> None:
    async def exercise() -> None:
        incident = _load_request()
        running = await _start_log_analysis()
        try:
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


def test_invalid_request_uses_native_grpc_status() -> None:
    async def exercise() -> None:
        running = await _start_log_analysis()
        try:
            async with grpc.aio.insecure_channel(running.target) as channel:
                stub = pb_grpc.LogAnalysisServiceStub(channel)
                with pytest.raises(grpc.aio.AioRpcError) as captured:
                    await stub.AnalyzeLogs(
                        pb.IncidentRequest(incident_id="inc-empty"),
                        timeout=2.0,
                    )
            assert captured.value.code() == grpc.StatusCode.INVALID_ARGUMENT
            assert captured.value.details() == "logs must not be empty"
        finally:
            await running.stop(0)

    asyncio.run(exercise())


def test_unexpected_failure_is_sanitized() -> None:
    def fail(_request: IncidentRequest) -> LogAnalysisResult:
        raise RuntimeError("private failure detail")

    async def exercise() -> None:
        running = await _start_log_analysis(fail)
        try:
            async with grpc.aio.insecure_channel(running.target) as channel:
                stub = pb_grpc.LogAnalysisServiceStub(channel)
                with pytest.raises(grpc.aio.AioRpcError) as captured:
                    await stub.AnalyzeLogs(
                        incident_request_to_proto(_load_request()),
                        timeout=2.0,
                    )
            assert captured.value.code() == grpc.StatusCode.INTERNAL
            assert captured.value.details() == "internal agent error"
            assert "private failure detail" not in captured.value.details()
        finally:
            await running.stop(0)

    asyncio.run(exercise())


def test_response_conversion_failure_is_sanitized() -> None:
    def invalid_result(_request: IncidentRequest) -> LogAnalysisResult:
        return LogAnalysisResult(
            evidence=[
                EvidenceItem(
                    service="api",
                    summary="invalid count",
                    count=2**40,
                )
            ]
        )

    async def exercise() -> None:
        running = await _start_log_analysis(invalid_result)
        try:
            async with grpc.aio.insecure_channel(running.target) as channel:
                stub = pb_grpc.LogAnalysisServiceStub(channel)
                with pytest.raises(grpc.aio.AioRpcError) as captured:
                    await stub.AnalyzeLogs(
                        incident_request_to_proto(_load_request()),
                        timeout=2.0,
                    )
            assert captured.value.code() == grpc.StatusCode.INTERNAL
            assert captured.value.details() == "internal agent error"
        finally:
            await running.stop(0)

    asyncio.run(exercise())


def test_maximum_log_count_completes_successfully() -> None:
    async def exercise() -> None:
        log = LogEntry(
            timestamp="2026-03-15T14:00:00Z",
            service="api",
            level=LogLevel.ERROR,
            message="upstream timeout",
        )
        incident = IncidentRequest(
            incident_id="inc-maximum",
            scenario="scale_test",
            logs=[log] * 5_000,
        )
        running = await _start_log_analysis()
        try:
            async with grpc.aio.insecure_channel(running.target) as channel:
                stub = pb_grpc.LogAnalysisServiceStub(channel)
                response = await stub.AnalyzeLogs(
                    incident_request_to_proto(incident),
                    timeout=10.0,
                )
            assert log_analysis_result_from_proto(response) == analyze_logs(incident)
        finally:
            await running.stop(0)

    asyncio.run(exercise())


def test_streaming_is_explicitly_unimplemented() -> None:
    async def exercise() -> None:
        running = await _start_log_analysis()
        try:
            async with grpc.aio.insecure_channel(running.target) as channel:
                stub = pb_grpc.LogAnalysisServiceStub(channel)
                stream = stub.AnalyzeLogsStream(
                    incident_request_to_proto(_load_request()),
                    timeout=2.0,
                )
                with pytest.raises(grpc.aio.AioRpcError) as captured:
                    await stream.read()
            assert captured.value.code() == grpc.StatusCode.UNIMPLEMENTED
            assert captured.value.details() == "streaming log analysis is not available"
        finally:
            await running.stop(0)

    asyncio.run(exercise())
