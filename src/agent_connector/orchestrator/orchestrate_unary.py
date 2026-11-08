"""Concurrent unary orchestration over gRPC or HTTP/JSON."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
import time
from typing import Literal
import uuid

import grpc
import httpx

from agent_connector.config import (
    DEFAULT_HTTP_HOST,
    DEFAULT_ORCHESTRATOR_JSONL_PATH,
    LOG_ANALYSIS_HTTP_PORT,
    RUNBOOK_HTTP_PORT,
    SEVERITY_HTTP_PORT,
    UNARY_DEADLINE_SECONDS,
)
from agent_connector.domain.models import (
    AgentOutcome,
    AgentStatus,
    IncidentReport,
    IncidentRequest,
    LogAnalysisResult,
    RunbookResponse,
    SeverityResponse,
)
from agent_connector.generated import incident_pb2_grpc as pb_grpc
from agent_connector.orchestrator.jsonl import JsonlLogger
from agent_connector.orchestrator.orchestrate import (
    AGENT_LOG_ANALYSIS,
    AGENT_RUNBOOK,
    AGENT_SEVERITY,
    AgentEndpoints,
)
from agent_connector.protocol.protobuf import (
    incident_request_to_proto,
    log_analysis_result_from_proto,
    runbook_response_from_proto,
    severity_response_from_proto,
)


UnaryTransport = Literal["grpc", "http"]


@dataclass(frozen=True)
class HttpAgentEndpoints:
    """Base URLs for the three independently running HTTP agent processes."""

    severity: str = f"http://{DEFAULT_HTTP_HOST}:{SEVERITY_HTTP_PORT}"
    runbook: str = f"http://{DEFAULT_HTTP_HOST}:{RUNBOOK_HTTP_PORT}"
    log_analysis: str = f"http://{DEFAULT_HTTP_HOST}:{LOG_ANALYSIS_HTTP_PORT}"


@dataclass
class _UnaryCallResult:
    response: SeverityResponse | RunbookResponse | LogAnalysisResult | None
    outcome: AgentOutcome


def _is_incomplete(status: AgentStatus) -> bool:
    return status != AgentStatus.OK


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


def _http_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        return text or f"HTTP {response.status_code}"
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str) and detail:
            return detail
    return f"HTTP {response.status_code}"


def _map_http_transport_error(error: Exception) -> tuple[AgentStatus, str]:
    # ConnectTimeout is a TimeoutException subclass; on some platforms
    # (notably Windows) a closed port surfaces as ConnectTimeout rather
    # than ConnectError. Treat both as UNAVAILABLE so sibling isolation
    # matches the gRPC unavailable-agent path.
    if isinstance(error, (httpx.ConnectError, httpx.ConnectTimeout)):
        return AgentStatus.UNAVAILABLE, str(error) or "connection failed"
    if isinstance(error, httpx.TimeoutException):
        return AgentStatus.TIMEOUT, str(error) or "request timed out"
    return AgentStatus.FAILED, str(error) or "http call failed"


async def _call_grpc_unary(
    *,
    agent: str,
    channel: grpc.aio.Channel,
    request: IncidentRequest,
    deadline_s: float,
    run_id: str,
    logger: JsonlLogger,
) -> _UnaryCallResult:
    logger.emit(
        "call_started",
        run_id=run_id,
        incident_id=request.incident_id,
        agent=agent,
        pattern="unary",
        transport="grpc",
        deadline_s=deadline_s,
    )
    started = time.perf_counter()
    proto_request = incident_request_to_proto(request)
    try:
        if agent == AGENT_SEVERITY:
            response = await pb_grpc.SeverityServiceStub(channel).AnalyzeSeverity(
                proto_request,
                timeout=deadline_s,
            )
            domain: SeverityResponse | RunbookResponse | LogAnalysisResult = (
                severity_response_from_proto(response)
            )
        elif agent == AGENT_RUNBOOK:
            response = await pb_grpc.RunbookServiceStub(channel).RecommendActions(
                proto_request,
                timeout=deadline_s,
            )
            domain = runbook_response_from_proto(response)
        else:
            response = await pb_grpc.LogAnalysisServiceStub(channel).AnalyzeLogs(
                proto_request,
                timeout=deadline_s,
            )
            domain = log_analysis_result_from_proto(response)

        latency_ms = (time.perf_counter() - started) * 1000.0
        outcome = AgentOutcome(
            name=agent,
            status=domain.status,
            error_message=domain.error_message,
            latency_ms=latency_ms,
        )
        logger.emit(
            "call_finished",
            run_id=run_id,
            incident_id=request.incident_id,
            agent=agent,
            status=outcome.status.value,
            latency_ms=round(latency_ms, 3),
            error_message=outcome.error_message or None,
            transport="grpc",
        )
        return _UnaryCallResult(response=domain, outcome=outcome)
    except grpc.aio.AioRpcError as error:
        latency_ms = (time.perf_counter() - started) * 1000.0
        status, message = _map_rpc_error(error)
        outcome = AgentOutcome(
            name=agent,
            status=status,
            error_message=message,
            latency_ms=latency_ms,
        )
        logger.emit(
            "call_finished",
            run_id=run_id,
            incident_id=request.incident_id,
            agent=agent,
            status=outcome.status.value,
            latency_ms=round(latency_ms, 3),
            error_message=outcome.error_message,
            transport="grpc",
        )
        return _UnaryCallResult(response=None, outcome=outcome)


async def _call_http_unary(
    *,
    agent: str,
    client: httpx.AsyncClient,
    url: str,
    request: IncidentRequest,
    deadline_s: float,
    run_id: str,
    logger: JsonlLogger,
) -> _UnaryCallResult:
    logger.emit(
        "call_started",
        run_id=run_id,
        incident_id=request.incident_id,
        agent=agent,
        pattern="unary",
        transport="http",
        deadline_s=deadline_s,
    )
    started = time.perf_counter()
    try:
        response = await client.post(
            url,
            json=request.model_dump(mode="json"),
            timeout=deadline_s,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        if response.status_code == 400:
            outcome = AgentOutcome(
                name=agent,
                status=AgentStatus.INVALID_ARGUMENT,
                error_message=_http_error_detail(response),
                latency_ms=latency_ms,
            )
            logger.emit(
                "call_finished",
                run_id=run_id,
                incident_id=request.incident_id,
                agent=agent,
                status=outcome.status.value,
                latency_ms=round(latency_ms, 3),
                error_message=outcome.error_message,
                transport="http",
            )
            return _UnaryCallResult(response=None, outcome=outcome)
        if response.status_code >= 500:
            outcome = AgentOutcome(
                name=agent,
                status=AgentStatus.FAILED,
                error_message=_http_error_detail(response),
                latency_ms=latency_ms,
            )
            logger.emit(
                "call_finished",
                run_id=run_id,
                incident_id=request.incident_id,
                agent=agent,
                status=outcome.status.value,
                latency_ms=round(latency_ms, 3),
                error_message=outcome.error_message,
                transport="http",
            )
            return _UnaryCallResult(response=None, outcome=outcome)
        if response.status_code != 200:
            outcome = AgentOutcome(
                name=agent,
                status=AgentStatus.FAILED,
                error_message=_http_error_detail(response),
                latency_ms=latency_ms,
            )
            logger.emit(
                "call_finished",
                run_id=run_id,
                incident_id=request.incident_id,
                agent=agent,
                status=outcome.status.value,
                latency_ms=round(latency_ms, 3),
                error_message=outcome.error_message,
                transport="http",
            )
            return _UnaryCallResult(response=None, outcome=outcome)

        payload = response.json()
        if agent == AGENT_SEVERITY:
            domain: SeverityResponse | RunbookResponse | LogAnalysisResult = (
                SeverityResponse.model_validate(payload)
            )
        elif agent == AGENT_RUNBOOK:
            domain = RunbookResponse.model_validate(payload)
        else:
            domain = LogAnalysisResult.model_validate(payload)

        outcome = AgentOutcome(
            name=agent,
            status=domain.status,
            error_message=domain.error_message,
            latency_ms=latency_ms,
        )
        logger.emit(
            "call_finished",
            run_id=run_id,
            incident_id=request.incident_id,
            agent=agent,
            status=outcome.status.value,
            latency_ms=round(latency_ms, 3),
            error_message=outcome.error_message or None,
            transport="http",
        )
        return _UnaryCallResult(response=domain, outcome=outcome)
    except Exception as error:
        latency_ms = (time.perf_counter() - started) * 1000.0
        status, message = _map_http_transport_error(error)
        outcome = AgentOutcome(
            name=agent,
            status=status,
            error_message=message,
            latency_ms=latency_ms,
        )
        logger.emit(
            "call_finished",
            run_id=run_id,
            incident_id=request.incident_id,
            agent=agent,
            status=outcome.status.value,
            latency_ms=round(latency_ms, 3),
            error_message=outcome.error_message,
            transport="http",
        )
        return _UnaryCallResult(response=None, outcome=outcome)


def _assemble_report(
    request: IncidentRequest,
    *,
    severity_result: _UnaryCallResult,
    runbook_result: _UnaryCallResult,
    log_result: _UnaryCallResult,
) -> IncidentReport:
    outcomes = [
        severity_result.outcome,
        runbook_result.outcome,
        log_result.outcome,
    ]
    return IncidentReport(
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
        log_analysis=(
            log_result.response
            if isinstance(log_result.response, LogAnalysisResult)
            else None
        ),
        log_analysis_events=[],
        agent_outcomes=outcomes,
        partial=any(_is_incomplete(item.status) for item in outcomes),
    )


async def _orchestrate_grpc_unary(
    request: IncidentRequest,
    *,
    endpoints: AgentEndpoints,
    unary_deadline_s: float,
    jsonl_path: Path | str | None,
) -> IncidentReport:
    run_id = str(uuid.uuid4())
    with JsonlLogger(jsonl_path) as logger:
        async with (
            grpc.aio.insecure_channel(endpoints.severity) as severity_channel,
            grpc.aio.insecure_channel(endpoints.runbook) as runbook_channel,
            grpc.aio.insecure_channel(endpoints.log_analysis) as log_channel,
        ):
            severity_task = asyncio.create_task(
                _call_grpc_unary(
                    agent=AGENT_SEVERITY,
                    channel=severity_channel,
                    request=request,
                    deadline_s=unary_deadline_s,
                    run_id=run_id,
                    logger=logger,
                )
            )
            runbook_task = asyncio.create_task(
                _call_grpc_unary(
                    agent=AGENT_RUNBOOK,
                    channel=runbook_channel,
                    request=request,
                    deadline_s=unary_deadline_s,
                    run_id=run_id,
                    logger=logger,
                )
            )
            log_task = asyncio.create_task(
                _call_grpc_unary(
                    agent=AGENT_LOG_ANALYSIS,
                    channel=log_channel,
                    request=request,
                    deadline_s=unary_deadline_s,
                    run_id=run_id,
                    logger=logger,
                )
            )
            try:
                severity_result, runbook_result, log_result = await asyncio.gather(
                    severity_task,
                    runbook_task,
                    log_task,
                )
            except asyncio.CancelledError:
                for task in (severity_task, runbook_task, log_task):
                    task.cancel()
                await asyncio.gather(
                    severity_task,
                    runbook_task,
                    log_task,
                    return_exceptions=True,
                )
                raise

        report = _assemble_report(
            request,
            severity_result=severity_result,
            runbook_result=runbook_result,
            log_result=log_result,
        )
        logger.emit(
            "report_complete",
            run_id=run_id,
            incident_id=request.incident_id,
            partial=report.partial,
            outcomes=[
                {"name": item.name, "status": item.status.value}
                for item in report.agent_outcomes
            ],
            transport="grpc",
        )
        return report


async def _orchestrate_http_unary(
    request: IncidentRequest,
    *,
    endpoints: HttpAgentEndpoints,
    unary_deadline_s: float,
    jsonl_path: Path | str | None,
) -> IncidentReport:
    run_id = str(uuid.uuid4())
    with JsonlLogger(jsonl_path) as logger:
        async with httpx.AsyncClient() as client:
            severity_task = asyncio.create_task(
                _call_http_unary(
                    agent=AGENT_SEVERITY,
                    client=client,
                    url=f"{endpoints.severity.rstrip('/')}/v1/severity/analyze",
                    request=request,
                    deadline_s=unary_deadline_s,
                    run_id=run_id,
                    logger=logger,
                )
            )
            runbook_task = asyncio.create_task(
                _call_http_unary(
                    agent=AGENT_RUNBOOK,
                    client=client,
                    url=f"{endpoints.runbook.rstrip('/')}/v1/runbook/recommend",
                    request=request,
                    deadline_s=unary_deadline_s,
                    run_id=run_id,
                    logger=logger,
                )
            )
            log_task = asyncio.create_task(
                _call_http_unary(
                    agent=AGENT_LOG_ANALYSIS,
                    client=client,
                    url=(
                        f"{endpoints.log_analysis.rstrip('/')}"
                        "/v1/log-analysis/analyze"
                    ),
                    request=request,
                    deadline_s=unary_deadline_s,
                    run_id=run_id,
                    logger=logger,
                )
            )
            try:
                severity_result, runbook_result, log_result = await asyncio.gather(
                    severity_task,
                    runbook_task,
                    log_task,
                )
            except asyncio.CancelledError:
                for task in (severity_task, runbook_task, log_task):
                    task.cancel()
                await asyncio.gather(
                    severity_task,
                    runbook_task,
                    log_task,
                    return_exceptions=True,
                )
                raise

        report = _assemble_report(
            request,
            severity_result=severity_result,
            runbook_result=runbook_result,
            log_result=log_result,
        )
        logger.emit(
            "report_complete",
            run_id=run_id,
            incident_id=request.incident_id,
            partial=report.partial,
            outcomes=[
                {"name": item.name, "status": item.status.value}
                for item in report.agent_outcomes
            ],
            transport="http",
        )
        return report


async def orchestrate_unary(
    request: IncidentRequest,
    *,
    transport: UnaryTransport,
    grpc_endpoints: AgentEndpoints | None = None,
    http_endpoints: HttpAgentEndpoints | None = None,
    unary_deadline_s: float = UNARY_DEADLINE_SECONDS,
    jsonl_path: Path | str | None = DEFAULT_ORCHESTRATOR_JSONL_PATH,
) -> IncidentReport:
    """Run all three agents concurrently using unary calls only."""
    if transport == "grpc":
        return await _orchestrate_grpc_unary(
            request,
            endpoints=grpc_endpoints or AgentEndpoints(),
            unary_deadline_s=unary_deadline_s,
            jsonl_path=jsonl_path,
        )
    if transport == "http":
        return await _orchestrate_http_unary(
            request,
            endpoints=http_endpoints or HttpAgentEndpoints(),
            unary_deadline_s=unary_deadline_s,
            jsonl_path=jsonl_path,
        )
    raise ValueError(f"unsupported unary transport: {transport!r}")
