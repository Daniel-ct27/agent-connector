"""Local demo control panel: start/stop agents, run fixtures, view results."""

from __future__ import annotations

import asyncio
import csv
import json
from pathlib import Path
import time

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent_connector.config import UNARY_DEADLINE_SECONDS
from agent_connector.demo.process_manager import ProcessManager
from agent_connector.domain.models import IncidentRequest, IncidentReport
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


class AnalyzeRequest(BaseModel):
    transport: str = Field(
        default="grpc-stream",
        pattern="^(grpc-stream|grpc-unary|http-unary)$",
    )
    fixture: str = "inc-db-001.json"
    analyzer_note: str = (
        "Agents must already be running; analyzer is chosen at agent process start."
    )


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

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        index_path = STATIC_DIR / "index.html"
        if not index_path.is_file():
            raise HTTPException(status_code=500, detail="demo UI missing")
        return HTMLResponse(index_path.read_text(encoding="utf-8"))

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
        return {"fixtures": names}

    @app.get("/api/summary")
    async def summary() -> dict:
        path = REPORT_DIR / "summary.csv"
        if not path.is_file():
            return {"rows": [], "note": "report/summary.csv not found"}
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        return {"rows": rows, "source": "report/summary.csv"}

    async def _run_transport(transport: str, request: IncidentRequest) -> tuple[IncidentReport, float]:
        started = time.perf_counter()
        if transport == "grpc-stream":
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

    def _load_fixture(name: str) -> IncidentRequest:
        fixture_path = FIXTURES_DIR / name
        if not fixture_path.is_file():
            raise HTTPException(status_code=404, detail=f"fixture not found: {name}")
        return IncidentRequest.model_validate(
            json.loads(fixture_path.read_text(encoding="utf-8"))
        )

    @app.post("/api/analyze")
    async def analyze(body: AnalyzeRequest) -> dict:
        request = _load_fixture(body.fixture)
        report, latency_ms = await _run_transport(body.transport, request)
        return {
            "transport": body.transport,
            "fixture": body.fixture,
            "latency_ms": round(latency_ms, 3),
            "report": report.model_dump(mode="json"),
        }

    @app.post("/api/compare")
    async def compare(body: AnalyzeRequest) -> dict:
        """Run unary gRPC and HTTP on the same fixture for a live side-by-side demo."""
        request = _load_fixture(body.fixture)
        (grpc_report, grpc_ms), (http_report, http_ms) = await asyncio.gather(
            _run_transport("grpc-unary", request),
            _run_transport("http-unary", request),
        )
        speedup = (http_ms / grpc_ms) if grpc_ms > 0 else None
        return {
            "fixture": body.fixture,
            "grpc": {
                "latency_ms": round(grpc_ms, 3),
                "partial": grpc_report.partial,
                "report": grpc_report.model_dump(mode="json"),
            },
            "http": {
                "latency_ms": round(http_ms, 3),
                "partial": http_report.partial,
                "report": http_report.model_dump(mode="json"),
            },
            "http_over_grpc_ratio": (
                None if speedup is None else round(speedup, 2)
            ),
        }

    return app
