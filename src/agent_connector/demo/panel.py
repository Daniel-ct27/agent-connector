"""Local demo control panel: start/stop agents, run fixtures, view results."""

from __future__ import annotations

import asyncio
import csv
import json
from pathlib import Path
import time

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent_connector.agentic import run_agentic
from agent_connector.analyzers.base import AnalyzerConfigError
from agent_connector.benchmarks.fixtures import generate_incident
from agent_connector.config import (
    BENCHMARK_CONCURRENCY_LEVELS,
    BENCHMARK_PAYLOAD_SIZES,
    DEFAULT_PLANNER,
    MAX_LOG_ENTRIES,
    UNARY_DEADLINE_SECONDS,
)
from agent_connector.demo.process_manager import ProcessManager
from agent_connector.domain.models import AgenticStep, IncidentRequest, IncidentReport
from agent_connector.orchestrator import (
    AgentEndpoints,
    HttpAgentEndpoints,
    orchestrate,
    orchestrate_unary,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = REPO_ROOT / "report"
STATIC_DIR = Path(__file__).resolve().parent / "static"
FIXTURES_DIR = REPO_ROOT / "scenarios" / "fixtures"

manager = ProcessManager()


class WorkloadRequest(BaseModel):
    """Interactive demo workload selection."""

    transport: str = Field(
        default="grpc-stream",
        pattern="^(grpc-stream|grpc-unary|http-unary|agentic)$",
    )
    source: str = Field(default="generated", pattern="^(fixture|generated)$")
    fixture: str = "inc-db-001.json"
    payload_size: int = Field(default=1000, ge=1, le=MAX_LOG_ENTRIES)
    concurrency: int = Field(default=1, ge=1, le=20)
    planner: str = Field(default=DEFAULT_PLANNER)


class AgenticRequest(BaseModel):
    """Dedicated agentic response-system run."""

    source: str = Field(default="fixture", pattern="^(fixture|generated)$")
    fixture: str = "inc-db-001.json"
    payload_size: int = Field(default=1000, ge=1, le=MAX_LOG_ENTRIES)
    planner: str = Field(default=DEFAULT_PLANNER)


def create_demo_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        manager.stop_all()

    app = FastAPI(
        title="Agent Connector Demo Panel",
        docs_url="/api/docs",
        lifespan=lifespan,
    )
    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    if (REPORT_DIR / "charts").is_dir():
        app.mount(
            "/charts",
            StaticFiles(directory=REPORT_DIR / "charts"),
            name="charts",
        )

    def _html_page(name: str) -> HTMLResponse:
        page_path = STATIC_DIR / name
        if not page_path.is_file():
            raise HTTPException(status_code=500, detail=f"demo UI missing: {name}")
        return HTMLResponse(page_path.read_text(encoding="utf-8"))

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        return _html_page("index.html")

    @app.get("/response", response_class=HTMLResponse)
    async def response_page() -> HTMLResponse:
        return _html_page("response.html")

    @app.get("/lab", response_class=HTMLResponse)
    async def lab_page() -> HTMLResponse:
        return _html_page("lab.html")

    @app.get("/api/servers")
    async def servers() -> dict:
        return {"servers": manager.status()}

    @app.post("/api/servers/{key}/start")
    async def start_server(key: str) -> dict:
        try:
            return manager.start(key)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post("/api/servers/{key}/stop")
    async def stop_server(key: str) -> dict:
        try:
            return manager.stop(key)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/servers/start-grpc")
    async def start_grpc() -> dict:
        try:
            return {"results": manager.start_group("grpc")}
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post("/api/servers/start-http")
    async def start_http() -> dict:
        try:
            return {"results": manager.start_group("http")}
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post("/api/servers/stop-all")
    async def stop_all() -> dict:
        return {"results": manager.stop_all()}

    @app.get("/api/fixtures")
    async def fixtures() -> dict:
        names = sorted(path.name for path in FIXTURES_DIR.glob("inc-*.json"))
        return {
            "fixtures": names,
            "payload_sizes": list(BENCHMARK_PAYLOAD_SIZES),
            "concurrency_levels": list(BENCHMARK_CONCURRENCY_LEVELS),
            "max_log_entries": MAX_LOG_ENTRIES,
        }

    @app.get("/api/summary")
    async def summary() -> dict:
        path = REPORT_DIR / "summary.csv"
        if not path.is_file():
            return {"rows": [], "note": "report/summary.csv not found", "charts": {}}
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        return {
            "rows": rows,
            "source": "report/summary.csv",
            "charts": _chart_payloads(rows),
        }

    async def _run_transport(
        transport: str,
        request: IncidentRequest,
        *,
        planner: str = DEFAULT_PLANNER,
    ) -> tuple[IncidentReport, float]:
        started = time.perf_counter()
        if transport == "agentic":
            report = await asyncio.to_thread(
                run_agentic,
                request,
                planner=planner,
            )
        elif transport == "grpc-stream":
            report = await orchestrate(
                request,
                endpoints=AgentEndpoints(),
                unary_deadline_s=UNARY_DEADLINE_SECONDS,
                jsonl_path=None,
            )
        elif transport == "grpc-unary":
            report = await orchestrate_unary(
                request,
                transport="grpc",
                grpc_endpoints=AgentEndpoints(),
                unary_deadline_s=UNARY_DEADLINE_SECONDS,
                jsonl_path=None,
            )
        else:
            report = await orchestrate_unary(
                request,
                transport="http",
                http_endpoints=HttpAgentEndpoints(),
                unary_deadline_s=UNARY_DEADLINE_SECONDS,
                jsonl_path=None,
            )
        latency_ms = (time.perf_counter() - started) * 1000.0
        return report, latency_ms

    def _resolve_request(
        *,
        source: str,
        fixture: str,
        payload_size: int,
    ) -> IncidentRequest:
        if source == "fixture":
            fixture_path = FIXTURES_DIR / fixture
            if not fixture_path.is_file():
                raise HTTPException(
                    status_code=404,
                    detail=f"fixture not found: {fixture}",
                )
            return IncidentRequest.model_validate(
                json.loads(fixture_path.read_text(encoding="utf-8"))
            )
        try:
            return generate_incident(payload_size)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    async def _wave(
        transport: str,
        base: IncidentRequest,
        concurrency: int,
        *,
        planner: str = DEFAULT_PLANNER,
    ) -> dict:
        started = time.perf_counter()

        async def one(index: int) -> tuple[IncidentReport, float]:
            request = base.model_copy(
                update={"incident_id": f"{base.incident_id}-c{concurrency}-i{index}"}
            )
            return await _run_transport(transport, request, planner=planner)

        results = await asyncio.gather(*[one(i) for i in range(concurrency)])
        wall_ms = (time.perf_counter() - started) * 1000.0
        reports = [item[0] for item in results]
        latencies = [item[1] for item in results]
        return {
            "wall_latency_ms": round(wall_ms, 3),
            "mean_request_latency_ms": round(sum(latencies) / len(latencies), 3),
            "partial": any(report.partial for report in reports),
            "report": reports[0].model_dump(mode="json"),
            "concurrency": concurrency,
        }

    @app.post("/api/analyze")
    async def analyze(body: WorkloadRequest) -> dict:
        request = _resolve_request(
            source=body.source,
            fixture=body.fixture,
            payload_size=body.payload_size,
        )
        wave = await _wave(
            body.transport,
            request,
            body.concurrency,
            planner=body.planner,
        )
        return {
            "transport": body.transport,
            "source": body.source,
            "fixture": body.fixture if body.source == "fixture" else None,
            "payload_size": (
                body.payload_size
                if body.source == "generated"
                else len(request.logs)
            ),
            "concurrency": body.concurrency,
            "latency_ms": wave["wall_latency_ms"],
            "mean_request_latency_ms": wave["mean_request_latency_ms"],
            "partial": wave["partial"],
            "report": wave["report"],
        }

    def _agentic_payload(
        *,
        body: AgenticRequest,
        request: IncidentRequest,
        report: IncidentReport,
        steps: list[dict],
        latency_ms: float,
    ) -> dict:
        return {
            "transport": "agentic",
            "planner": report.agentic_mode or body.planner,
            "source": body.source,
            "fixture": body.fixture if body.source == "fixture" else None,
            "payload_size": len(request.logs),
            "latency_ms": round(latency_ms, 3),
            "partial": report.partial,
            "planner_degraded": report.planner_degraded,
            "planner_error": report.planner_error,
            "steps": steps,
            "report": report.model_dump(mode="json"),
        }

    @app.post("/api/agentic")
    async def agentic(body: AgenticRequest) -> dict:
        """Run the observe→decide→act response path and return a step timeline."""
        request = _resolve_request(
            source=body.source,
            fixture=body.fixture,
            payload_size=body.payload_size,
        )
        steps: list[dict] = []

        def on_step(step: AgenticStep) -> None:
            steps.append(step.model_dump(mode="json"))

        started = time.perf_counter()
        try:
            report = await asyncio.to_thread(
                run_agentic,
                request,
                planner=body.planner,
                on_step=on_step,
            )
        except AnalyzerConfigError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(
                status_code=500,
                detail="agentic run failed",
            ) from error
        latency_ms = (time.perf_counter() - started) * 1000.0
        return _agentic_payload(
            body=body,
            request=request,
            report=report,
            steps=steps,
            latency_ms=latency_ms,
        )

    @app.post("/api/agentic/stream")
    async def agentic_stream(body: AgenticRequest) -> StreamingResponse:
        """Stream NDJSON events as the agentic loop observes, decides, and acts."""
        request = _resolve_request(
            source=body.source,
            fixture=body.fixture,
            payload_size=body.payload_size,
        )
        queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()
        loop = asyncio.get_running_loop()
        started = time.perf_counter()

        def on_step(step: AgenticStep) -> None:
            loop.call_soon_threadsafe(
                queue.put_nowait,
                ("step", step.model_dump(mode="json")),
            )

        async def runner() -> None:
            try:
                report = await asyncio.to_thread(
                    run_agentic,
                    request,
                    planner=body.planner,
                    on_step=on_step,
                )
                latency_ms = (time.perf_counter() - started) * 1000.0
                await queue.put(
                    (
                        "done",
                        _agentic_payload(
                            body=body,
                            request=request,
                            report=report,
                            steps=[
                                step.model_dump(mode="json")
                                for step in report.agentic_steps
                            ],
                            latency_ms=latency_ms,
                        ),
                    )
                )
            except AnalyzerConfigError as error:
                await queue.put(("error", {"detail": str(error), "status": 400}))
            except Exception:
                await queue.put(
                    ("error", {"detail": "agentic run failed", "status": 500})
                )

        async def event_gen():
            task = asyncio.create_task(runner())
            try:
                while True:
                    kind, payload = await queue.get()
                    yield json.dumps({"event": kind, "data": payload}) + "\n"
                    if kind in ("done", "error"):
                        break
            finally:
                await task

        return StreamingResponse(event_gen(), media_type="application/x-ndjson")

    @app.post("/api/compare")
    async def compare(body: WorkloadRequest) -> dict:
        """Run unary gRPC and HTTP on the same workload side-by-side."""
        request = _resolve_request(
            source=body.source,
            fixture=body.fixture,
            payload_size=body.payload_size,
        )
        grpc_wave, http_wave = await asyncio.gather(
            _wave("grpc-unary", request, body.concurrency),
            _wave("http-unary", request, body.concurrency),
        )
        grpc_ms = grpc_wave["wall_latency_ms"]
        http_ms = http_wave["wall_latency_ms"]
        speedup = (http_ms / grpc_ms) if grpc_ms > 0 else None
        return {
            "source": body.source,
            "fixture": body.fixture if body.source == "fixture" else None,
            "payload_size": (
                body.payload_size
                if body.source == "generated"
                else len(request.logs)
            ),
            "concurrency": body.concurrency,
            "log_count": len(request.logs),
            "grpc": grpc_wave,
            "http": http_wave,
            "http_over_grpc_ratio": (
                None if speedup is None else round(speedup, 2)
            ),
        }

    return app


def _chart_payloads(rows: list[dict[str, str]]) -> dict:
    """Shape summary rows for interactive Chart.js series."""

    def _num(row: dict[str, str], key: str) -> float | None:
        value = row.get(key, "")
        if value in ("", None):
            return None
        return float(value)

    latency_labels = sorted(
        {
            int(row["payload_size"])
            for row in rows
            if row["concurrency"] == "1"
            and row["transport"] in {"grpc", "http"}
        }
    )
    latency_grpc = []
    latency_http = []
    for size in latency_labels:
        grpc = next(
            (
                _num(row, "median_latency_ms")
                for row in rows
                if row["transport"] == "grpc"
                and row["concurrency"] == "1"
                and int(row["payload_size"]) == size
            ),
            None,
        )
        http = next(
            (
                _num(row, "median_latency_ms")
                for row in rows
                if row["transport"] == "http"
                and row["concurrency"] == "1"
                and int(row["payload_size"]) == size
            ),
            None,
        )
        latency_grpc.append(grpc)
        latency_http.append(http)

    throughput_labels = sorted(
        {
            int(row["concurrency"])
            for row in rows
            if row["payload_size"] == "1000"
            and row["transport"] in {"grpc", "http"}
        }
    )
    throughput_grpc = []
    throughput_http = []
    for level in throughput_labels:
        throughput_grpc.append(
            next(
                (
                    _num(row, "throughput_rps")
                    for row in rows
                    if row["transport"] == "grpc"
                    and row["payload_size"] == "1000"
                    and int(row["concurrency"]) == level
                ),
                None,
            )
        )
        throughput_http.append(
            next(
                (
                    _num(row, "throughput_rps")
                    for row in rows
                    if row["transport"] == "http"
                    and row["payload_size"] == "1000"
                    and int(row["concurrency"]) == level
                ),
                None,
            )
        )

    ttfe_labels = sorted(
        {
            int(row["payload_size"])
            for row in rows
            if row["transport"] == "grpc-stream" and row["concurrency"] == "1"
        }
    )
    ttfe_values = []
    for size in ttfe_labels:
        ttfe_values.append(
            next(
                (
                    _num(row, "median_ttfe_ms")
                    for row in rows
                    if row["transport"] == "grpc-stream"
                    and row["concurrency"] == "1"
                    and int(row["payload_size"]) == size
                ),
                None,
            )
        )

    return {
        "latency": {
            "labels": latency_labels,
            "grpc": latency_grpc,
            "http": latency_http,
        },
        "throughput": {
            "labels": throughput_labels,
            "grpc": throughput_grpc,
            "http": throughput_http,
        },
        "ttfe": {
            "labels": ttfe_labels,
            "values": ttfe_values,
        },
    }
