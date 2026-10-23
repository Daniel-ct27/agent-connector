"""Unit tests for orchestrator JSONL path normalization."""

from __future__ import annotations

from pathlib import Path

from agent_connector.orchestrator.jsonl import JsonlLogger, normalize_jsonl_path


def test_normalize_jsonl_path_disables_empty_values() -> None:
    assert normalize_jsonl_path(None) is None
    assert normalize_jsonl_path("") is None
    assert normalize_jsonl_path("   ") is None
    assert normalize_jsonl_path(Path("")) is None
    assert normalize_jsonl_path(Path(".")) is None


def test_normalize_jsonl_path_keeps_real_paths() -> None:
    assert normalize_jsonl_path("logs/run.jsonl") == Path("logs/run.jsonl")
    assert normalize_jsonl_path(Path("out.jsonl")) == Path("out.jsonl")


def test_jsonl_logger_skips_emit_when_disabled() -> None:
    with JsonlLogger("") as logger:
        logger.emit("call_started", run_id="x", incident_id="y")
    with JsonlLogger(None) as logger:
        logger.emit("call_started", run_id="x", incident_id="y")
