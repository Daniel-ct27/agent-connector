"""Unit tests for Stage 7 synthetic fixture generation."""

from __future__ import annotations

from pathlib import Path

from agent_connector.benchmarks.fixtures import (
    generate_incident,
    write_generated_fixtures,
)
from agent_connector.config import BENCHMARK_PAYLOAD_SIZES, MAX_LOG_ENTRIES
from agent_connector.domain.validation import validate_incident_request
import pytest


def test_generate_incident_exact_sizes_and_reproducible() -> None:
    for size in BENCHMARK_PAYLOAD_SIZES:
        first = generate_incident(size)
        second = generate_incident(size)
        assert len(first.logs) == size
        assert first == second
        assert first.scenario == "db_connection_failure"
        validate_incident_request(first)


def test_generate_incident_rejects_over_limit() -> None:
    with pytest.raises(ValueError, match="MAX_LOG_ENTRIES"):
        generate_incident(MAX_LOG_ENTRIES + 1)


def test_write_generated_fixtures() -> None:
    out_dir = (
        Path(__file__).resolve().parents[2]
        / ".pytest_tmp"
        / "generated_fixtures"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = write_generated_fixtures(
        sizes=(100,),
        directory=out_dir,
    )
    assert len(paths) == 1
    assert paths[0].is_file()
    text = paths[0].read_text(encoding="utf-8")
    assert '"incident_id": "inc-bench-100"' in text
    assert text.count('"message"') == 100
