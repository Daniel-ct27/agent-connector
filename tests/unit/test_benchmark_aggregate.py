"""Unit tests for Stage 7 summary aggregation."""

from __future__ import annotations

import csv
from pathlib import Path

from agent_connector.benchmarks.aggregate import summarize_trials, write_summary_csv


def _write_trials(path: Path) -> None:
    rows = [
        {
            "run_id": "r1",
            "transport": "grpc",
            "payload_size": "100",
            "concurrency": "1",
            "trial_index": "1",
            "incident_id": "inc-bench-100",
            "latency_ms": "10.0",
            "ttfe_ms": "",
            "request_bytes": "1000",
            "response_bytes": "200",
            "partial": "false",
            "severity_status": "OK",
            "runbook_status": "OK",
            "log_analysis_status": "OK",
            "error": "",
        },
        {
            "run_id": "r1",
            "transport": "grpc",
            "payload_size": "100",
            "concurrency": "1",
            "trial_index": "2",
            "incident_id": "inc-bench-100",
            "latency_ms": "30.0",
            "ttfe_ms": "",
            "request_bytes": "1000",
            "response_bytes": "220",
            "partial": "false",
            "severity_status": "OK",
            "runbook_status": "OK",
            "log_analysis_status": "OK",
            "error": "",
        },
        {
            "run_id": "r1",
            "transport": "http",
            "payload_size": "100",
            "concurrency": "1",
            "trial_index": "1",
            "incident_id": "inc-bench-100",
            "latency_ms": "40.0",
            "ttfe_ms": "",
            "request_bytes": "1200",
            "response_bytes": "300",
            "partial": "true",
            "severity_status": "OK",
            "runbook_status": "TIMEOUT",
            "log_analysis_status": "OK",
            "error": "deadline",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def test_summarize_trials_computes_median_and_rates() -> None:
    out_dir = (
        Path(__file__).resolve().parents[2] / ".pytest_tmp" / "benchmark_aggregate"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    trials = out_dir / "trials.csv"
    _write_trials(trials)

    summaries = summarize_trials(trials)
    assert len(summaries) == 2
    grpc = next(row for row in summaries if row["transport"] == "grpc")
    http = next(row for row in summaries if row["transport"] == "http")
    assert grpc["n"] == 2
    assert grpc["median_latency_ms"] == 20.0
    assert grpc["success_rate"] == 1.0
    assert http["timeout_rate"] == 1.0
    assert http["success_rate"] == 0.0

    summary_path = write_summary_csv(trials)
    assert summary_path.is_file()
    assert "median_latency_ms" in summary_path.read_text(encoding="utf-8")
