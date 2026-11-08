"""Single-trial measurement helpers for Stage 7 benchmarks."""

from __future__ import annotations

from dataclasses import dataclass
import time

from agent_connector.domain.models import AgentStatus, IncidentReport, IncidentRequest
from agent_connector.orchestrator import (
    AgentEndpoints,
    HttpAgentEndpoints,
    orchestrate,
    orchestrate_unary,
)
from agent_connector.protocol.protobuf import (
    incident_request_to_proto,
    log_analysis_result_to_proto,
    runbook_response_to_proto,
    severity_response_to_proto,
)


@dataclass(frozen=True)
class TrialMeasurement:
    """One timed (or warm-up) orchestrator invocation measurement."""

    latency_ms: float
    ttfe_ms: float | None
    request_bytes: int
    response_bytes: int
    partial: bool
    severity_status: str
    runbook_status: str
    log_analysis_status: str
    error: str


def request_bytes_for(transport: str, request: IncidentRequest) -> int:
    """Return the locked request-size definition for ``transport``."""
    if transport == "http":
        return len(request.model_dump_json().encode("utf-8"))
    return incident_request_to_proto(request).ByteSize()


def response_bytes_for(transport: str, report: IncidentReport) -> int:
    """Return the locked response-size definition for ``transport``."""
    if transport == "http":
        total = 0
        if report.severity is not None:
            total += len(report.severity.model_dump_json().encode("utf-8"))
        if report.runbook is not None:
            total += len(report.runbook.model_dump_json().encode("utf-8"))
        if report.log_analysis is not None:
            total += len(report.log_analysis.model_dump_json().encode("utf-8"))
        return total

    total = 0
    if report.severity is not None:
        total += severity_response_to_proto(report.severity).ByteSize()
    if report.runbook is not None:
        total += runbook_response_to_proto(report.runbook).ByteSize()
    if report.log_analysis is not None:
        total += log_analysis_result_to_proto(report.log_analysis).ByteSize()
    return total


def _status_map(report: IncidentReport) -> dict[str, str]:
    return {item.name: item.status.value for item in report.agent_outcomes}


def _first_error(report: IncidentReport) -> str:
    for item in report.agent_outcomes:
        if item.status != AgentStatus.OK and item.error_message:
            return item.error_message
    return ""


async def measure_unary_trial(
    *,
    transport: str,
    request: IncidentRequest,
    grpc_endpoints: AgentEndpoints | None = None,
    http_endpoints: HttpAgentEndpoints | None = None,
    unary_deadline_s: float,
) -> TrialMeasurement:
    """Time one unary orchestrator call for ``grpc`` or ``http``."""
    if transport not in {"grpc", "http"}:
        raise ValueError(f"unsupported unary transport: {transport!r}")

    req_bytes = request_bytes_for(transport, request)
    started = time.perf_counter()
    report = await orchestrate_unary(
        request,
        transport=transport,  # type: ignore[arg-type]
        grpc_endpoints=grpc_endpoints,
        http_endpoints=http_endpoints,
        unary_deadline_s=unary_deadline_s,
        jsonl_path=None,
    )
    latency_ms = (time.perf_counter() - started) * 1000.0
    statuses = _status_map(report)
    return TrialMeasurement(
        latency_ms=latency_ms,
        ttfe_ms=None,
        request_bytes=req_bytes,
        response_bytes=response_bytes_for(transport, report),
        partial=report.partial,
        severity_status=statuses.get("severity", AgentStatus.FAILED.value),
        runbook_status=statuses.get("runbook", AgentStatus.FAILED.value),
        log_analysis_status=statuses.get("log_analysis", AgentStatus.FAILED.value),
        error=_first_error(report),
    )


async def measure_stream_trial(
    *,
    request: IncidentRequest,
    grpc_endpoints: AgentEndpoints | None = None,
    unary_deadline_s: float,
    stream_deadline_s: float,
) -> TrialMeasurement:
    """Time one mixed gRPC stream orchestrator call and capture TTFE."""
    req_bytes = request_bytes_for("grpc", request)
    ttfe_holder: dict[str, float] = {}
    started = time.perf_counter()

    def on_event(_event) -> None:
        if "ttfe_ms" not in ttfe_holder:
            ttfe_holder["ttfe_ms"] = (time.perf_counter() - started) * 1000.0

    report = await orchestrate(
        request,
        endpoints=grpc_endpoints,
        unary_deadline_s=unary_deadline_s,
        stream_deadline_s=stream_deadline_s,
        jsonl_path=None,
        on_stream_event=on_event,
    )
    latency_ms = (time.perf_counter() - started) * 1000.0
    statuses = _status_map(report)
    return TrialMeasurement(
        latency_ms=latency_ms,
        ttfe_ms=ttfe_holder.get("ttfe_ms"),
        request_bytes=req_bytes,
        response_bytes=response_bytes_for("grpc", report),
        partial=report.partial,
        severity_status=statuses.get("severity", AgentStatus.FAILED.value),
        runbook_status=statuses.get("runbook", AgentStatus.FAILED.value),
        log_analysis_status=statuses.get("log_analysis", AgentStatus.FAILED.value),
        error=_first_error(report),
    )
