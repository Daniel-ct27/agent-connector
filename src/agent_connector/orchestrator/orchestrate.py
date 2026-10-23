"""Concurrent mixed gRPC orchestration with deadlines and partial reports."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
import logging
from pathlib import Path
import time
import uuid

import grpc

from agent_connector.config import (
    DEFAULT_GRPC_HOST,
    DEFAULT_ORCHESTRATOR_JSONL_PATH,
    LOG_ANALYSIS_GRPC_PORT,
    RUNBOOK_GRPC_PORT,
    SEVERITY_GRPC_PORT,
    STREAM_DEADLINE_SECONDS,
    UNARY_DEADLINE_SECONDS,
)
from agent_connector.domain.models import (
    AgentOutcome,
    AgentStatus,
    IncidentReport,
    IncidentRequest,
    LogAnalysisEvent,
    LogAnalysisResult,
    RunbookResponse,
    SeverityResponse,
)
from agent_connector.generated import incident_pb2_grpc as pb_grpc
from agent_connector.orchestrator.jsonl import JsonlLogger
from agent_connector.protocol.protobuf import (
    incident_request_to_proto,
    log_analysis_event_from_proto,
    runbook_response_from_proto,
    severity_response_from_proto,
)


AGENT_SEVERITY = "severity"
AGENT_RUNBOOK = "runbook"
AGENT_LOG_ANALYSIS = "log_analysis"

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentEndpoints:
    """gRPC targets for the three independently running agent processes."""

    severity: str = f"{DEFAULT_GRPC_HOST}:{SEVERITY_GRPC_PORT}"
    runbook: str = f"{DEFAULT_GRPC_HOST}:{RUNBOOK_GRPC_PORT}"
    log_analysis: str = f"{DEFAULT_GRPC_HOST}:{LOG_ANALYSIS_GRPC_PORT}"


@dataclass
class _UnaryCallResult:
    response: SeverityResponse | RunbookResponse | None
    outcome: AgentOutcome


@dataclass
class _StreamCallResult:
    events: list[LogAnalysisEvent]
    result: LogAnalysisResult | None
    outcome: AgentOutcome


def _map_rpc_error(error: grpc.aio.AioRpcError) -> tuple[AgentStatus, str]:
    code = error.code()
    details = error.details() or code.name
    if code == grpc.StatusCode.DEADLINE_EXCEEDED:
        return AgentStatus.TIMEOUT, details
    if code == grpc.StatusCode.UNAVAILABLE:
        return AgentStatus.UNAVAILABLE, details
    if code == grpc.StatusCode.INVALID_ARGUMENT:
        return AgentStatus.INVALID_ARGUMENT, details
    if code == grpc.StatusCode.CANCELLED:
        return AgentStatus.FAILED, details or "call cancelled"
    return AgentStatus.FAILED, details


async def _call_severity(
    channel: grpc.aio.Channel,
    request: IncidentRequest,
    *,
    deadline_s: float,
    run_id: str,
    logger: JsonlLogger,
) -> _UnaryCallResult:
    stub = pb_grpc.SeverityServiceStub(channel)
    logger.emit(
        "call_started",
        run_id=run_id,
        incident_id=request.incident_id,
        agent=AGENT_SEVERITY,
        pattern="unary",
        deadline_s=deadline_s,
    )
    started = time.perf_counter()
    try:
        response = await stub.AnalyzeSeverity(
            incident_request_to_proto(request),
            timeout=deadline_s,
        )
        domain = severity_response_from_proto(response)
        latency_ms = (time.perf_counter() - started) * 1000.0
        outcome = AgentOutcome(
            name=AGENT_SEVERITY,
            status=domain.status,
            error_message=domain.error_message,
            latency_ms=latency_ms,
        )
        logger.emit(
            "call_finished",
            run_id=run_id,
            incident_id=request.incident_id,
            agent=AGENT_SEVERITY,
            status=outcome.status.value,
            latency_ms=round(latency_ms, 3),
            error_message=outcome.error_message or None,
        )
        return _UnaryCallResult(response=domain, outcome=outcome)
    except grpc.aio.AioRpcError as error:
        latency_ms = (time.perf_counter() - started) * 1000.0
        status, message = _map_rpc_error(error)
        outcome = AgentOutcome(
            name=AGENT_SEVERITY,
            status=status,
            error_message=message,
            latency_ms=latency_ms,
        )
        logger.emit(
            "call_finished",
            run_id=run_id,
            incident_id=request.incident_id,
            agent=AGENT_SEVERITY,
            status=outcome.status.value,
            latency_ms=round(latency_ms, 3),
            error_message=outcome.error_message,
        )
        return _UnaryCallResult(response=None, outcome=outcome)


async def _call_runbook(
    channel: grpc.aio.Channel,
    request: IncidentRequest,
    *,
    deadline_s: float,
    run_id: str,
    logger: JsonlLogger,
) -> _UnaryCallResult:
    stub = pb_grpc.RunbookServiceStub(channel)
    logger.emit(
        "call_started",
        run_id=run_id,
        incident_id=request.incident_id,
        agent=AGENT_RUNBOOK,
        pattern="unary",
        deadline_s=deadline_s,
    )
    started = time.perf_counter()
    try:
        response = await stub.RecommendActions(
            incident_request_to_proto(request),
            timeout=deadline_s,
        )
        domain = runbook_response_from_proto(response)
        latency_ms = (time.perf_counter() - started) * 1000.0
        outcome = AgentOutcome(
            name=AGENT_RUNBOOK,
            status=domain.status,
            error_message=domain.error_message,
            latency_ms=latency_ms,
        )
        logger.emit(
            "call_finished",
            run_id=run_id,
            incident_id=request.incident_id,
            agent=AGENT_RUNBOOK,
            status=outcome.status.value,
            latency_ms=round(latency_ms, 3),
            error_message=outcome.error_message or None,
        )
        return _UnaryCallResult(response=domain, outcome=outcome)
    except grpc.aio.AioRpcError as error:
        latency_ms = (time.perf_counter() - started) * 1000.0
        status, message = _map_rpc_error(error)
        outcome = AgentOutcome(
            name=AGENT_RUNBOOK,
            status=status,
            error_message=message,
            latency_ms=latency_ms,
        )
        logger.emit(
            "call_finished",
            run_id=run_id,
            incident_id=request.incident_id,
            agent=AGENT_RUNBOOK,
            status=outcome.status.value,
            latency_ms=round(latency_ms, 3),
            error_message=outcome.error_message,
        )
        return _UnaryCallResult(response=None, outcome=outcome)


async def _call_log_analysis_stream(
    channel: grpc.aio.Channel,
    request: IncidentRequest,
    *,
    deadline_s: float,
    run_id: str,
    logger: JsonlLogger,
    on_event: Callable[[LogAnalysisEvent], None] | None,
) -> _StreamCallResult:
    stub = pb_grpc.LogAnalysisServiceStub(channel)
    logger.emit(
        "call_started",
        run_id=run_id,
        incident_id=request.incident_id,
        agent=AGENT_LOG_ANALYSIS,
        pattern="stream",
        deadline_s=deadline_s,
    )
    started = time.perf_counter()
    events: list[LogAnalysisEvent] = []
    result: LogAnalysisResult | None = None
    try:
        stream = stub.AnalyzeLogsStream(
            incident_request_to_proto(request),
            timeout=deadline_s,
        )
        async for proto_event in stream:
            event = log_analysis_event_from_proto(proto_event)
            events.append(event)
            logger.emit(
                "stream_event",
                run_id=run_id,
                incident_id=request.incident_id,
                agent=AGENT_LOG_ANALYSIS,
                event_type=event.type.value,
                message=event.message,
            )
            if on_event is not None:
                try:
                    on_event(event)
                except Exception:
                    # Callback failures must not abort the RPC or drop sibling
                    # agent results from the assembled IncidentReport.
                    _LOG.exception(
                        "on_stream_event callback failed; continuing stream"
                    )
            if event.result is not None:
                result = event.result

        latency_ms = (time.perf_counter() - started) * 1000.0
        if result is not None:
            status = result.status
            error_message = result.error_message
        elif events:
            status = AgentStatus.PARTIAL
            error_message = "stream ended without a final result"
        else:
            status = AgentStatus.FAILED
            error_message = "stream produced no events"

        outcome = AgentOutcome(
            name=AGENT_LOG_ANALYSIS,
            status=status,
            error_message=error_message,
            latency_ms=latency_ms,
        )
        logger.emit(
            "call_finished",
            run_id=run_id,
            incident_id=request.incident_id,
            agent=AGENT_LOG_ANALYSIS,
            status=outcome.status.value,
            latency_ms=round(latency_ms, 3),
            error_message=outcome.error_message or None,
        )
        return _StreamCallResult(events=events, result=result, outcome=outcome)
    except grpc.aio.AioRpcError as error:
        latency_ms = (time.perf_counter() - started) * 1000.0
        status, message = _map_rpc_error(error)
        if events and status == AgentStatus.TIMEOUT:
            # Retain partial stream findings on deadline.
            status = AgentStatus.TIMEOUT
        elif events and status == AgentStatus.FAILED:
            status = AgentStatus.PARTIAL
            message = message or "stream terminated early"
        outcome = AgentOutcome(
            name=AGENT_LOG_ANALYSIS,
            status=status,
            error_message=message,
            latency_ms=latency_ms,
        )
        logger.emit(
            "call_finished",
            run_id=run_id,
            incident_id=request.incident_id,
            agent=AGENT_LOG_ANALYSIS,
            status=outcome.status.value,
            latency_ms=round(latency_ms, 3),
            error_message=outcome.error_message,
        )
        return _StreamCallResult(events=events, result=result, outcome=outcome)


def _is_incomplete(status: AgentStatus) -> bool:
    return status != AgentStatus.OK


async def orchestrate(
    request: IncidentRequest,
    *,
    endpoints: AgentEndpoints | None = None,
    unary_deadline_s: float = UNARY_DEADLINE_SECONDS,
    stream_deadline_s: float = STREAM_DEADLINE_SECONDS,
    jsonl_path: Path | str | None = DEFAULT_ORCHESTRATOR_JSONL_PATH,
    on_stream_event: Callable[[LogAnalysisEvent], None] | None = None,
) -> IncidentReport:
    """Run Severity, Runbook, and Log Analysis concurrently over gRPC.

    Returns an ``IncidentReport`` that retains completed responses and any
    stream events already received when individual calls fail or time out.
    """
    targets = endpoints or AgentEndpoints()
    run_id = str(uuid.uuid4())

    with JsonlLogger(jsonl_path) as logger:
        async with (
            grpc.aio.insecure_channel(targets.severity) as severity_channel,
            grpc.aio.insecure_channel(targets.runbook) as runbook_channel,
            grpc.aio.insecure_channel(targets.log_analysis) as log_channel,
        ):
            severity_task = asyncio.create_task(
                _call_severity(
                    severity_channel,
                    request,
                    deadline_s=unary_deadline_s,
                    run_id=run_id,
                    logger=logger,
                )
            )
            runbook_task = asyncio.create_task(
                _call_runbook(
                    runbook_channel,
                    request,
                    deadline_s=unary_deadline_s,
                    run_id=run_id,
                    logger=logger,
                )
            )
            stream_task = asyncio.create_task(
                _call_log_analysis_stream(
                    log_channel,
                    request,
                    deadline_s=stream_deadline_s,
                    run_id=run_id,
                    logger=logger,
                    on_event=on_stream_event,
                )
            )

            try:
                severity_result, runbook_result, stream_result = await asyncio.gather(
                    severity_task,
                    runbook_task,
                    stream_task,
                )
            except asyncio.CancelledError:
                for task in (severity_task, runbook_task, stream_task):
                    task.cancel()
                await asyncio.gather(
                    severity_task,
                    runbook_task,
                    stream_task,
                    return_exceptions=True,
                )
                raise

        outcomes = [
            severity_result.outcome,
            runbook_result.outcome,
            stream_result.outcome,
        ]
        report = IncidentReport(
            incident_id=request.incident_id,
            scenario=request.scenario,
            severity=(
                severity_result.response
                if isinstance(severity_result.response, SeverityResponse)
                else None
            ),
            runbook=(
                runbook_result.response
                if isinstance(runbook_result.response, RunbookResponse)
                else None
            ),
            log_analysis=stream_result.result,
            log_analysis_events=stream_result.events,
            agent_outcomes=outcomes,
            partial=any(_is_incomplete(item.status) for item in outcomes),
        )
        logger.emit(
            "report_complete",
            run_id=run_id,
            incident_id=request.incident_id,
            partial=report.partial,
            outcomes=[
                {"name": item.name, "status": item.status.value} for item in outcomes
            ],
        )
        return report
