"""Aggregate raw Stage 7 trial CSV rows into summary.csv and charts."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
import statistics
from typing import Any


SUMMARY_CSV_FIELDS = (
    "transport",
    "payload_size",
    "concurrency",
    "n",
    "median_latency_ms",
    "p95_latency_ms",
    "throughput_rps",
    "median_request_bytes",
    "median_response_bytes",
    "success_rate",
    "timeout_rate",
    "unavailable_rate",
    "failed_rate",
    "invalid_rate",
    "median_ttfe_ms",
    "p95_ttfe_ms",
)


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return float("nan")
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    weight = rank - low
    return sorted_values[low] * (1.0 - weight) + sorted_values[high] * weight


def _rate(rows: list[dict[str, str]], predicate) -> float:
    if not rows:
        return 0.0
    return sum(1 for row in rows if predicate(row)) / len(rows)


def _agent_has(row: dict[str, str], status: str) -> bool:
    return status in {
        row["severity_status"],
        row["runbook_status"],
        row["log_analysis_status"],
    }


def summarize_trials(trials_path: Path | str) -> list[dict[str, Any]]:
    """Group timed trials into locked summary rows."""
    path = Path(trials_path)
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        key = (row["transport"], row["payload_size"], row["concurrency"])
        grouped[key].append(row)

    summaries: list[dict[str, Any]] = []
    for (transport, payload_size, concurrency), cell_rows in sorted(
        grouped.items(),
        key=lambda item: (item[0][0], int(item[0][1]), int(item[0][2])),
    ):
        latencies = sorted(float(row["latency_ms"]) for row in cell_rows)
        request_bytes = sorted(int(row["request_bytes"]) for row in cell_rows)
        response_bytes = sorted(int(row["response_bytes"]) for row in cell_rows)
        ttfe = sorted(
            float(row["ttfe_ms"])
            for row in cell_rows
            if row.get("ttfe_ms") not in (None, "")
        )
        concurrency_n = int(concurrency)
        median_latency = statistics.median(latencies)
        # Throughput for a cell: mean of (concurrency / trial_wall_seconds).
        throughputs = [
            concurrency_n / (float(row["latency_ms"]) / 1000.0)
            for row in cell_rows
            if float(row["latency_ms"]) > 0
        ]
        summaries.append(
            {
                "transport": transport,
                "payload_size": int(payload_size),
                "concurrency": concurrency_n,
                "n": len(cell_rows),
                "median_latency_ms": median_latency,
                "p95_latency_ms": _percentile(latencies, 95),
                "throughput_rps": (
                    statistics.mean(throughputs) if throughputs else 0.0
                ),
                "median_request_bytes": statistics.median(request_bytes),
                "median_response_bytes": statistics.median(response_bytes),
                "success_rate": _rate(
                    cell_rows,
                    lambda row: row["partial"].lower() == "false",
                ),
                "timeout_rate": _rate(
                    cell_rows,
                    lambda row: _agent_has(row, "TIMEOUT"),
                ),
                "unavailable_rate": _rate(
                    cell_rows,
                    lambda row: _agent_has(row, "UNAVAILABLE"),
                ),
                "failed_rate": _rate(
                    cell_rows,
                    lambda row: _agent_has(row, "FAILED"),
                ),
                "invalid_rate": _rate(
                    cell_rows,
                    lambda row: _agent_has(row, "INVALID_ARGUMENT"),
                ),
                "median_ttfe_ms": (
                    statistics.median(ttfe) if ttfe else ""
                ),
                "p95_ttfe_ms": (_percentile(ttfe, 95) if ttfe else ""),
            }
        )
    return summaries


def write_summary_csv(
    trials_path: Path | str,
    summary_path: Path | str | None = None,
) -> Path:
    """Write ``summary.csv`` next to ``trials.csv`` (or to ``summary_path``)."""
    trials = Path(trials_path)
    out = Path(summary_path) if summary_path is not None else trials.with_name(
        "summary.csv"
    )
    rows = summarize_trials(trials)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            serialized = {
                key: (
                    f"{row[key]:.3f}"
                    if isinstance(row[key], float)
                    else row[key]
                )
                for key in SUMMARY_CSV_FIELDS
            }
            writer.writerow(serialized)
    return out


def write_charts(summary_path: Path | str, charts_dir: Path | str | None = None) -> list[Path]:
    """Render locked Stage 7 comparison charts from ``summary.csv``."""
    try:
        import matplotlib.pyplot as plt
    except ImportError as error:  # pragma: no cover - optional for bare installs
        raise RuntimeError(
            "matplotlib is required for charts; pip install matplotlib"
        ) from error

    summary = Path(summary_path)
    out_dir = Path(charts_dir) if charts_dir is not None else summary.parent / "charts"
    out_dir.mkdir(parents=True, exist_ok=True)

    with summary.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    written: list[Path] = []

    def _rows_for(*transports: str) -> list[dict[str, str]]:
        return [row for row in rows if row["transport"] in transports]

    # Latency median by payload for concurrency=1 unary transports.
    unary = [
        row
        for row in _rows_for("grpc", "http")
        if int(row["concurrency"]) == 1
    ]
    if unary:
        fig, ax = plt.subplots()
        for transport in ("grpc", "http"):
            series = [row for row in unary if row["transport"] == transport]
            series.sort(key=lambda row: int(row["payload_size"]))
            if not series:
                continue
            ax.plot(
                [int(row["payload_size"]) for row in series],
                [float(row["median_latency_ms"]) for row in series],
                marker="o",
                label=transport,
            )
        ax.set_xlabel("payload size (log lines)")
        ax.set_ylabel("median latency (ms)")
        ax.set_title("Unary median latency vs payload (concurrency=1)")
        ax.legend()
        ax.grid(True, alpha=0.3)
        path = out_dir / "unary_latency_vs_payload.png"
        fig.savefig(path, dpi=140, bbox_inches="tight")
        plt.close(fig)
        written.append(path)

    # Throughput at payload=1000 across concurrency.
    throughput_rows = [
        row
        for row in _rows_for("grpc", "http")
        if int(row["payload_size"]) == 1000
    ]
    if throughput_rows:
        fig, ax = plt.subplots()
        for transport in ("grpc", "http"):
            series = [row for row in throughput_rows if row["transport"] == transport]
            series.sort(key=lambda row: int(row["concurrency"]))
            if not series:
                continue
            ax.plot(
                [int(row["concurrency"]) for row in series],
                [float(row["throughput_rps"]) for row in series],
                marker="o",
                label=transport,
            )
        ax.set_xlabel("concurrency")
        ax.set_ylabel("throughput (req/s)")
        ax.set_title("Unary throughput vs concurrency (payload=1000)")
        ax.legend()
        ax.grid(True, alpha=0.3)
        path = out_dir / "unary_throughput_vs_concurrency.png"
        fig.savefig(path, dpi=140, bbox_inches="tight")
        plt.close(fig)
        written.append(path)

    # Stream TTFE vs payload at concurrency=1.
    stream_rows = [
        row
        for row in _rows_for("grpc-stream")
        if int(row["concurrency"]) == 1 and row.get("median_ttfe_ms")
    ]
    if stream_rows:
        stream_rows.sort(key=lambda row: int(row["payload_size"]))
        fig, ax = plt.subplots()
        ax.plot(
            [int(row["payload_size"]) for row in stream_rows],
            [float(row["median_ttfe_ms"]) for row in stream_rows],
            marker="o",
            label="grpc-stream",
        )
        ax.set_xlabel("payload size (log lines)")
        ax.set_ylabel("median TTFE (ms)")
        ax.set_title("Stream time-to-first-event vs payload")
        ax.legend()
        ax.grid(True, alpha=0.3)
        path = out_dir / "stream_ttfe_vs_payload.png"
        fig.savefig(path, dpi=140, bbox_inches="tight")
        plt.close(fig)
        written.append(path)

    return written
