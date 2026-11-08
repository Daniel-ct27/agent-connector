"""Concurrent race/stress smoke against ephemeral gRPC + HTTP agents.

Launches agents, then fires overlapping unary waves looking for unexpected
partials, crashes, or status mismatches under load.
"""

from __future__ import annotations

import asyncio
from collections import Counter
import socket
import time

import uvicorn

from agent_connector.agents.log_analysis import analyze_logs, analyze_logs_stream
from agent_connector.agents.runbook import recommend_actions
from agent_connector.agents.severity import analyze_severity
from agent_connector.analyzers import DeterministicAnalyzer
from agent_connector.benchmarks.fixtures import generate_incident
from agent_connector.domain.models import AgentStatus, IncidentRequest, LogAnalysisResult
from agent_connector.generated import incident_pb2_grpc as pb_grpc
from agent_connector.grpc_services.lifecycle import start_server
from agent_connector.grpc_services.log_analysis import LogAnalysisGrpcService
from agent_connector.grpc_services.runbook import RunbookGrpcService
from agent_connector.grpc_services.severity import SeverityGrpcService
from agent_connector.http_services.log_analysis import create_log_analysis_app
from agent_connector.http_services.runbook import create_runbook_app
from agent_connector.http_services.severity import create_severity_app
from agent_connector.orchestrator import AgentEndpoints, HttpAgentEndpoints, orchestrate_unary


PAYLOAD = 1_000
WAVES = 20
CONCURRENCY = 10
UNARY_DEADLINE_S = 5.0


class _HttpServer:
    def __init__(self, server: uvicorn.Server, task: asyncio.Task, base_url: str) -> None:
        self.server = server
        self.task = task
        self.base_url = base_url

    async def stop(self) -> None:
        self.server.should_exit = True
        await self.task


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _start_http(app) -> _HttpServer:
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    for _ in range(400):
        if server.started:
            break
        await asyncio.sleep(0.01)
    else:
        server.should_exit = True
        await task
        raise RuntimeError("HTTP server failed to start")
    return _HttpServer(server, task, f"http://127.0.0.1:{port}")


async def _start_stack():
    analyzer = DeterministicAnalyzer()

    def logs(request: IncidentRequest) -> LogAnalysisResult:
        return analyze_logs(request, analyzer=analyzer)

    g_sev = await start_server(
        lambda server: pb_grpc.add_SeverityServiceServicer_to_server(
            SeverityGrpcService(analyze_severity),
            server,
        ),
        port=0,
    )
    g_run = await start_server(
        lambda server: pb_grpc.add_RunbookServiceServicer_to_server(
            RunbookGrpcService(recommend_actions),
            server,
        ),
        port=0,
    )
    g_log = await start_server(
        lambda server: pb_grpc.add_LogAnalysisServiceServicer_to_server(
            LogAnalysisGrpcService(logs, analyze_logs_stream),
            server,
        ),
        port=0,
    )
    grpc_endpoints = AgentEndpoints(
        severity=g_sev.target,
        runbook=g_run.target,
        log_analysis=g_log.target,
    )

    h_sev = await _start_http(create_severity_app(analyze_severity))
    h_run = await _start_http(create_runbook_app(recommend_actions))
    h_log = await _start_http(create_log_analysis_app(logs))
    http_endpoints = HttpAgentEndpoints(
        severity=h_sev.base_url,
        runbook=h_run.base_url,
        log_analysis=h_log.base_url,
    )
    return (g_sev, g_run, g_log, h_sev, h_run, h_log, grpc_endpoints, http_endpoints)


async def _wave(
    *,
    transport: str,
    wave_index: int,
    grpc_endpoints: AgentEndpoints,
    http_endpoints: HttpAgentEndpoints,
) -> list:
    base = generate_incident(PAYLOAD)

    async def one(i: int):
        request = base.model_copy(
            update={"incident_id": f"stress-{transport}-w{wave_index}-i{i}"}
        )
        return await orchestrate_unary(
            request,
            transport=transport,  # type: ignore[arg-type]
            grpc_endpoints=grpc_endpoints,
            http_endpoints=http_endpoints,
            unary_deadline_s=UNARY_DEADLINE_S,
            jsonl_path=None,
        )

    return list(await asyncio.gather(*[one(i) for i in range(CONCURRENCY)]))


async def main() -> int:
    stack = await _start_stack()
    g_sev, g_run, g_log, h_sev, h_run, h_log, grpc_endpoints, http_endpoints = stack
    totals = Counter()
    bad = 0
    started = time.perf_counter()
    try:
        for transport in ("grpc", "http"):
            print(
                f"stress {transport}: {WAVES} waves x {CONCURRENCY} "
                f"concurrent, payload={PAYLOAD}"
            )
            for wave in range(WAVES):
                reports = await _wave(
                    transport=transport,
                    wave_index=wave,
                    grpc_endpoints=grpc_endpoints,
                    http_endpoints=http_endpoints,
                )
                for report in reports:
                    totals["requests"] += 1
                    if report.partial:
                        bad += 1
                        totals["partial"] += 1
                        for outcome in report.agent_outcomes:
                            if outcome.status != AgentStatus.OK:
                                totals[f"{outcome.name}:{outcome.status.value}"] += 1
                    else:
                        totals["ok"] += 1
                if (wave + 1) % 5 == 0:
                    print(f"  {transport} wave {wave + 1}/{WAVES} ok")
    finally:
        await g_sev.stop(0)
        await g_run.stop(0)
        await g_log.stop(0)
        await h_sev.stop()
        await h_run.stop()
        await h_log.stop()

    elapsed = time.perf_counter() - started
    print("--- stress summary ---")
    print(f"elapsed_s={elapsed:.2f}")
    for key, value in sorted(totals.items()):
        print(f"{key}={value}")
    if bad:
        print(f"FAILED: {bad} partial/failed requests under load")
        return 1
    print("PASSED: no partial reports under race/stress load")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
