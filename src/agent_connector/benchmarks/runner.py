"""Stage 7 benchmark matrix runner (raw trials CSV + run metadata)."""

from __future__ import annotations

import asyncio
import csv
from dataclasses import dataclass
import json
import platform
from pathlib import Path
import sys
import time
import uuid

from agent_connector.benchmarks.fixtures import generate_incident
from agent_connector.benchmarks.measure import (
    TrialMeasurement,
    measure_stream_trial,
    measure_unary_trial,
)
from agent_connector.config import (
    BENCHMARK_CONCURRENCY_LEVELS,
    BENCHMARK_PAYLOAD_SIZES,
    BENCHMARK_TIMED_TRIALS,
    BENCHMARK_WARMUP_TRIALS,
    DEFAULT_BENCHMARK_RESULTS_DIR,
    STREAM_DEADLINE_SECONDS,
    UNARY_DEADLINE_SECONDS,
)
from agent_connector.orchestrator import AgentEndpoints, HttpAgentEndpoints


TRIAL_CSV_FIELDS = (
    "run_id",
    "transport",
    "payload_size",
    "concurrency",
    "trial_index",
    "incident_id",
    "latency_ms",
    "ttfe_ms",
    "request_bytes",
    "response_bytes",
    "partial",
    "severity_status",
    "runbook_status",
    "log_analysis_status",
    "error",
)


@dataclass(frozen=True)
class BenchmarkTransports:
    """Which transport cells to execute."""

    grpc_unary: bool = True
    http_unary: bool = True
    grpc_stream: bool = True


def _combine_wave(measurements: list[TrialMeasurement]) -> TrialMeasurement:
    """Collapse concurrent measurements into one trial row.

    Latency is the wall-clock of the concurrent wave (max individual latency
    when started together). Bytes are means. Partial/statuses reflect any
    non-OK outcome in the wave.
    """
    if not measurements:
        raise ValueError("measurements must not be empty")
    latency_ms = max(item.latency_ms for item in measurements)
    ttfe_values = [item.ttfe_ms for item in measurements if item.ttfe_ms is not None]
    partial = any(item.partial for item in measurements)

    def _pick_status(attr: str) -> str:
        values = [getattr(item, attr) for item in measurements]
        for value in values:
            if value != "OK":
                return value
        return "OK"

    errors = [item.error for item in measurements if item.error]
    return TrialMeasurement(
        latency_ms=latency_ms,
        ttfe_ms=(sum(ttfe_values) / len(ttfe_values)) if ttfe_values else None,
        request_bytes=round(
            sum(item.request_bytes for item in measurements) / len(measurements)
        ),
        response_bytes=round(
            sum(item.response_bytes for item in measurements) / len(measurements)
        ),
        partial=partial,
        severity_status=_pick_status("severity_status"),
        runbook_status=_pick_status("runbook_status"),
        log_analysis_status=_pick_status("log_analysis_status"),
        error=errors[0] if errors else "",
    )


async def _run_concurrent_wave(
    *,
    transport: str,
    payload_size: int,
    concurrency: int,
    grpc_endpoints: AgentEndpoints | None,
    http_endpoints: HttpAgentEndpoints | None,
    unary_deadline_s: float,
    stream_deadline_s: float,
) -> TrialMeasurement:
    base = generate_incident(payload_size)
    started = time.perf_counter()

    async def one(index: int) -> TrialMeasurement:
        request = base.model_copy(
            update={"incident_id": f"{base.incident_id}-c{concurrency}-i{index}"}
        )
        if transport == "grpc-stream":
            return await measure_stream_trial(
                request=request,
                grpc_endpoints=grpc_endpoints,
                unary_deadline_s=unary_deadline_s,
                stream_deadline_s=stream_deadline_s,
            )
        return await measure_unary_trial(
            transport="grpc" if transport == "grpc" else "http",
            request=request,
            grpc_endpoints=grpc_endpoints,
            http_endpoints=http_endpoints,
            unary_deadline_s=unary_deadline_s,
        )

    results = await asyncio.gather(*[one(i) for i in range(concurrency)])
    wall_ms = (time.perf_counter() - started) * 1000.0
    combined = _combine_wave(list(results))
    # Prefer true wave wall-clock over max-of-individuals for concurrency > 1.
    return TrialMeasurement(
        latency_ms=wall_ms,
        ttfe_ms=combined.ttfe_ms,
        request_bytes=combined.request_bytes,
        response_bytes=combined.response_bytes,
        partial=combined.partial,
        severity_status=combined.severity_status,
        runbook_status=combined.runbook_status,
        log_analysis_status=combined.log_analysis_status,
        error=combined.error,
    )


def _transport_names(selected: BenchmarkTransports) -> list[str]:
    names: list[str] = []
    if selected.grpc_unary:
        names.append("grpc")
    if selected.http_unary:
        names.append("http")
    if selected.grpc_stream:
        names.append("grpc-stream")
    return names


def write_run_meta(path: Path, *, run_id: str, extra: dict | None = None) -> None:
    """Write machine/library metadata beside a benchmark result set."""
    meta = {
        "run_id": run_id,
        "python": sys.version,
        "platform": platform.platform(),
        "hostname": platform.node(),
        "executable": sys.executable,
    }
    try:
        import fastapi
        import grpc
        import httpx
        import pydantic
        import uvicorn

        meta["libraries"] = {
            "grpcio": getattr(grpc, "__version__", "unknown"),
            "httpx": httpx.__version__,
            "fastapi": fastapi.__version__,
            "uvicorn": uvicorn.__version__,
            "pydantic": pydantic.__version__,
        }
    except Exception as error:  # pragma: no cover - metadata best-effort
        meta["libraries_error"] = str(error)
    if extra:
        meta.update(extra)
    path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


async def run_benchmark_matrix(
    *,
    results_dir: Path | str = DEFAULT_BENCHMARK_RESULTS_DIR,
    transports: BenchmarkTransports | None = None,
    payload_sizes: tuple[int, ...] = BENCHMARK_PAYLOAD_SIZES,
    concurrency_levels: tuple[int, ...] = BENCHMARK_CONCURRENCY_LEVELS,
    warmup_trials: int = BENCHMARK_WARMUP_TRIALS,
    timed_trials: int = BENCHMARK_TIMED_TRIALS,
    grpc_endpoints: AgentEndpoints | None = None,
    http_endpoints: HttpAgentEndpoints | None = None,
    unary_deadline_s: float = UNARY_DEADLINE_SECONDS,
    stream_deadline_s: float = STREAM_DEADLINE_SECONDS,
) -> Path:
    """Execute the locked matrix and write ``trials.csv`` + ``run_meta.json``."""
    selected = transports or BenchmarkTransports()
    run_id = str(uuid.uuid4())
    out_dir = Path(results_dir) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    trials_path = out_dir / "trials.csv"

    write_run_meta(
        out_dir / "run_meta.json",
        run_id=run_id,
        extra={
            "payload_sizes": list(payload_sizes),
            "concurrency_levels": list(concurrency_levels),
            "warmup_trials": warmup_trials,
            "timed_trials": timed_trials,
            "transports": _transport_names(selected),
        },
    )

    with trials_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRIAL_CSV_FIELDS)
        writer.writeheader()

        for transport in _transport_names(selected):
            for payload_size in payload_sizes:
                for concurrency in concurrency_levels:
                    for _ in range(warmup_trials):
                        await _run_concurrent_wave(
                            transport=transport,
                            payload_size=payload_size,
                            concurrency=concurrency,
                            grpc_endpoints=grpc_endpoints,
                            http_endpoints=http_endpoints,
                            unary_deadline_s=unary_deadline_s,
                            stream_deadline_s=stream_deadline_s,
                        )
                    for trial_index in range(1, timed_trials + 1):
                        measurement = await _run_concurrent_wave(
                            transport=transport,
                            payload_size=payload_size,
                            concurrency=concurrency,
                            grpc_endpoints=grpc_endpoints,
                            http_endpoints=http_endpoints,
                            unary_deadline_s=unary_deadline_s,
                            stream_deadline_s=stream_deadline_s,
                        )
                        writer.writerow(
                            {
                                "run_id": run_id,
                                "transport": transport,
                                "payload_size": payload_size,
                                "concurrency": concurrency,
                                "trial_index": trial_index,
                                "incident_id": f"inc-bench-{payload_size}",
                                "latency_ms": f"{measurement.latency_ms:.3f}",
                                "ttfe_ms": (
                                    ""
                                    if measurement.ttfe_ms is None
                                    else f"{measurement.ttfe_ms:.3f}"
                                ),
                                "request_bytes": measurement.request_bytes,
                                "response_bytes": measurement.response_bytes,
                                "partial": str(measurement.partial).lower(),
                                "severity_status": measurement.severity_status,
                                "runbook_status": measurement.runbook_status,
                                "log_analysis_status": measurement.log_analysis_status,
                                "error": measurement.error,
                            }
                        )
                        handle.flush()

    return out_dir
