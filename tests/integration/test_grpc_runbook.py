"""Real-channel integration tests for the Runbook gRPC service."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import grpc
import pytest

from agent_connector.agents.runbook import recommend_actions
from agent_connector.domain.models import IncidentRequest, RunbookResponse
from agent_connector.generated import incident_pb2 as pb
from agent_connector.generated import incident_pb2_grpc as pb_grpc
from agent_connector.grpc_services.lifecycle import start_server
from agent_connector.grpc_services.runbook import RunbookGrpcService
from agent_connector.protocol.protobuf import (
    incident_request_to_proto,
    runbook_response_from_proto,
)


FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "scenarios"
    / "fixtures"
    / "inc-db-001.json"
)


def _load_request() -> IncidentRequest:
    return IncidentRequest.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))


async def _start_runbook(analyzer=recommend_actions):
    service = RunbookGrpcService(analyzer)
    return await start_server(
        lambda server: pb_grpc.add_RunbookServiceServicer_to_server(service, server),
        port=0,
    )


def test_recommend_actions_returns_expected_runbook() -> None:
    async def exercise() -> None:
        incident = _load_request()
        running = await _start_runbook()
        try:
            async with grpc.aio.insecure_channel(running.target) as channel:
                stub = pb_grpc.RunbookServiceStub(channel)
                response = await stub.RecommendActions(
                    incident_request_to_proto(incident),
                    timeout=2.0,
                )

            converted = runbook_response_from_proto(response)
            expected = recommend_actions(incident)
            assert converted.status == expected.status
            assert [item.runbook_id for item in converted.recommendations] == [
                item.runbook_id for item in expected.recommendations
            ]
            assert converted.recommendations[0].steps == expected.recommendations[0].steps
        finally:
            await running.stop(0)

    asyncio.run(exercise())


def test_invalid_request_uses_native_grpc_status() -> None:
    async def exercise() -> None:
        running = await _start_runbook()
        try:
            async with grpc.aio.insecure_channel(running.target) as channel:
                stub = pb_grpc.RunbookServiceStub(channel)
                with pytest.raises(grpc.aio.AioRpcError) as captured:
                    await stub.RecommendActions(
                        pb.IncidentRequest(incident_id="inc-empty"),
                        timeout=2.0,
                    )
            assert captured.value.code() == grpc.StatusCode.INVALID_ARGUMENT
            assert captured.value.details() == "logs must not be empty"
        finally:
            await running.stop(0)

    asyncio.run(exercise())


def test_unexpected_failure_is_sanitized() -> None:
    def fail(_request: IncidentRequest) -> RunbookResponse:
        raise RuntimeError("private failure detail")

    async def exercise() -> None:
        running = await _start_runbook(fail)
        try:
            async with grpc.aio.insecure_channel(running.target) as channel:
                stub = pb_grpc.RunbookServiceStub(channel)
                with pytest.raises(grpc.aio.AioRpcError) as captured:
                    await stub.RecommendActions(
                        incident_request_to_proto(_load_request()),
                        timeout=2.0,
                    )
            assert captured.value.code() == grpc.StatusCode.INTERNAL
            assert captured.value.details() == "internal agent error"
            assert "private failure detail" not in captured.value.details()
        finally:
            await running.stop(0)

    asyncio.run(exercise())
