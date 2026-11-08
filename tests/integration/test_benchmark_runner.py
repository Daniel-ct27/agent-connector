"""Integration smoke for a tiny Stage 7 benchmark matrix."""

from __future__ import annotations

import asyncio
import csv
import json
from pathlib import Path
import socket

import uvicorn

from agent_connector.agents.log_analysis import analyze_logs, analyze_logs_stream
from agent_connector.agents.runbook import recommend_actions
from agent_connector.agents.severity import analyze_severity
from agent_connector.analyzers import DeterministicAnalyzer
from agent_connector.benchmarks.runner import BenchmarkTransports, run_benchmark_matrix
from agent_connector.domain.models import IncidentRequest, LogAnalysisResult
from agent_connector.generated import incident_pb2_grpc as pb_grpc
from agent_connector.grpc_services.lifecycle import RunningServer, start_server
from agent_connector.grpc_services.log_analysis import LogAnalysisGrpcService
from agent_connector.grpc_services.runbook import RunbookGrpcService
from agent_connector.grpc_services.severity import SeverityGrpcService
from agent_connector.http_services.log_analysis import create_log_analysis_app
from agent_connector.http_services.runbook import create_runbook_app
from agent_connector.http_services.severity import create_severity_app
from agent_connector.orchestrator import AgentEndpoints, HttpAgentEndpoints


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


async def _start_http_app(app) -> _HttpServer:
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
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
    return _HttpServer(server, task, f"http://127.0.0.1:{port}")


async def _stop_http(*servers: _HttpServer) -> None:
    for server in servers:
        await server.stop()



async def _start_grpc() -> tuple[RunningServer, RunningServer, RunningServer, AgentEndpoints]:
    analyzer = DeterministicAnalyzer()

    def logs(request: IncidentRequest) -> LogAnalysisResult:
        return analyze_logs(request, analyzer=analyzer)

    severity_s = await start_server(
        lambda server: pb_grpc.add_SeverityServiceServicer_to_server(
            SeverityGrpcService(analyze_severity),
            server,
        ),
        port=0,
    )
    runbook_s = await start_server(
        lambda server: pb_grpc.add_RunbookServiceServicer_to_server(
            RunbookGrpcService(recommend_actions),
            server,
        ),
        port=0,
    )
    log_s = await start_server(
        lambda server: pb_grpc.add_LogAnalysisServiceServicer_to_server(
            LogAnalysisGrpcService(logs, analyze_logs_stream),
            server,
        ),
        port=0,
    )
    endpoints = AgentEndpoints(
        severity=severity_s.target,
        runbook=runbook_s.target,
        log_analysis=log_s.target,
    )
    return severity_s, runbook_s, log_s, endpoints


def test_tiny_matrix_writes_trials_csv() -> None:
    async def exercise() -> None:
        g_sev, g_run, g_log, grpc_endpoints = await _start_grpc()
        analyzer = DeterministicAnalyzer()

        def logs(request: IncidentRequest) -> LogAnalysisResult:
            return analyze_logs(request, analyzer=analyzer)

        h_sev = await _start_http_app(create_severity_app(analyze_severity))
        h_run = await _start_http_app(create_runbook_app(recommend_actions))
        h_log = await _start_http_app(create_log_analysis_app(logs))
        http_endpoints = HttpAgentEndpoints(
            severity=h_sev.base_url,
            runbook=h_run.base_url,
            log_analysis=h_log.base_url,
        )
        out_root = (
            Path(__file__).resolve().parents[2]
            / ".pytest_tmp"
            / "benchmark_runner"
        )
        try:
            out_dir = await run_benchmark_matrix(
                results_dir=out_root,
                transports=BenchmarkTransports(
                    grpc_unary=True,
                    http_unary=True,
                    grpc_stream=True,
                ),
                payload_sizes=(100,),
                concurrency_levels=(1,),
                warmup_trials=0,
                timed_trials=1,
                grpc_endpoints=grpc_endpoints,
                http_endpoints=http_endpoints,
            )
        finally:
            await g_sev.stop(0)
            await g_run.stop(0)
            await g_log.stop(0)
            await _stop_http(h_sev, h_run, h_log)

        trials_path = out_dir / "trials.csv"
        meta_path = out_dir / "run_meta.json"
        assert trials_path.is_file()
        assert meta_path.is_file()
        rows = list(csv.DictReader(trials_path.open(encoding="utf-8")))
        assert len(rows) == 3
        transports = {row["transport"] for row in rows}
        assert transports == {"grpc", "http", "grpc-stream"}
        for row in rows:
            assert row["payload_size"] == "100"
            assert row["concurrency"] == "1"
            assert float(row["latency_ms"]) > 0
            assert int(row["request_bytes"]) > 0
            if row["transport"] == "grpc-stream":
                assert row["ttfe_ms"] != ""
                assert float(row["ttfe_ms"]) > 0
            else:
                assert row["ttfe_ms"] == ""
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["timed_trials"] == 1
        assert "python" in meta

    asyncio.run(exercise())
