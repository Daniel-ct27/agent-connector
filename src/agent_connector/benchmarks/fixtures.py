"""Reproducible multi-size synthetic incident fixtures."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import random

from agent_connector.config import (
    BENCHMARK_FIXTURE_SEED,
    BENCHMARK_PAYLOAD_SIZES,
    MAX_LOG_ENTRIES,
)
from agent_connector.domain.models import IncidentRequest, LogEntry, LogLevel


_SERVICES = ("api-gateway", "checkout-service", "orders-db")
_ERROR_TEMPLATES = (
    "failed to open database connection: dial tcp 10.0.2.15:5432: i/o timeout",
    "upstream request failed: connection refused to checkout-service:8080",
    "could not accept connections: too many clients already",
    "returning 503 for /checkout after upstream timeout",
)
_LEVELS = (LogLevel.ERROR, LogLevel.ERROR, LogLevel.FATAL, LogLevel.WARN)


def generate_incident(
    payload_size: int,
    *,
    seed: int = BENCHMARK_FIXTURE_SEED,
    incident_id: str | None = None,
) -> IncidentRequest:
    """Build a deterministic ``db_connection_failure`` incident of exact size."""
    if payload_size < 1:
        raise ValueError("payload_size must be >= 1")
    if payload_size > MAX_LOG_ENTRIES:
        raise ValueError(
            f"payload_size must be <= MAX_LOG_ENTRIES ({MAX_LOG_ENTRIES})"
        )

    rng = random.Random(seed ^ payload_size)
    base = datetime(2026, 3, 15, 14, 2, 0, tzinfo=timezone.utc)
    logs: list[LogEntry] = []
    for index in range(payload_size):
        template_index = index % len(_ERROR_TEMPLATES)
        service = _SERVICES[index % len(_SERVICES)]
        level = _LEVELS[template_index]
        timestamp = (base + timedelta(seconds=index)).isoformat().replace(
            "+00:00",
            "Z",
        )
        message = _ERROR_TEMPLATES[template_index]
        if level in (LogLevel.ERROR, LogLevel.FATAL) and "timeout" in message:
            message = f"{message} attempt {1 + (index // len(_ERROR_TEMPLATES))}"
        metadata = {
            "request_id": f"req-{10_000 + index}",
            "seq": str(index),
        }
        if rng.random() < 0.25:
            metadata["shard"] = str(rng.randint(0, 3))
        logs.append(
            LogEntry(
                timestamp=timestamp,
                service=service,
                level=level,
                message=message,
                metadata=metadata,
            )
        )

    return IncidentRequest(
        incident_id=incident_id or f"inc-bench-{payload_size}",
        scenario="db_connection_failure",
        logs=logs,
    )


def generated_fixture_path(
    payload_size: int,
    *,
    directory: Path | str = "scenarios/generated",
) -> Path:
    """Return the canonical path for a generated fixture of ``payload_size``."""
    return Path(directory) / f"inc-bench-{payload_size}.json"


def write_generated_fixtures(
    *,
    sizes: tuple[int, ...] = BENCHMARK_PAYLOAD_SIZES,
    seed: int = BENCHMARK_FIXTURE_SEED,
    directory: Path | str = "scenarios/generated",
) -> list[Path]:
    """Write generated fixtures to disk and return their paths."""
    out_dir = Path(directory)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for size in sizes:
        path = generated_fixture_path(size, directory=out_dir)
        incident = generate_incident(size, seed=seed)
        path.write_text(
            incident.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return written


def load_or_generate_incident(
    payload_size: int,
    *,
    directory: Path | str = "scenarios/generated",
    seed: int = BENCHMARK_FIXTURE_SEED,
) -> IncidentRequest:
    """Load a generated fixture if present, otherwise build it in memory."""
    path = generated_fixture_path(payload_size, directory=directory)
    if path.is_file():
        return IncidentRequest.model_validate(
            json.loads(path.read_text(encoding="utf-8"))
        )
    return generate_incident(payload_size, seed=seed)
